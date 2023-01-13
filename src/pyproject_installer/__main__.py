"""
Build features:
    - Linux only
    - build wheel from source tree (not tree => sdist => wheel)
    - build in current Python env (non-isolated)
    - build without checking build deps (up to the caller)
    - editable builds(PEP660) are not supported

Install features:
    - install without bytecompilation
    - RECORD is dropped (PEP627)
    - signature verification of signed wheel is not supported
"""
from pathlib import Path
import argparse
import json
import logging
import sys

from . import __version__ as project_version
from .build_cmd import build_wheel, build_sdist, WHEEL_TRACKER
from .codes import ExitCodes
from .errors import RunCommandError, RunCommandEnvError, DepsUnsyncedError
from .install_cmd import install_wheel
from .run_cmd import run_command
from .deps_cmd import deps_command, SUPPORTED_COLLECTORS, DEFAULT_CONFIG_NAME

logger = logging.getLogger(Path(__file__).parent.name)


def build(args, parser):
    outdir = args.srcdir / "dist" if args.outdir is None else args.outdir
    try:
        config_settings = convert_config_settings(args.backend_config_settings)
    except ValueError as e:
        parser.error(str(e))

    build_func = build_sdist if args.sdist else build_wheel
    build_func(
        args.srcdir,
        outdir=outdir,
        config=config_settings,
        verbose=args.verbose,
    )


def install(args, parser):
    try:
        wheel = default_built_wheel() if args.wheel is None else args.wheel
    except ValueError as e:
        parser.error(str(e))

    install_wheel(
        wheel,
        destdir=args.destdir,
        installer=args.installer,
        strip_dist_info=args.strip_dist_info,
    )


def deps(action_name):
    def wrapped(args, parser):
        if (
            hasattr(args, "depformatextra")
            and args.depformatextra is not None
            and args.depformat is None
        ):
            parser.error("depformatextra option must be used with depformat")
        kwargs = {x: getattr(args, x) for x in args.main_args}
        try:
            deps_command(action_name, args.depsconfig, **kwargs)
        except DepsUnsyncedError:
            # sync --verify error
            sys.exit(ExitCodes.SYNC_VERIFY_ERROR)

    return wrapped


class RunnerResult:
    def __init__(
        self, status, message, log, exception=None, print_traceback=False
    ):
        self.status = status
        self.message = message
        self.log = log
        self.exception = exception
        self.print_traceback = print_traceback

    def report(self):
        status_msg = "Command's result: %(status)s"
        if self.message is not None:
            status_msg += " (%(message)s)"
        self.log(
            status_msg, {"status": self.status.name, "message": self.message}
        )

        if self.exception is not None:
            error_msg = "Command's error:"
            if self.print_traceback:
                self.log(error_msg, exc_info=self.exception)
            else:
                self.log(f"{error_msg} %s", str(self.exception))


def run(args, parser):
    try:
        wheel = default_built_wheel() if args.wheel is None else args.wheel
    except ValueError as e:
        parser.error(str(e))

    try:
        run_command(wheel, command=args.command)
    except RunCommandEnvError as e:
        result = RunnerResult(
            status=ExitCodes.FAILURE,
            message="virtual env setup failed",
            log=logger.info,
            exception=e,
            print_traceback=True,
        )
    except RunCommandError as e:
        result = RunnerResult(
            status=ExitCodes.FAILURE,
            message=None,
            log=logger.info,
            exception=e,
            print_traceback=False,
        )
    except BaseException as e:
        result = RunnerResult(
            status=ExitCodes.INTERNAL_ERROR,
            message="internal error happened",
            log=logger.error,
            exception=e,
            print_traceback=True,
        )
    else:
        result = RunnerResult(
            status=ExitCodes.OK,
            message=None,
            log=logger.info,
        )

    result.report()
    sys.exit(result.status)


def default_built_wheel():
    """
    By default the `.build` module saves wheel into 'srcdir/dist' and tracks
    it in 'srcdir/dist/.wheeltracker'.
    """
    default_wheel_dir = Path.cwd() / "dist"
    try:
        wheel_filename = (
            (default_wheel_dir / WHEEL_TRACKER)
            .read_text(encoding="utf-8")
            .rstrip()
        )
    except FileNotFoundError:
        raise ValueError(
            "Missing wheel tracker, re-run build steps or specify wheel"
        ) from None

    return default_wheel_dir / wheel_filename


def convert_config_settings(value):
    if value is None:
        return None

    err_msg = (
        f"Invalid value of --backend-config-settings: {value!r}, "
        "should be a dumped JSON dictionary"
    )
    try:
        config_settings = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError(err_msg) from None

    if not isinstance(config_settings, dict):
        raise ValueError(err_msg) from None

    return config_settings


class MainArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        """Overrides default exit code(2) with our"""
        try:
            super().error(message)
        except SystemExit as e:
            e.code = ExitCodes.WRONG_USAGE
            raise


def deps_subparsers(parser):
    subparsers = parser.add_subparsers(
        title="deps subcommands",
        help="--help for additional help",
        required=True,
    )

    def add_deps_argument(parser, destname, *args, **kwargs):
        parser.add_argument(*args, **kwargs)
        destnames = parser.get_default("main_args") or []
        destnames.append(destname)
        parser.set_defaults(main_args=destnames)

    def add_deps_parser(parsers, name, *args, **kwargs):
        parser = parsers.add_parser(name, *args, **kwargs)
        parser.set_defaults(main=deps(name))
        return parser

    # show
    subparser_show = add_deps_parser(
        subparsers,
        "show",
        description="Show configuration and data of dependencies's sources.",
    )

    destname = "srcnames"
    add_deps_argument(
        subparser_show,
        destname,
        destname,
        help="source names (default: all)",
        nargs="*",
    )

    # sync
    subparser_sync = add_deps_parser(
        subparsers,
        "sync",
        description="Sync stored requirements to configured sources.",
    )

    destname = "srcnames"
    add_deps_argument(
        subparser_sync,
        destname,
        destname,
        help="source names (default: all)",
        nargs="*",
    )

    destname = "verify"
    add_deps_argument(
        subparser_sync,
        destname,
        f"--{destname}",
        help=(
            "Sync sources, but print diff and exits with code "
            f"{ExitCodes.SYNC_VERIFY_ERROR} if the sources were unsynced"
        ),
        action="store_true",
    )

    # eval
    subparser_eval = add_deps_parser(
        subparsers,
        "eval",
        description=(
            "Evaluate stored requirements according to PEP508 in current Python"
            " environment and print them to stdout in PEP508 format "
            "(by default) or specified one."
        ),
    )
    destname = "srcnames"
    add_deps_argument(
        subparser_eval,
        destname,
        destname,
        help="source names (default: all)",
        nargs="*",
    )

    destname = "depformat"
    add_deps_argument(
        subparser_eval,
        destname,
        f"--{destname}",
        help=(
            "format of dependency to print (default: PEP508 format). "
            "Supported substitutions: "
            "$name - project's name, "
            "$nname - PEP503 normalized project's name, "
            "$fextra - project's extras (expanded first with --depformatextra)."
        ),
    )
    destname = "depformatextra"
    add_deps_argument(
        subparser_eval,
        destname,
        f"--{destname}",
        help=(
            "format of extras to print (one extra of dependencies per line). "
            "Result is expanded in format specified by --depformat as $fextra "
            "(default: ''). Supported substitutions: $extra."
        ),
    )

    destname = "extra"
    add_deps_argument(
        subparser_eval,
        destname,
        f"--{destname}",
        dest=destname,
        help="PEP508 'extra' marker to evaluate with (default: None)",
    )

    destname = "excludes"
    add_deps_argument(
        subparser_eval,
        destname,
        "--exclude",
        dest=destname,
        nargs="+",
        default=[],
        help=(
            "regexes patterns, exclude requirement having PEP503-normalized "
            "name that matches one of these patterns (default: [])"
        ),
    )

    # add
    subparser_add = add_deps_parser(
        subparsers,
        "add",
        description=(
            "Configure source of Python dependencies "
            "(note: this doesn't sync the source). "
            "Supported sources: standardized formats like PEP517, PEP518 or "
            "core metadata are fully supported, while tool-specific formats "
            "like pip, tox or poetry have limited support."
        ),
    )

    destname = "srcname"
    add_deps_argument(
        subparser_add,
        destname,
        destname,
        help="source name",
    )

    destname = "srctype"
    add_deps_argument(
        subparser_add,
        destname,
        destname,
        choices=SUPPORTED_COLLECTORS,
        help="source type",
    )

    destname = "srcargs"
    add_deps_argument(
        subparser_add,
        destname,
        destname,
        nargs="*",
        help="specific configuration options for source (default: [])",
    )

    # delete
    subparser_delete = add_deps_parser(
        subparsers,
        "delete",
        description="Deconfigure source of Python dependencies",
    )

    destname = "srcname"
    add_deps_argument(
        subparser_delete,
        destname,
        destname,
        help="source name",
    )


def main_parser(prog):
    parser = MainArgumentParser(
        description=(
            "Build, check and install Python project from source tree in "
            "network-isolated environments"
        ),
        prog=prog,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="verbose output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=project_version,
    )

    subparsers = parser.add_subparsers(
        title="subcommands",
        help="--help for additional help",
        required=True,
    )

    # build subcli
    parser_build = subparsers.add_parser(
        "build",
        description=(
            "Build project from source tree in current Python environment "
            "according to PEP517. This doesn't trigger installation of "
            "project's build dependencies."
        ),
    )
    parser_build.add_argument(
        "srcdir",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="source directory (default: current working directory)",
    )
    parser_build.add_argument(
        "--outdir",
        "-o",
        type=Path,
        help="output directory for built wheel (default: {srcdir}/dist)",
    )
    parser_build.add_argument(
        "--sdist",
        action="store_true",
        help=(
            "build source distribution(sdist) instead of binary one(wheel). "
            "Note: installer supports only wheel format."
        ),
    )
    parser_build.add_argument(
        "--backend-config-settings",
        type=str,
        help=(
            "ad-hoc configuration for build backend as dumped JSON dictionary "
            "(default: None)"
        ),
    )
    parser_build.set_defaults(main=build)

    # install subcli
    parser_install = subparsers.add_parser(
        "install",
        description=(
            "Install project built in wheel format. "
            "This doesn't trigger installation of project's runtime "
            "dependencies."
        ),
    )
    parser_install.add_argument(
        "wheel",
        type=Path,
        nargs="?",
        default=None,
        help=(
            "wheel file to install "
            "(default: contructed as directory {cwd}/dist and wheel filename "
            f"read from {{cwd}}/dist/{WHEEL_TRACKER})"
        ),
    )
    parser_install.add_argument(
        "--destdir",
        "-d",
        default="/",
        type=Path,
        help=(
            "Wheel installation root will be prepended with destdir "
            "(default: /)"
        ),
    )
    parser_install.add_argument(
        "--installer",
        type=str,
        help=(
            "Name of installer to be recorded in dist-info/INSTALLER "
            "(default: None, INSTALLER will be omitted)"
        ),
    )
    parser_install.add_argument(
        "--no-strip-dist-info",
        dest="strip_dist_info",
        action="store_false",
        help=(
            "Don't strip dist-info. By default only METADATA and "
            "entry_points.txt files are allowed in dist-info directory. "
            "Note: RECORD is unconditionally filtered out. "
            "(default: False)"
        ),
    )
    parser_install.set_defaults(main=install)

    # run subcli
    parser_run = subparsers.add_parser(
        "run",
        description=(
            "Run command within Python virtual environment that has access to "
            "system and user site packages, their console scripts and installed"
            " built package)."
        ),
    )
    parser_run.add_argument(
        "--wheel",
        type=Path,
        default=None,
        help=(
            "wheel file to install "
            "(default: contructed as directory {cwd}/dist and wheel filename "
            f"read from {{cwd}}/dist/{WHEEL_TRACKER})"
        ),
    )
    parser_run.add_argument(
        "command",
        nargs="+",
        help=(
            "Command to run. "
            "For example, python -m pyproject_installer run -- pytest -vra"
        ),
    )
    parser_run.set_defaults(main=run)

    # deps subcli
    parser_deps = subparsers.add_parser(
        "deps",
        description=(
            "Collect PEP508 requirements from different sources, store and "
            "evaluate them in Python environment."
        ),
    )
    parser_deps.add_argument(
        "--depsconfig",
        type=Path,
        default=Path.cwd() / DEFAULT_CONFIG_NAME,
        help=(
            "configuration file to use "
            f"(default: {{cwd}}/{DEFAULT_CONFIG_NAME})"
        ),
    )

    deps_subparsers(parser_deps)
    return parser


def emit_less_than_warning(record):
    # nonzero if record should be logged
    return record.levelno < logging.WARNING


def setup_logging(verbose=False):
    # emit WARNING, ERROR and CRITICAL to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)

    # emit DEBUG and INFO to stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.addFilter(emit_less_than_warning)

    if verbose:
        log_level = logging.DEBUG
        log_format = "%(levelname)-8s : %(name)s : %(message)s"
    else:
        log_level = logging.INFO
        log_format = "%(levelname)-8s : %(message)s"

    logging.basicConfig(
        format=log_format,
        handlers=(stdout_handler, stderr_handler),
        level=log_level,
    )


def main(cli_args, prog=f"python -m {__package__}"):
    parser = main_parser(prog)
    args = parser.parse_args(cli_args)
    setup_logging(args.verbose)

    args.main(args, parser)


if __name__ == "__main__":
    main(sys.argv[1:])

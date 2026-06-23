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

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from . import __version__ as project_version
from .build_cmd import WHEEL_TRACKER, build_sdist, build_wheel
from .codes import ExitCodes
from .completion_cmd import SUPPORTED_SHELLS, completion_command
from .completion_cmd._autocomplete import run_autocomplete
from .deps_cmd import DEFAULT_CONFIG_NAME, SUPPORTED_COLLECTORS, deps_command
from .errors import (
    DepsNoCandidateError,
    DepsUnsyncedError,
    RunCommandEnvError,
    RunCommandError,
)
from .install_cmd import install_wheel
from .run_cmd import run_command

logger = logging.getLogger(Path(__file__).parent.name)


def build(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    srcdir = args.srcdir or Path.cwd()
    outdir = srcdir / "dist" if args.outdir is None else args.outdir
    try:
        config_settings = convert_config_settings(args.backend_config_settings)
    except (ValueError, TypeError) as e:
        parser.error(str(e))

    build_func = build_sdist if args.sdist else build_wheel
    build_func(
        srcdir,
        outdir=outdir,
        config=config_settings,
        verbose=args.verbose,
    )


def install(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        wheel = default_built_wheel() if args.wheel is None else args.wheel
    except ValueError as e:
        parser.error(str(e))

    install_wheel(
        wheel,
        destdir=args.destdir,
        installer=args.installer,
        strip_dist_info=args.strip_dist_info,
        rpm_filelist=args.rpm_filelist,
        force_site=args.force_site,
        exclude_paths=args.exclude_paths,
    )


def deps(
    action_name: str,
) -> Callable[[argparse.Namespace, argparse.ArgumentParser], None]:
    def wrapped(
        args: argparse.Namespace,
        parser: argparse.ArgumentParser,
    ) -> None:
        depsconfig = args.depsconfig or Path.cwd() / DEFAULT_CONFIG_NAME

        if (
            hasattr(args, "depformatextra")
            and args.depformatextra is not None
            and args.depformat is None
        ):
            parser.error("depformatextra option must be used with depformat")

        if hasattr(args, "candidates"):
            if args.sources is not None:
                if any((args.srcname, args.srctype, args.srcargs)):
                    parser.error("--sources takes no positional name/type/args")
                if args.candidates is not None:
                    parser.error(
                        "--sources is mutually exclusive with --candidates",
                    )
            else:
                if args.srcname is None:
                    parser.error(
                        "srcname positional is required with --candidates or "
                        "srctype",
                    )
                if all((args.candidates, args.srctype)):
                    parser.error(
                        "srctype positional is mutually exclusive "
                        "with --candidates",
                    )
                if not any((args.candidates, args.srctype)):
                    parser.error(
                        "either srctype or --candidates is required",
                    )

        if (
            hasattr(args, "sync")
            and not args.sync
            and any(
                (args.verify, args.verify_excludes, args.verify_ignore_version),
            )
        ):
            parser.error("--verify options on add must be used with --sync")

        if getattr(args, "verify_excludes", []) and not args.verify:
            parser.error("--verify-exclude option must be used with --verify")

        if getattr(args, "verify_ignore_version", False) and not args.verify:
            parser.error(
                "--verify-ignore-version option must be used with --verify",
            )

        kwargs = {x: getattr(args, x) for x in args.main_args}
        try:
            deps_command(action_name, depsconfig, **kwargs)
        except DepsUnsyncedError:
            # sync --verify error
            sys.exit(ExitCodes.SYNC_VERIFY_ERROR)
        except DepsNoCandidateError as e:
            # add --candidates with no candidate picked: report and exit
            logger.info("%s", e)
            sys.exit(ExitCodes.ADD_NO_CANDIDATE_ERROR)

    return wrapped


class RunnerResult:

    def __init__(
        self,
        status: ExitCodes,
        message: str | None,
        log: Callable[..., None],
        *,
        exception: BaseException | None = None,
        print_traceback: bool = False,
    ) -> None:
        self.status = status
        self.message = message
        self.log = log
        self.exception = exception
        self.print_traceback = print_traceback

    def report(self) -> None:
        status_msg = "Command's result: %(status)s"
        if self.message is not None:
            status_msg += " (%(message)s)"
        self.log(
            status_msg,
            {"status": self.status.name, "message": self.message},
        )

        if self.exception is not None:
            error_msg = "Command's error:"
            if self.print_traceback:
                self.log(error_msg, exc_info=self.exception)
            else:
                self.log(f"{error_msg} %s", str(self.exception))


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
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
    except BaseException as e:  # noqa: BLE001
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


def completion(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,  # noqa: ARG001  (handler convention)
) -> None:
    completion_command(args.shell)


def default_built_wheel() -> Path:
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
            "Missing wheel tracker, re-run build steps or specify wheel",
        ) from None

    return default_wheel_dir / wheel_filename


def parse_candidates(value: str) -> tuple[tuple[str, ...], ...]:
    """Parse a ;-separated --candidates list into (type, *args) tuples.

    Each ;-separated entry is split on whitespace into a type followed by its
    args, and blank entries are dropped; surrounding or repeated whitespace
    and a trailing ';' are therefore harmless (' pep735  test ;' is one
    ('pep735', 'test') entry). A malformed candidate list is rejected as a
    usage error rather than silently skipped: it is an error when no entries
    are left after dropping blanks (an empty, whitespace-only, or ';'-only
    value), or when an entry's type is not a known collector.
    """
    candidates = tuple(
        tuple(parts) for entry in value.split(";") if (parts := entry.split())
    )
    if not candidates:
        raise argparse.ArgumentTypeError(f"no candidates parsed from {value!r}")
    for srctype, *_ in candidates:
        if srctype not in SUPPORTED_COLLECTORS:
            raise argparse.ArgumentTypeError(
                f"invalid candidate type: {srctype!r} "
                f"(choose from {', '.join(SUPPORTED_COLLECTORS)})",
            )
    return candidates


def parse_sources(value: str) -> tuple[tuple[str, ...], ...]:
    """Parse a ;-separated --sources list into (name, type, *args) tuples.

    Each ;-separated entry is split on whitespace into a name, a type and
    the type's args, and blank entries are dropped; surrounding or repeated
    whitespace and a trailing ';' are therefore harmless. A malformed list
    is rejected as a usage error rather than silently skipped: it is an
    error when no entries are left after dropping blanks (an empty,
    whitespace-only, or ';'-only value), when an entry has fewer than two
    tokens (a name without a type), when an entry's type is not a known
    collector, or when a name is repeated within the list.
    """
    sources = tuple(
        tuple(parts) for entry in value.split(";") if (parts := entry.split())
    )
    if not sources:
        raise argparse.ArgumentTypeError(f"no sources parsed from {value!r}")
    seen: set[str] = set()
    for srcname, *rest in sources:
        if not rest:
            raise argparse.ArgumentTypeError(
                f"missing source type for {srcname!r}",
            )
        srctype = rest[0]
        if srctype not in SUPPORTED_COLLECTORS:
            raise argparse.ArgumentTypeError(
                f"invalid source type for {srcname!r}: {srctype!r} "
                f"(choose from {', '.join(SUPPORTED_COLLECTORS)})",
            )
        if srcname in seen:
            raise argparse.ArgumentTypeError(
                f"duplicate source name in a given list: {srcname!r}",
            )
        seen.add(srcname)
    return sources


def convert_config_settings(value: str | None) -> dict[str, Any] | None:
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
        raise TypeError(err_msg) from None

    return config_settings


class MainArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        """Overrides default exit code(2) with our"""
        try:
            super().error(message)
        except SystemExit as e:
            e.code = ExitCodes.WRONG_USAGE
            raise


def deps_subparsers(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(
        title="deps subcommands",
        help="--help for additional help",
        required=True,
    )

    def add_deps_argument(
        parser: argparse.ArgumentParser,
        destname: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        parser.add_argument(*args, **kwargs)
        destnames = parser.get_default("main_args") or []
        destnames.append(destname)
        parser.set_defaults(main_args=destnames)

    def add_deps_parser(
        parsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
        name: str,
        *args: Any,
        **kwargs: Any,
    ) -> argparse.ArgumentParser:
        parser = parsers.add_parser(
            name,
            *args,
            **kwargs,
        )
        parser.set_defaults(main=deps(name))
        return parser

    def add_sync_options(parser: argparse.ArgumentParser) -> None:
        """Add the verify options shared by `sync` and `add`.

        Registered in `main_args`, so they are forwarded to the action:
        `sync()` directly, or `add()` (which passes them on to its own
        sync when `--sync` is given).
        """
        destname = "verify"
        add_deps_argument(
            parser,
            destname,
            f"--{destname}",
            action="store_true",
            help=(
                "Sync sources, but print diff and exits with code "
                f"{ExitCodes.SYNC_VERIFY_ERROR} if the sources were unsynced"
            ),
        )

        destname = "verify_excludes"
        add_deps_argument(
            parser,
            destname,
            "--verify-exclude",
            dest=destname,
            nargs="+",
            default=[],
            help=(
                "Regex patterns; exclude from diff requirements whose "
                "PEP503-normalized names match one of the patterns "
                "(default: []). Requires --verify"
            ),
        )

        destname = "verify_ignore_version"
        add_deps_argument(
            parser,
            destname,
            "--verify-ignore-version",
            dest=destname,
            action="store_true",
            help=(
                "Exclude from diff requirements that differ only in their "
                "version specifier (same PEP503-normalized name, extras, "
                "marker and url). Requires --verify"
            ),
        )

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

    add_sync_options(subparser_sync)

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
        nargs="?",
        default=None,
        help="source name (omit when using --sources)",
    )

    destname = "srctype"
    add_deps_argument(
        subparser_add,
        destname,
        destname,
        nargs="?",
        default=None,
        choices=SUPPORTED_COLLECTORS,
        help="source type (omit when using --candidates or --sources)",
    )

    destname = "srcargs"
    add_deps_argument(
        subparser_add,
        destname,
        destname,
        nargs="*",
        help=(
            "specific configuration options for source "
            "(omit when using --candidates or --sources; default: [])"
        ),
    )

    destname = "candidates"
    add_deps_argument(
        subparser_add,
        destname,
        f"--{destname}",
        type=parse_candidates,
        default=None,
        metavar="LIST",
        help=(
            "Discover the source from an ordered, ';'-separated list of "
            "'<type> [args ...]' candidates: the first that collects "
            "successfully (its source is present, even with zero deps) is "
            "picked and supplies the recorded type/args. Mutually exclusive "
            "with the positional type/args; the source name is the only "
            "positional."
        ),
    )

    destname = "sources"
    add_deps_argument(
        subparser_add,
        destname,
        f"--{destname}",
        type=parse_sources,
        default=None,
        metavar="LIST",
        help=(
            "Add a batch of explicitly named sources from a ';'-separated "
            "list of '<name> <type> [args ...]' entries, each configured "
            "(and, with --sync, synced and verified) in turn. Takes no "
            "positional name/type/args and is mutually exclusive with "
            "--candidates."
        ),
    )

    destname = "reconfigure"
    add_deps_argument(
        subparser_add,
        destname,
        f"--{destname}",
        action="store_true",
        help=(
            "Reconfigure an already-configured source: keep it when the type "
            "and args are unchanged, replace it (dropping stored deps) when "
            "they differ. Without this, an existing source is an error."
        ),
    )

    destname = "sync"
    add_deps_argument(
        subparser_add,
        destname,
        f"--{destname}",
        action="store_true",
        help=(
            "After configuring the source, sync it in the same process "
            "(accepts the verify options below). Lets one add call replace "
            "a separate sync."
        ),
    )
    add_sync_options(subparser_add)

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


def main_parser(prog: str) -> MainArgumentParser:
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
    parser.add_argument(
        "-C",
        dest="cwd",
        default=None,
        metavar="DIR",
        help=(
            "change to DIR before running subcommand "
            "(default: current working directory)%(default).0s"
        ),
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
        default=None,
        metavar="DIR",
        help=(
            "source directory "
            "(default: current working directory)%(default).0s"
        ),
    )
    parser_build.add_argument(
        "--outdir",
        "-o",
        type=Path,
        metavar="DIR",
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
        metavar="FILE",
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
        metavar="DIR",
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
    parser_install.add_argument(
        "--rpm-filelist",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "write an RPM %%files-compatible filelist of installed "
            "files (plus computed .pyc paths) to PATH "
            "(default: None, filelist is not written)"
        ),
    )
    parser_install.add_argument(
        "--exclude-paths",
        dest="exclude_paths",
        nargs="+",
        default=[],
        metavar="PATTERN",
        help=(
            "fnmatch glob patterns. Files whose wheel-relative POSIX path "
            "matches any pattern are excluded from installation. "
            "(default: [])"
        ),
    )
    site_group = parser_install.add_mutually_exclusive_group()
    site_group.add_argument(
        "--platlib",
        dest="force_site",
        action="store_const",
        const="platlib",
        help=(
            "force install into platlib site-packages, overriding "
            "wheel's Root-Is-Purelib (also redirects .data/purelib "
            "content). Mutually exclusive with --purelib."
        ),
    )
    site_group.add_argument(
        "--purelib",
        dest="force_site",
        action="store_const",
        const="purelib",
        help=(
            "force install into purelib site-packages, overriding "
            "wheel's Root-Is-Purelib (also redirects .data/platlib "
            "content). Mutually exclusive with --platlib."
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
        metavar="FILE",
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
        default=None,
        metavar="FILE",
        help=(
            "configuration file to use "
            f"(default: {{cwd}}/{DEFAULT_CONFIG_NAME})%(default).0s"
        ),
    )

    deps_subparsers(parser_deps)

    # completion subcli
    parser_completion = subparsers.add_parser(
        "completion",
        description=(
            "Print a shell completion script for the requested shell to "
            "stdout."
        ),
    )
    parser_completion.add_argument(
        "shell",
        choices=SUPPORTED_SHELLS,
        help="shell to generate completion for",
    )
    parser_completion.set_defaults(main=completion)

    return parser


def setup_logging(*, verbose: bool = False) -> None:
    # emit all diagnostics to stderr; stdout is reserved for data output
    stderr_handler = logging.StreamHandler(sys.stderr)

    if verbose:
        log_level = logging.DEBUG
        log_format = "%(levelname)-8s : %(name)s : %(message)s"
    else:
        log_level = logging.INFO
        log_format = "%(levelname)-8s : %(message)s"

    logging.basicConfig(
        format=log_format,
        handlers=(stderr_handler,),
        level=log_level,
    )


def main(
    cli_args: Sequence[str],
    prog: str = f"python -m {__package__}",
) -> None:
    parser = main_parser(prog)
    args = parser.parse_args(cli_args)
    setup_logging(verbose=args.verbose)

    if args.cwd:
        try:
            os.chdir(args.cwd)
        except OSError as e:
            parser.error(f"-C: {e}")
        logger.debug("changed working directory to %s", args.cwd)

    args.main(args, parser)


def cli_entry() -> None:
    """Console-script entry; used by [project.scripts] = pyproject-installer.

    Checks for the ``_PYPROJECT_INSTALLER_COMPLETE`` sentinel set by the
    bash completion wrapper. When present, hands off to the
    autocomplete runtime (which reads ``COMP_WORDS`` / ``COMP_CWORD``
    from the environment, prints candidates, and exits) BEFORE normal
    argparse processing runs. Otherwise behaves as the standard entry
    point with ``prog="pyproject-installer"``.
    """
    if os.environ.get("_PYPROJECT_INSTALLER_COMPLETE") == "1":
        run_autocomplete(main_parser("pyproject-installer"))
    main(sys.argv[1:], prog="pyproject-installer")


if __name__ == "__main__":
    main(sys.argv[1:])

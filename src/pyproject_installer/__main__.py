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
import re
import sys

from packaging.markers import Marker
from packaging.requirements import Requirement

from . import __version__ as project_version
from .build_cmd import build_wheel, build_sdist, WHEEL_TRACKER
from .codes import ExitCodes
from .errors import RunCommandError, RunCommandEnvError
from .install_cmd import install_wheel
from .run_cmd import run_command
# from .deps_cmd import deps_command
from .deps_cmd.collectors import SUPPORTED_COLLECTORS, get_collector

logger = logging.getLogger(Path(__file__).parent.name)


# def wheel_build_deps(srcdir):
#     return call_hook(
#         python=sys.executable,
#         srcdir=srcdir,
#         verbose=False,
#         hook="get_requires_for_build_wheel",
#     )["result"]
# 
# 
# def build_deps(args, parser):
#     cwd = Path.cwd()
#     srcdir = validate_source_dir(cwd)
#     pyproject_file = srcdir / "pyproject.toml"
#     if args.wheel:
#         # logger.info("wheel deps: %s", wheel_build_deps(srcdir))
#         for dep in wheel_build_deps(srcdir):
#             print(dep)
#     else:
#         # logger.info("bootstrap deps: %s", bootstrap_build_deps(pyproject_file))
#         for dep in bootstrap_build_deps(pyproject_file):
#             print(dep)
class DepsSources:
    def __init__(self, depsfile):
        self.depsfile = depsfile
        # default config
        self.config = self.default_config()
        try:
            with self.depsfile.open(encoding="utf-8") as f:
                try:
                    self.config = json.load(f)
                except json.JSONDecodeError:
                    raise ValueError(
                        f"Invalid dependencies file: {f}"
                    ) from None
        except FileNotFoundError:
            # new file
            pass

    def default_config(self):
        return {"groups": {}}

    def add(self, group, srcname, srctype, srcargs, ignore):
        src_dict = {
            srcname: {
                "srctype": srctype,
                "srcargs": srcargs,
                "deps": [],
                "ignore": ignore,
            }
        }
        config_groups = self.config["groups"]
        if group not in config_groups:
            config_groups[group] = src_dict
        else:
            if srcname in config_groups[group]:
                raise ValueError(
                    f"'{srcname}' source already exists in '{group}' group"
                )
            config_groups[group].update(src_dict)
        with self.depsfile.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def delete(self, groups, srcname=None):
        # remove all groups by default
        if not groups and srcname is None:
            self.config = self.default_config()
        else:
            config_groups = self.config["groups"]
            missing_groups = set(groups) - config_groups.keys()
            if missing_groups:
                raise ValueError(
                    "Non existent groups: {}".format(', '.join(missing_groups))
                )
            selected_groups = config_groups.keys()
            if groups:
                selected_groups = selected_groups & set(groups)

            for group in selected_groups:
                if srcname is None:
                    del config_groups[group]
                else:
                    if srcname not in config_groups[group]:
                        raise ValueError(
                            f"Non existent srcname: {srcname} (group: {group})"
                        )
                    del config_groups[group][srcname]

        with self.depsfile.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)


    def show(self):
        out = json.dumps(self.config, indent=2) + "\n"
        sys.stdout.write(out)

    def sync(self):
        for group_name, group in self.config["groups"].items():
            for src_name, src in group.items():
                src["deps"] = []
                srctype = src["srctype"]
                collector_cls = get_collector(srctype)
                if collector_cls is None:
                    raise ValueError(
                        f"Unsupported collector type: {srctype} "
                        f"(group: {group_name}, src: {src_name})"
                    )
                regexes = [re.compile(x) for x in src["ignore"]]
                collector = collector_cls(*src["srcargs"])
                for req in collector.collect():
                    name = Requirement(req).name
                    if any(regex.match(name) for regex in regexes):
                        continue
                    src["deps"].append(req)
        with self.depsfile.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def eval(self, groups=[], namesonly=True):
        config_groups = self.config["groups"]
        missing_groups = set(groups) - config_groups.keys()
        if missing_groups:
            raise ValueError(
                "Non existent groups: {}".format(', '.join(missing_groups))
            )
        selected_groups = config_groups.keys()
        if groups:
            selected_groups = selected_groups & set(groups)
        deps = []
        for group in selected_groups:
            for src in config_groups[group].values():
                for req in src["deps"]:
                    parsed_req = Requirement(req)
                    marker = parsed_req.marker
                    if marker is not None:
                        marker_res = marker.evaluate()
                        if not marker_res:
                            continue
                    if namesonly:
                        deps.append(parsed_req.name)
                    else:
                        deps.append(req)
        for dep in deps:
            sys.stdout.write(dep + "\n")

    def verify(self, groups=[]):
        config_groups = self.config["groups"]
        missing_groups = set(groups) - config_groups.keys()
        if missing_groups:
            raise ValueError(
                "Non existent groups: {}".format(', '.join(missing_groups))
            )
        selected_groups = config_groups.keys()
        if groups:
            selected_groups = selected_groups & set(groups)
        for group in selected_groups:
            for src in config_groups[group].values():
                for req in src["deps"]:
                    parsed_req = Requirement(req)
                    marker = parsed_req.marker
                    if marker is not None:
                        marker_res = marker.evaluate()
                        if not marker_res:
                            continue
                    if namesonly:
                        deps.append(parsed_req.name)
                    else:
                        deps.append(req)


def deps_add(args, parser):
    DepsSources(args.depsfile).add(
        args.group,
        srcname=args.srcname,
        srctype=args.srctype,
        srcargs=args.srcargs,
        ignore=args.ignore,
    )


def deps_show(args, parser):
    DepsSources(args.depsfile).show()


def deps_sync(args, parser):
    DepsSources(args.depsfile).sync()


def deps_del(args, parser):
    DepsSources(args.depsfile).delete(args.groups, srcname=args.srcname)


def deps_eval(args, parser):
    DepsSources(args.depsfile).eval(args.groups, namesonly=args.namesonly)


def deps_verify(args, parser):
    DepsSources(args.depsfile).verify(args.groups)


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
    # add subcli
    subparser_add = subparsers.add_parser(
        "add",
        description=("TODO"),
    )
    subparser_add.add_argument(
        "--ignore",
        action="append",
        help=("TODO"),
    )
    subparser_add.add_argument(
        "group",
        type=str,
        help=("TODO"),
    )
    subparser_add.add_argument(
        "srcname",
        type=str,
        help=("TODO"),
    )
    subparser_add.add_argument(
        "srctype",
        type=str,  # TODO: validate type
        choices=SUPPORTED_COLLECTORS,
        help=("TODO"),
    )
    subparser_add.add_argument(
        "srcargs",
        nargs="*",
        help=("TODO"),
    )
    subparser_add.set_defaults(main=deps_add)

    # show subcli
    subparser_show = subparsers.add_parser(
        "show",
        description=("TODO"),
    )
    subparser_show.set_defaults(main=deps_show)

    # sync subcli
    subparser_sync = subparsers.add_parser(
        "sync",
        description=("TODO"),
    )
    subparser_sync.set_defaults(main=deps_sync)

    # del subcli
    subparser_del = subparsers.add_parser(
        "del",
        description=("TODO"),
    )
    subparser_del.add_argument(
        "groups",
        nargs="*",
        help=("TODO"),
    )
    subparser_del.add_argument(
        "--srcname",
        help="TODO",
    )
    subparser_del.set_defaults(main=deps_del)

    # eval subcli
    subparser_eval = subparsers.add_parser(
        "eval",
        description=("TODO"),
    )
    subparser_eval.add_argument(
        "groups",
        nargs="*",
        help=("TODO"),
    )
    subparser_eval.add_argument(
        "--no-namesonly",
        dest="namesonly",
        help="TODO",
        action="store_false"
    )
    subparser_eval.set_defaults(main=deps_eval)

    return subparsers


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
        description=("TODO"),
    )
    parser_deps.add_argument(
        "--depsfile",
        type=Path,
        default=Path.cwd() / "deps.json",
        help=("TODO"),
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

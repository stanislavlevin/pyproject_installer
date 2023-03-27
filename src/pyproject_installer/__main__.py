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
from collections.abc import MutableMapping
from collections import namedtuple
from copy import deepcopy
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
from .errors import RunCommandError, RunCommandEnvError, DepsUnsyncedError
from .install_cmd import install_wheel
from .run_cmd import run_command
# from .deps_cmd import deps_command
from .deps_cmd.collectors import SUPPORTED_COLLECTORS, get_collector

logger = logging.getLogger(Path(__file__).parent.name)


FILTER_TYPES = {"include", "exclude"}


class DepsSourcesConfig:
    def __init__(self, file, create=False):
        self.file = Path(file)
        self.read(create=create)

    def set_default(self):
        # default config
        self.config = {}
        self.sources = {}

    def read(self, create):
        if not self.file.is_file():
            if create:
                # new file
                self.set_default()
                return
            raise FileNotFoundError(f"Missing deps config file: {self.file}")

        with self.file.open(encoding="utf-8") as f:
            try:
                self.config = json.load(f)
            except json.JSONDecodeError:
                raise ValueError(
                    f"Invalid dependencies file: {f}"
                ) from None

    def save(self):
        # first parse the whole config
        json_config = json.dumps(self.config, indent=2) + "\n"
        self.file.write_text(json_config, encoding="utf-8")

    def show(self, srcnames=()):
        show_conf = {"sources": {}}
        for source_name in self.find_sources(srcnames):
            source = self.get_source(source_name)
            show_conf["sources"][source_name] = source
        self._show(show_conf)

    def _show(self, conf):
        out = json.dumps(conf, indent=2) + "\n"
        sys.stdout.write(out)

    @property
    def sources(self):
        return self.config["sources"]

    @sources.setter
    def sources(self, value):
        self.config["sources"] = deepcopy(value)

    def get_source(self, source):
        if source not in self.sources:
            raise ValueError(f"Source '{source}' doesn't exist")
        return self.sources[source]

    def add_source(self, srcname, srctype, srcargs):
        srcargs = tuple(srcargs)
        self.validate_collector(srctype, srcargs)

        if srcname in self.sources:
            raise ValueError(f"Source {srcname} already exists")
        self.sources[srcname] = {"srctype": srctype}
        if srcargs:
            self.sources[srcname]["srcargs"] = srcargs
        self.save()

    def del_source(self, source):
        if source not in self.sources:
            raise ValueError(f"Source {source} doesn't exist")
        del self.sources[source]
        self.save()

    def find_sources(self, srcnames=()):
        missing_sources = set(srcnames) - set(self.sources)
        if missing_sources:
            raise ValueError(
                "Non existent sources: {}".format(', '.join(missing_sources))
            )

        if srcnames:
            yield from srcnames
        else:
            yield from self.sources

    def validate_collector(self, srctype, srcargs):
        collector_cls = get_collector(srctype)
        if collector_cls is None:
            raise ValueError(f"Unsupported collector type: {srctype}")
        try:
            return collector_cls(*srcargs)
        except TypeError as e:
            raise ValueError(
                f"Unsupported arguments of collector {srctype}: {e!s}"
            ) from None

    def collect(self, srctype, srcargs):
        collector = self.validate_collector(srctype, srcargs)
        return collector.collect()

    def sync(self, srcnames=(), verify=False):
        """Sync sources

        With enabled `verify` DepsUnsyncedError is raised if sources are not
        synced and the diff is printed.
        """
        for srcname in self.find_sources(srcnames):
            source = self.get_source(srcname)
            diff = {srcname: {}}

            synced_deps = set(
                self.collect(
                    source["srctype"],
                    srcargs=source.get("srcargs", ()),
                )
            )

            stored_deps = set(source.get("deps", ()))

            if stored_deps == synced_deps:
                continue

            new_deps = synced_deps - stored_deps
            if new_deps:
                diff[srcname]["new_deps"] = tuple(new_deps)

            extra_deps = stored_deps - synced_deps
            if extra_deps:
                diff[srcname]["extra_deps"] = tuple(extra_deps)

            source["deps"] = sorted(synced_deps)
            self.save()

            if verify and diff[srcname]:
                out = json.dumps(diff, indent=2) + "\n"
                sys.stdout.write(out)
                raise DepsUnsyncedError

    def eval(self, srcnames=(), namesonly=True, extra=None, excludes=[]):
        deps = set()
        exclude_regexes = {re.compile(x) for x in excludes}

        for srcname in self.find_sources(srcnames):
            source = self.get_source(srcname)
            for req in source.get("deps", ()):
                parsed_req = Requirement(req)
                marker = parsed_req.marker
                if marker is not None:
                    env = None
                    if extra is not None:
                        env = {"extra": extra}
                    marker_res = marker.evaluate(env)
                    if not marker_res:
                        continue
                if any(reg.match(parsed_req.name) for reg in exclude_regexes):
                    continue
                if namesonly:
                    deps.add(parsed_req.name)
                else:
                    deps.add(req)

        for dep in deps:
            sys.stdout.write(dep + "\n")

def deps_del(args, parser):
    DepsSourcesConfig(args.depsfile).del_source(args.source)


def deps_add(args, parser):
    DepsSourcesConfig(args.depsfile, create=True).add_source(
        args.source, srctype=args.srctype, srcargs=args.srcargs
    )


def deps_eval(args, parser):
    DepsSourcesConfig(args.depsfile).eval(
        args.srcnames,
        namesonly=args.namesonly,
        extra=args.extra,
        excludes=args.excludes,
    )


def deps_show(args, parser):
    DepsSourcesConfig(args.depsfile).show(args.srcnames)


def deps_sync(args, parser):
    try:
        DepsSourcesConfig(args.depsfile).sync(args.srcnames, verify=args.verify)
    except DepsUnsyncedError:
        sys.exit(ExitCodes.FAILURE)


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
    # show subcli
    subparser_show = subparsers.add_parser(
        "show",
        description=("TODO"),
    )
    subparser_show.add_argument(
        "srcnames",
        type=str,
        help=("TODO"),
        nargs="*",
    )
    subparser_show.set_defaults(main=deps_show)


    # sync subcli
    subparser_sync = subparsers.add_parser(
        "sync",
        description=("TODO"),
    )
    subparser_sync.add_argument(
        "srcnames",
        nargs="*",
        help=("TODO"),
    )
    subparser_sync.add_argument(
        "--verify",
        help="TODO",
        action="store_true"
    )
    subparser_sync.set_defaults(main=deps_sync)

    # eval subcli
    subparser_eval = subparsers.add_parser(
        "eval",
        description=("TODO"),
    )
    subparser_eval.add_argument(
        "srcnames",
        nargs="*",
        help=("TODO"),
    )
    subparser_eval.add_argument(
        "--no-namesonly",
        dest="namesonly",
        help="TODO",
        action="store_false"
    )
    subparser_eval.add_argument(
        "--extra",
        help="TODO",
        type=str,
    )
    subparser_eval.add_argument(
        "--exclude",
        type=str,
        dest="excludes",
        nargs="+",
        default=[],
        help=("TODO"),
    )
    subparser_eval.set_defaults(main=deps_eval)

    # add subcli
    subparser_add = subparsers.add_parser(
        "add",
        description=("TODO"),
    )
    subparser_add.add_argument(
        "source",
        type=str,
        help=("TODO"),
    )
    subparser_add.add_argument(
        "srctype",
        type=str,
        choices=SUPPORTED_COLLECTORS,
        help=("TODO"),
    )
    subparser_add.add_argument(
        "srcargs",
        nargs="*",
        help=("TODO"),
    )
    subparser_add.set_defaults(main=deps_add)

    # del subcli
    subparser_del = subparsers.add_parser(
        "del",
        description=("TODO"),
    )
    subparser_del.add_argument(
        "source",
        type=str,
        help=("TODO"),
    )
    subparser_del.set_defaults(main=deps_del)


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
        default=Path.cwd() / "pyproject_deps.json",
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

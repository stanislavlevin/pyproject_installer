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
from .install_cmd import install_wheel


def build(args):
    outdir = args.srcdir / "dist" if args.outdir is None else args.outdir
    config_settings = convert_config_settings(args.backend_config_settings)

    build_func = build_sdist if args.sdist else build_wheel
    build_func(
        args.srcdir,
        outdir=outdir,
        config=config_settings,
        verbose=args.verbose,
    )


def install(args):
    wheel = default_built_wheel() if args.wheel is None else args.wheel
    install_wheel(
        wheel,
        destdir=args.destdir,
        installer=args.installer,
        strip_dist_info=args.strip_dist_info,
    )


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
            "Missing wheel tracker, re-run build steps or specify wheel to "
            "install"
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


def main_parser(prog):
    parser = argparse.ArgumentParser(
        description="Build and install Python project from source tree",
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
        description="valid subcommands",
        help="--help for additional help",
        required=True,
    )

    # build subcli
    parser_build = subparsers.add_parser("build")
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
    parser_install = subparsers.add_parser("install")
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

    args.main(args)


if __name__ == "__main__":
    main(sys.argv[1:])

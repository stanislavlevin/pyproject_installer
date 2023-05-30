from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import logging
import shutil
import sys

from ..lib.build_backend import backend_hook
from ..lib.wheel import WheelFile

__all__ = [
    "build_wheel",
    "build_sdist",
    "build_metadata",
    "WHEEL_TRACKER",
]

logger = logging.getLogger(__name__)

WHEEL_TRACKER = ".wheeltracker"

SUPPORTED_BUILD_HOOKS = (
    "build_wheel",
    "build_sdist",
    "prepare_metadata_for_build_wheel",
)


def build(srcdir, outdir, hook, config=None, verbose=False):
    logger.info("Source tree: %s", srcdir)
    logger.info("Output dir: %s", outdir)
    if config is not None:
        logger.info("Ad-hoc backend config: %r", config)

    if hook not in SUPPORTED_BUILD_HOOKS:
        raise ValueError(
            f"Unknown build hook: {hook}, "
            f"supported: {', '.join(SUPPORTED_BUILD_HOOKS)}"
        )

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(
            f"Unable to create path for outdir: {outdir}"
        ) from None
    outdir = outdir.resolve(strict=True)

    hook_result = backend_hook(
        python=sys.executable,
        srcdir=srcdir,
        verbose=verbose,
        hook=hook,
        hook_args=[(str(outdir),), {"config_settings": config}],
    )
    return hook_result["result"]


def build_wheel(srcdir, outdir, config=None, verbose=False):
    logger.info("Building wheel")
    wheel_filename = build(
        srcdir,
        outdir=outdir,
        hook="build_wheel",
        config=config,
        verbose=verbose,
    )

    # track result for wheel installer
    (outdir / WHEEL_TRACKER).write_text(f"{wheel_filename}\n", encoding="utf-8")
    logger.info("Built wheel: %s", wheel_filename)


def build_sdist(srcdir, outdir, config=None, verbose=False):
    logger.info("Building sdist")
    sdist_filename = build(
        srcdir,
        outdir=outdir,
        hook="build_sdist",
        config=config,
        verbose=verbose,
    )
    logger.info("Built sdist: %s", sdist_filename)


@contextmanager
def build_out_tmpdir(srcdir, hook, config, verbose):
    tmpdir = TemporaryDirectory()
    tmp_path = Path(tmpdir.name)
    try:
        result = build(
            srcdir,
            outdir=tmp_path,
            hook=hook,
            config=config,
            verbose=verbose,
        )
        yield result, tmp_path
    finally:
        tmpdir.cleanup()


def build_metadata(srcdir, outdir, config=None, verbose=False):
    """Build core metadata and put it on outdir"""
    logger.info("Building metadata")
    metadata_filename = "METADATA"
    metadata_path_dest = outdir / metadata_filename

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(
            f"Unable to create path for outdir: {outdir}"
        ) from None
    outdir = outdir.resolve(strict=True)

    hook = "prepare_metadata_for_build_wheel"
    logger.info("Building metadata with %s", hook)
    with build_out_tmpdir(srcdir, hook, config, verbose) as (
        distinfo_dir,
        tmp_path,
    ):
        if distinfo_dir != "":
            metadata_path_src = tmp_path / distinfo_dir / metadata_filename
            # Python 3.8 syntax
            with metadata_path_src.open(
                mode="rb"
            ) as fsrc, metadata_path_dest.open(mode="wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
            return metadata_filename

    # backend doesn't support optional prepare_metadata_for_build_wheel
    # fallback to build_wheel
    hook = "build_wheel"
    logger.info("Fallback to building metadata with %s", hook)
    with build_out_tmpdir(srcdir, hook, config, verbose) as (
        wheel_filename,
        tmp_path,
    ):
        wheel_path = tmp_path / wheel_filename
        with WheelFile(wheel_path) as whl:
            metadata_path_src = whl.dist_info / metadata_filename
            if sys.version_info > (3, 9):
                # Python3.9: zipfile.Path.open opens in text mode by default
                mode = "rb"
            else:
                # Python3.8: zipfile.Path.open supports only binary mode
                mode = "r"
            # Python 3.8 syntax
            with metadata_path_src.open(
                mode=mode
            ) as fsrc, metadata_path_dest.open(mode="wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
    return metadata_filename

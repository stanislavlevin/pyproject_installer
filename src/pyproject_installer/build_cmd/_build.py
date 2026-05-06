import logging
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, get_args

from ..lib.build_backend import backend_hook
from ..lib.wheel import WheelFile

__all__ = [
    "WHEEL_TRACKER",
    "build_metadata",
    "build_sdist",
    "build_wheel",
]

logger = logging.getLogger(__name__)

WHEEL_TRACKER = ".wheeltracker"


SUPPORTED_BUILD_HOOKS_TYPE = Literal[
    "build_wheel",
    "build_sdist",
    "prepare_metadata_for_build_wheel",
]


SUPPORTED_BUILD_HOOKS: tuple[str, ...] = get_args(SUPPORTED_BUILD_HOOKS_TYPE)


def build(
    srcdir: Path,
    *,
    outdir: Path,
    hook: SUPPORTED_BUILD_HOOKS_TYPE,
    config: dict[str, Any] | None = None,
    verbose: bool = False,
) -> str:
    logger.info("Source tree: %s", srcdir)
    logger.info("Output dir: %s", outdir)
    if config is not None:
        logger.info("Ad-hoc backend config: %r", config)

    if hook not in SUPPORTED_BUILD_HOOKS:
        raise ValueError(
            f"Unknown build hook: {hook}, "
            f"supported: {', '.join(SUPPORTED_BUILD_HOOKS)}",
        )

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(
            f"Unable to create path for outdir: {outdir}",
        ) from None
    outdir = outdir.resolve(strict=True)

    hook_result = backend_hook(
        python=sys.executable,
        srcdir=srcdir,
        verbose=verbose,
        hook=hook,
        hook_args=((str(outdir),), {"config_settings": config}),
    )
    return hook_result["result"]


def build_wheel(
    srcdir: Path,
    *,
    outdir: Path,
    config: dict[str, Any] | None = None,
    verbose: bool = False,
) -> None:
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


def build_sdist(
    srcdir: Path,
    *,
    outdir: Path,
    config: dict[str, Any] | None = None,
    verbose: bool = False,
) -> None:
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
def build_out_tmpdir(
    srcdir: Path,
    hook: SUPPORTED_BUILD_HOOKS_TYPE,
    config: dict[str, Any] | None,
    *,
    verbose: bool,
) -> Iterator[tuple[str, Path]]:
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


def build_metadata(
    srcdir: Path,
    *,
    outdir: Path,
    config: dict[str, Any] | None = None,
    verbose: bool = False,
) -> str:
    """Build core metadata and put it on outdir"""
    logger.info("Building metadata")
    metadata_filename = "METADATA"
    metadata_path_dest = outdir / metadata_filename

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(
            f"Unable to create path for outdir: {outdir}",
        ) from None
    outdir = outdir.resolve(strict=True)

    hook: SUPPORTED_BUILD_HOOKS_TYPE = "prepare_metadata_for_build_wheel"
    logger.info("Building metadata with %s", hook)
    with (
        build_out_tmpdir(srcdir, hook, config, verbose=verbose) as (
            distinfo_dir,
            tmp_path,
        ),
    ):
        if distinfo_dir:
            metadata_path_src = tmp_path / distinfo_dir / metadata_filename
            with (
                metadata_path_src.open(mode="rb") as fsrc,
                metadata_path_dest.open(mode="wb") as fdst,
            ):
                shutil.copyfileobj(fsrc, fdst)
            return metadata_filename

    # backend doesn't support optional prepare_metadata_for_build_wheel
    # fallback to build_wheel
    hook = "build_wheel"
    logger.info("Fallback to building metadata with %s", hook)
    with (
        build_out_tmpdir(srcdir, hook, config, verbose=verbose) as (
            wheel_filename,
            tmp_path,
        ),
    ):
        wheel_path = tmp_path / wheel_filename
        with WheelFile(wheel_path) as whl:
            metadata_path_zip_src = whl.dist_info / metadata_filename
            with (
                metadata_path_zip_src.open(mode="rb") as fsrc,
                metadata_path_dest.open(mode="wb") as fdst,
            ):
                shutil.copyfileobj(fsrc, fdst)
    return metadata_filename

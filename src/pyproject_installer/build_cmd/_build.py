import logging
import sys

from ..lib.build_backend import backend_hook

__all__ = [
    "build_wheel",
    "build_sdist",
    "WHEEL_TRACKER",
]

logger = logging.getLogger(__name__)

WHEEL_TRACKER = ".wheeltracker"

SUPPORTED_BUILD_HOOKS = ("build_wheel", "build_sdist")


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

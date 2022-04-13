from contextlib import suppress
from pathlib import Path
import json
import logging
import os
import subprocess
import sys
import threading

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from ._vendor import tomli as tomllib


__all__ = [
    "build_wheel",
    "build_sdist",
    "WHEEL_TRACKER",
]

logger = logging.getLogger(__name__)

BACKEND_CALLER = Path(__file__).parent / "helper" / "backend_caller.py"
WHEEL_TRACKER = ".wheeltracker"

SUPPORTED_BUILD_HOOKS = ("build_wheel", "build_sdist")


class RaisingThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exc = None

    def run(self, *args, **kwargs):
        self._exc = None
        try:
            super().run(*args, **kwargs)
        except BaseException as e:
            self._exc = e

    def join(self, *args, **kwargs):
        super().join(*args, **kwargs)
        if self._exc:
            raise self._exc


def parse_build_system_spec(srcdir):
    """
    PEP517 spec: https://peps.python.org/pep-0517/#source-trees.

    If the pyproject.toml file is absent, or the build-backend key is
    missing, the source tree is not using this specification, and tools
    should revert to the legacy behaviour of running setup.py (either
    directly, or by implicitly invoking the setuptools.build_meta:__legacy__
    backend).


    PEP518 spec: https://peps.python.org/pep-0518/#build-system-table.

    The [build-system] table is used to store build-related data. Initially
    only one key of the table will be valid and is mandatory for the table:
    requires.

    Tools should not require the existence of the [build-system] table.
    If the file exists but is lacking the [build-system] table
    then the default values as specified above should be used. If the table
    is specified but is missing required fields then the tool should
    consider it an error.
    """
    logger.debug("Checking for PEP517 spec")
    pyproject_file = srcdir / "pyproject.toml"
    default_build_system = {
        "build-backend": "setuptools.build_meta:__legacy__",
        "requires": ["setuptools", "wheel"],
    }

    if not pyproject_file.is_file():
        logger.info("pyproject.toml was not found, using defaults")
        return default_build_system

    logger.debug("Parsing configuration file: %s", pyproject_file)
    with pyproject_file.open("rb") as f:
        try:
            pyproject_data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            raise ValueError("Invalid pyproject.toml") from None

    build_system = pyproject_data.get("build-system")
    if build_system is None:
        logger.info("build-system was not found, using defaults")
        return default_build_system

    try:
        requires = build_system["requires"]
    except KeyError:
        raise KeyError(
            f"Missing mandatory build-system.requires in {pyproject_file}"
        ) from None

    # requires: list of strings
    if not isinstance(requires, list):
        raise TypeError(
            f"requires should be a list of strings, given: {requires!r}"
        )

    for req in requires:
        if not isinstance(req, str):
            raise TypeError(
                f"requires should be a list of strings, given: {requires!r}"
            )

    try:
        build_backend = build_system["build-backend"]
    except KeyError:
        logger.info(
            "build-system.build-backend was not found, using default backend"
        )
        # preserve 'requires' according to PEP518
        return {
            "build-backend": default_build_system["build-backend"],
            "requires": requires,
        }

    # build-backend: a string naming a Python object
    if not isinstance(build_backend, str):
        raise TypeError(
            f"build-backend should be a string, given: {build_backend!r}"
        )

    bs = {
        "build-backend": build_backend,
        "requires": requires,
    }

    # optional keys
    try:
        backend_path = build_system["backend-path"]
    except KeyError:
        pass
    else:
        # PEP517 in-tree build backends: Directories in backend-path are
        # interpreted as relative to the project root, and MUST refer to a
        # location within the source tree (after relative paths and symbolic
        # links have been resolved).
        # The first restriction is to ensure that source trees remain
        # self-contained, and cannot refer to locations outside of the source
        # tree. Frontends SHOULD check this condition (typically by resolving
        # the location to an absolute path and resolving symbolic links, and
        # then checking it against the project root), and fail with an error
        # message if it is violated.

        # backend-path: list of directories
        if not isinstance(backend_path, list):
            raise TypeError(
                "backend-path should be a list of strings, "
                f"given: {backend_path!r}"
            )

        for path in backend_path:
            if not isinstance(path, str):
                raise TypeError(
                    "backend-path should be a list of strings, "
                    f"given: {backend_path!r}"
                )
            path_p = Path(path)
            if path_p.is_absolute():
                raise ValueError(
                    f"Invalid absolute backend-path: {path}, "
                    "should be relative to source root"
                )

            try:
                bep = (srcdir / path_p).resolve(strict=True)
            except (FileNotFoundError, RuntimeError):
                raise ValueError(
                    f"Unable to resolve backend-path: {path}"
                ) from None
            try:
                bep.relative_to(srcdir)
            except ValueError:
                raise ValueError(
                    "Invalid backend-path, "
                    "path should refer to location within source tree, "
                    f"given {path} is resolved to {bep}"
                ) from None

        bs["backend-path"] = backend_path

    return bs


def make_args(python, result_fd, verbose, build_system, hook, hook_args):
    args = [
        python,
        BACKEND_CALLER,
        "--result-fd",
        str(result_fd),
    ]
    if verbose:
        args.append("--verbose")

    args.append(build_system["build-backend"])
    # optional keys
    if "backend-path" in build_system:
        for bep in build_system["backend-path"]:
            args.extend(["--backend-path", bep])

    args.extend([hook, "--hook-args", json.dumps(hook_args)])
    return args


def validate_source_dir(srcdir):
    """Resolve and validate source path"""
    logger.debug("Validating source path")
    try:
        srcdir = srcdir.resolve(strict=True)
    except (FileNotFoundError, RuntimeError):
        raise ValueError(
            f"Unable to resolve path for source directory: {srcdir}"
        ) from None

    if not srcdir.is_dir():
        raise ValueError("Source path should be a directory")

    if (
        not (srcdir / "pyproject.toml").is_file()
        and not (srcdir / "setup.py").is_file()
    ):
        # not a Python project
        raise ValueError("Required either pyproject.toml or setup.py")

    return srcdir


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
    srcdir = validate_source_dir(srcdir)

    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(
            f"Unable to create path for outdir: {outdir}"
        ) from None
    outdir = outdir.resolve(strict=True)

    hook_result = call_hook(
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


def call_hook(python, srcdir, verbose, hook, hook_args=[(), {}]):
    build_system = parse_build_system_spec(srcdir)
    read = b""

    rfd, wfd = os.pipe()

    try:

        def read_from_pipe():
            nonlocal read
            buffer_size = 2048
            while True:
                read_chunk = os.read(rfd, buffer_size)
                if not read_chunk:
                    break
                read += read_chunk

        t = RaisingThread(target=read_from_pipe)
        t.start()
        capture_output = not verbose

        try:
            args = make_args(
                python=python,
                result_fd=wfd,
                verbose=verbose,
                build_system=build_system,
                hook=hook,
                hook_args=hook_args,
            )
            subprocess.run(
                args=args,
                stdin=None,
                capture_output=capture_output,
                cwd=srcdir,
                check=True,
                pass_fds=(wfd,),
            )
        except subprocess.CalledProcessError as e:
            err_msg = f"{hook} failed"
            if capture_output:
                err_msg += (
                    "\n\nCaptured stdout:\n\n{stdout}"
                    "\n\nCaptured stderr:\n\n{stderr}"
                ).format(
                    stdout=e.stdout.decode(encoding="utf-8", errors="replace"),
                    stderr=e.stderr.decode(encoding="utf-8", errors="replace"),
                )
            raise RuntimeError(err_msg) from None

        os.close(wfd)
        try:
            t.join()
        except BaseException as e:
            raise RuntimeError(str(e)) from e
        os.close(rfd)
        try:
            result = json.loads(read.decode("utf-8"))
        except json.JSONDecodeError:
            raise RuntimeError(
                "Received invalid JSON data from backend helper: "
                f"{read.decode('utf-8')!r}"
            ) from None
    finally:
        # already closed
        with suppress(OSError):
            os.close(wfd)
            os.close(rfd)

    return result

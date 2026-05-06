"""
Intended to be run in subprocess to call build backend's hooks.
Must not have dependencies other than stdlib.
"""

import argparse
import json
import logging
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, TypedDict, overload

logger = logging.getLogger(Path(__file__).name)

# hook name: fallback (None - mandatory hook)
HookResultType = list[str] | str | None
BuildWheelResultType = str
BuildSdistResultType = str
RequiresBuildWheelResultType = list[str]
RequiresBuildSdistResultType = list[str]
PrepareMetadataResultType = str

SUPPORTED_HOOKS: dict[str, HookResultType] = {
    "build_wheel": None,
    "build_sdist": None,
    "get_requires_for_build_wheel": [],
    "get_requires_for_build_sdist": [],
    # PEP517 doesn't specify default value
    "prepare_metadata_for_build_wheel": "",
}


class BackendBuildWheelType(TypedDict):
    result: BuildWheelResultType


class BackendBuildSdistType(TypedDict):
    result: BuildSdistResultType


class BackendRequiresBuildWheelType(TypedDict):
    result: RequiresBuildWheelResultType


class BackendRequiresBuildSdistType(TypedDict):
    result: RequiresBuildSdistResultType


class BackendPrepareMetadataType(TypedDict):
    result: PrepareMetadataResultType


BackendResultType = (
    BackendBuildWheelType
    | BackendBuildSdistType
    | BackendRequiresBuildWheelType
    | BackendRequiresBuildSdistType
    | BackendPrepareMetadataType
)


def backend_object(backend: str, backend_path: list[str] | None = None) -> Any:
    if backend_path is not None:
        # Projects can specify that their backend code is hosted in-tree by
        # including the backend-path key in pyproject.toml. This key contains a
        # list of directories, which the frontend will add to the start of
        # sys.path when loading the backend, and running the backend hooks.
        sys.path[:0] = backend_path

    module_path, _, object_path = backend.partition(":")
    backend_obj = import_module(module_path)

    if backend_path is not None:
        # The backend code MUST be loaded from one of the directories specified
        # in backend-path (i.e., it is not permitted to specify backend-path and
        # not have in-tree backend code).
        # Front ends MAY enforce this check, but are not required to. Doing so
        # would typically involve checking the backend's __file__ attribute
        # against the locations in backend-path.
        backend_file = backend_obj.__file__
        if backend_file is None:
            raise ValueError(
                f"Backend {backend!r} has no __file__ location; "
                f"cannot enforce backend-path",
            )
        actual_bep = Path(backend_file).resolve(strict=True)
        for path in backend_path:
            expected_bep = Path(path).resolve(strict=True)

            try:
                actual_bep.relative_to(expected_bep)
            except ValueError:
                pass
            else:
                break
        else:
            raise ValueError(
                "backend code must be loaded from one of backend-path, "
                f"but loaded from {actual_bep}",
            )

    # arbitrary depth of attrs
    if object_path:
        for subattr in object_path.split("."):
            backend_obj = getattr(backend_obj, subattr)

    return backend_obj


def write_result(result_fd: int, result: str) -> None:
    payload = result.encode("utf-8")
    sent = 0
    while sent != len(payload):
        sent += os.write(result_fd, payload[sent:])


def main_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PEP517 hook caller in subprocess",
        prog=prog,
    )
    parser.add_argument(
        "backend",
        type=str,
        help="build backend endpoint",
    )
    parser.add_argument(
        "--backend-path",
        action="append",
        type=str,
        help="custom in-tree build backend path",
    )
    parser.add_argument(
        "--result-fd",
        type=int,
        help="File descriptor to write a result back",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="verbose output",
    )
    parser.add_argument(
        "hook_name",
        choices=SUPPORTED_HOOKS,
        type=str,
        help="Hook name",
    )
    parser.add_argument(
        "--hook-args",
        type=str,
        help="Hook arguments as dumped JSON in [args, kwargs] format",
    )
    return parser


def emit_less_than_warning(record: logging.LogRecord) -> bool:
    # nonzero if record should be logged
    return record.levelno < logging.WARNING


def setup_logging(*, verbose: bool = False) -> None:
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


@overload
def call_hook(
    backend: str,
    backend_path: list[str] | None,
    hook: Literal["build_wheel"],
    hook_args: list[str],
    hook_kwargs: dict[str, Any],
) -> BuildWheelResultType: ...


@overload
def call_hook(
    backend: str,
    backend_path: list[str] | None,
    hook: Literal["build_sdist"],
    hook_args: list[str],
    hook_kwargs: dict[str, Any],
) -> BuildSdistResultType: ...


@overload
def call_hook(
    backend: str,
    backend_path: list[str] | None,
    hook: Literal["get_requires_for_build_wheel"],
    hook_args: list[str],
    hook_kwargs: dict[str, Any],
) -> RequiresBuildWheelResultType: ...


@overload
def call_hook(
    backend: str,
    backend_path: list[str] | None,
    hook: Literal["get_requires_for_build_sdist"],
    hook_args: list[str],
    hook_kwargs: dict[str, Any],
) -> RequiresBuildSdistResultType: ...


@overload
def call_hook(
    backend: str,
    backend_path: list[str] | None,
    hook: Literal["prepare_metadata_for_build_wheel"],
    hook_args: list[str],
    hook_kwargs: dict[str, Any],
) -> PrepareMetadataResultType: ...


def call_hook(
    backend: str,
    backend_path: list[str] | None,
    hook: str,
    hook_args: list[str],
    hook_kwargs: dict[str, Any],
) -> HookResultType:
    hook_obj = backend_object(backend, backend_path=backend_path)
    try:
        hook_func = getattr(hook_obj, hook)
    except AttributeError:
        fallback = SUPPORTED_HOOKS[hook]
        if fallback is None:
            raise ValueError(
                f"Missing mandatory hook in build backend: {hook}",
            ) from None
        return fallback

    result: HookResultType = hook_func(*hook_args, **hook_kwargs)
    return result


def main(cli_args: list[str], prog: str = Path(__file__).name) -> None:
    parser = main_parser(prog)
    args = parser.parse_args(cli_args)
    setup_logging(verbose=args.verbose)

    backend = args.backend
    backend_path = args.backend_path
    hook = args.hook_name
    result_fd = args.result_fd
    if args.hook_args is not None:
        try:
            hook_args, hook_kwargs = json.loads(args.hook_args)
        except json.JSONDecodeError:
            raise ValueError(
                f"Invalid hook args: {args.hook_args!r}, "
                "should be a dumped JSON",
            ) from None
    else:
        hook_args, hook_kwargs = [[], {}]

    logger.info("Calling hook %s in subprocess", hook)
    logger.info("Build backend: %s", backend)
    if backend_path is not None:
        logger.info("In-tree backend paths: %s", ", ".join(backend_path))
    if hook_args:
        logger.info("Hook args: %r", hook_args)
    if hook_kwargs:
        logger.info("Hook kwargs: %r", hook_kwargs)

    hook_result = call_hook(
        backend,
        backend_path=backend_path,
        hook=hook,
        hook_args=hook_args,
        hook_kwargs=hook_kwargs,
    )

    if result_fd is not None:
        write_result(result_fd, json.dumps({"result": hook_result}))


if __name__ == "__main__":
    main(sys.argv[1:])

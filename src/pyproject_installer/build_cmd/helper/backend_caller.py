"""
Intended to be run in subprocess to call build backend's hooks.
Must not have dependencies other than stdlib.
"""
from importlib import import_module
from pathlib import Path
import argparse
import logging
import os
import json
import sys


logger = logging.getLogger(Path(__file__).name)

# hook name: fallback (None - mandatory hook)
SUPPORTED_HOOKS = {
    "build_wheel": None,
    "build_sdist": None,
    "get_requires_for_build_wheel": [],
    "get_requires_for_build_sdist": [],
}


def backend_object(backend, backend_path=None):
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
        actual_bep = Path(backend_obj.__file__).resolve(strict=True)
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
                f"but loaded from {actual_bep}"
            )

    # arbitrary depth of attrs
    if object_path:
        for subattr in object_path.split("."):
            backend_obj = getattr(backend_obj, subattr)

    return backend_obj


def write_result(result_fd, result):
    result = result.encode("utf-8")
    sent = 0
    while sent != len(result):
        sent += os.write(result_fd, result[sent:])


def main_parser(prog):
    parser = argparse.ArgumentParser(
        description="PEP517 hook caller in subprocess", prog=prog
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


def call_hook(backend, backend_path, hook, hook_args, hook_kwargs):
    hook_obj = backend_object(backend, backend_path=backend_path)
    try:
        hook_func = getattr(hook_obj, hook)
    except AttributeError:
        fallback = SUPPORTED_HOOKS[hook]
        if fallback is None:
            raise ValueError(f"Missing mandatory hook in build backend: {hook}")
        return fallback

    return hook_func(*hook_args, **hook_kwargs)


def main(cli_args, prog=Path(__file__).name):
    parser = main_parser(prog)
    args = parser.parse_args(cli_args)
    setup_logging(args.verbose)

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
                "should be a dumped JSON"
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

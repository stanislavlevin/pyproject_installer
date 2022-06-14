from contextlib import suppress
import logging
import json
import textwrap
import subprocess
import sys

import pytest

from pyproject_installer.build_cmd.helper import backend_caller


@pytest.fixture
def project(tmpdir, monkeypatch):
    project_path = tmpdir / "project"
    project_path.mkdir()
    monkeypatch.chdir(project_path)
    return project_path


@pytest.fixture
def build_backend_src(tmpdir):
    def _build_backend_src(be_module="be", be_object=None, hooks=None):
        backend_path = tmpdir / be_module
        backend_path.mkdir()
        module_text = textwrap.dedent(
            """\
            def _build_wheel(
                wheel_directory, metadata_directory=None, config_settings=None
            ):
                return "foo-1.0.whl"

            def _build_sdist(sdist_directory, config_settings=None):
                return "foo-1.0.tar.gz"

            def _get_requires_for_build_wheel(config_settings=None):
                return ["build_wheel_dep"]

            def _get_requires_for_build_sdist(config_settings=None):
                return ["build_sdist_dep"]
            """
        )
        if hooks is None:
            hooks = list(backend_caller.SUPPORTED_HOOKS.keys())

        if be_object is None:
            for hook in hooks:
                module_text += f"{hook} = _{hook}\n"
        else:
            module_text += "class A:\n    '''docstring'''\n"
            for hook in hooks:
                module_text += f"    {hook} = _{hook}\n"
            module_text += f"{be_object} = A()\n"

        (backend_path / "__init__.py").write_text(module_text)
        return backend_path

    return _build_backend_src


@pytest.fixture
def build_backend(project, build_backend_src, monkeypatch):
    module = None

    def _build_backend(*args, **kwargs):
        nonlocal module
        module = args[0] if args else kwargs["be_module"]
        backend_path = build_backend_src(*args, **kwargs)
        monkeypatch.syspath_prepend(backend_path.parent)
        return backend_path

    yield _build_backend
    with suppress(KeyError):
        del sys.modules[module]


@pytest.fixture
def in_tree_build_backend(build_backend_src, monkeypatch):
    module = None
    sys_path_orig = sys.path[:]

    def _in_tree_build_backend(*args, **kwargs):
        nonlocal module
        module = args[0] if args else kwargs["be_module"]
        backend_path = build_backend_src(*args, **kwargs)
        monkeypatch.chdir(backend_path.parent)
        return backend_path

    yield _in_tree_build_backend
    sys.path[:] = sys_path_orig
    with suppress(KeyError):
        del sys.modules[module]


@pytest.fixture
def mock_call_hook(mocker):
    return mocker.patch.object(backend_caller, "call_hook")


@pytest.fixture
def build_backend_path():
    path = "."
    yield path
    del sys.path_importer_cache[path]


def test_help():
    result = subprocess.run(
        args=[
            sys.executable,
            "-m",
            "pyproject_installer.build_cmd.helper.backend_caller",
            "--help",
        ],
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout.rstrip().startswith(b"usage: backend_caller.py ")
    assert result.stderr == b""


def test_invalid_hook_choice():
    invalid_hook = "invalid_hook_name"
    result = subprocess.run(
        args=[
            sys.executable,
            "-m",
            "pyproject_installer.build_cmd.helper.backend_caller",
            "be",
            invalid_hook,
        ],
        capture_output=True,
    )
    expected_err_msg = (
        "argument hook_name: invalid choice: '{}' (choose from {})\n"
    ).format(
        invalid_hook,
        ", ".join([f"{x!r}" for x in backend_caller.SUPPORTED_HOOKS]),
    )

    assert result.returncode != 0
    assert expected_err_msg.encode("utf-8") in result.stderr
    assert result.stdout == b""


def test_invalid_hook_args():
    with pytest.raises(
        ValueError,
        match="Invalid hook args: 'invalid_hook_args', should be a dumped JSON",
    ):
        backend_caller.main(
            ["be", "build_wheel", "--hook-args", "invalid_hook_args"]
        )


@pytest.mark.parametrize(
    "verbose, logging_kwargs",
    (
        (False, ("%(levelname)-8s : %(message)s", logging.INFO)),
        (True, ("%(levelname)-8s : %(name)s : %(message)s", logging.DEBUG)),
    ),
    ids=["default", "verbose"],
)
def test_logging(verbose, logging_kwargs, mocker, mock_call_hook):
    """Check format and level of logging depending on verbosity"""
    m = mocker.patch.object(backend_caller.logging, "basicConfig")
    build_args = [
        "foo",
        "build_wheel",
        "--hook-args",
        json.dumps([["/bar"], {}]),
    ]
    if verbose:
        build_args.append("--verbose")

    backend_caller.main(build_args)

    expected_format, expected_level = logging_kwargs
    expected_handlers = (
        (logging.StreamHandler, logging.NOTSET, sys.stdout),
        (logging.StreamHandler, logging.WARNING, sys.stderr),
    )
    m.assert_called_once()
    # args
    assert m.call_args.args == ()
    # kwargs
    kwargs = m.call_args.kwargs
    assert len(kwargs) == 3
    ## format
    assert kwargs["format"] == expected_format
    ## root logger level
    assert kwargs["level"] == expected_level
    ## handlers
    actual_handlers = kwargs["handlers"]
    assert len(actual_handlers) == 2
    for expected_handler, actual_handler in zip(
        expected_handlers, actual_handlers
    ):
        expected_type, expected_level, expected_stream = expected_handler
        assert isinstance(actual_handler, expected_type)
        assert actual_handler.level == expected_level
        assert actual_handler.stream == expected_stream


@pytest.mark.parametrize(
    "level,destination",
    (
        ("critical", "stderr"),
        ("error", "stderr"),
        ("warning", "stderr"),
        ("info", "stdout"),
        ("debug", "stdout"),
    ),
)
def test_logging_destination(level, destination):
    code = textwrap.dedent(
        f"""\
            from pyproject_installer.build_cmd.helper import backend_caller

            backend_caller.setup_logging(verbose=True)
            backend_caller.logger.{level}("{level}")
        """
    )
    cmd = [sys.executable, "-c", code]
    result = subprocess.run(args=cmd, capture_output=True)
    assert result.returncode == 0
    if destination == "stderr":
        log_out = result.stderr
        log_no_out = result.stdout
    else:
        log_out = result.stdout
        log_no_out = result.stderr
    assert log_out.endswith(b" " + level.encode("utf-8") + b"\n")
    assert log_no_out == b""


def test_cli_hook_no_args(mock_call_hook):
    hook_args = ["be", "build_wheel"]
    expected_args = ("be",)
    expected_kwargs = {
        "backend_path": None,
        "hook": "build_wheel",
        "hook_args": [],
        "hook_kwargs": {},
    }
    backend_caller.main(hook_args)
    mock_call_hook.assert_called_once_with(*expected_args, **expected_kwargs)


def test_cli_hook_pos_args_only(mock_call_hook):
    build_args = [
        "be",
        "build_wheel",
        "--hook-args",
        json.dumps([["/wheeldir", {"key": "value"}, "/metadir"], {}]),
    ]
    expected_args = ("be",)
    expected_kwargs = {
        "backend_path": None,
        "hook": "build_wheel",
        "hook_args": ["/wheeldir", {"key": "value"}, "/metadir"],
        "hook_kwargs": {},
    }
    backend_caller.main(build_args)
    mock_call_hook.assert_called_once_with(*expected_args, **expected_kwargs)


def test_cli_hook_kwargs_only(mock_call_hook):
    build_args = [
        "be",
        "build_wheel",
        "--hook-args",
        json.dumps(
            [
                [],
                {
                    "wheel_directory": "/wheeldir",
                    "metadata_directory": "/metadir",
                    "config": {"key": "value"},
                },
            ],
        ),
    ]
    expected_args = ("be",)
    expected_kwargs = {
        "backend_path": None,
        "hook": "build_wheel",
        "hook_args": [],
        "hook_kwargs": {
            "wheel_directory": "/wheeldir",
            "metadata_directory": "/metadir",
            "config": {"key": "value"},
        },
    }
    backend_caller.main(build_args)
    mock_call_hook.assert_called_once_with(*expected_args, **expected_kwargs)


def test_cli_hook_args_and_kwargs(mock_call_hook):
    build_args = [
        "be",
        "build_wheel",
        "--hook-args",
        json.dumps(
            [
                ["/wheeldir"],
                {
                    "metadata_directory": "/metadir",
                    "config": {"key": "value"},
                },
            ],
        ),
    ]
    expected_args = ("be",)
    expected_kwargs = {
        "backend_path": None,
        "hook": "build_wheel",
        "hook_args": ["/wheeldir"],
        "hook_kwargs": {
            "metadata_directory": "/metadir",
            "config": {"key": "value"},
        },
    }
    backend_caller.main(build_args)
    mock_call_hook.assert_called_once_with(*expected_args, **expected_kwargs)


def test_cli_hook_backend_path(mock_call_hook):
    hook_args = ["be", "build_wheel", "--backend-path", "bep"]
    expected_args = ("be",)
    expected_kwargs = {
        "backend_path": ["bep"],
        "hook": "build_wheel",
        "hook_args": [],
        "hook_kwargs": {},
    }
    backend_caller.main(hook_args)
    mock_call_hook.assert_called_once_with(*expected_args, **expected_kwargs)


def test_cli_hook_backend_paths(mock_call_hook):
    hook_args = [
        "be",
        "build_wheel",
        "--backend-path",
        "bep1",
        "--backend-path",
        "bep2",
    ]
    expected_args = ("be",)
    expected_kwargs = {
        "backend_path": ["bep1", "bep2"],
        "hook": "build_wheel",
        "hook_args": [],
        "hook_kwargs": {},
    }
    backend_caller.main(hook_args)
    mock_call_hook.assert_called_once_with(*expected_args, **expected_kwargs)


def test_missing_backend_module():
    be_module = "nonexistent_backend_module"
    with pytest.raises(ModuleNotFoundError, match=be_module):
        backend_caller.main([be_module, "build_wheel"])


def test_missing_backend_object(build_backend):
    be = build_backend("be")
    be_object = "nonexistent_backend_object"

    with pytest.raises(
        AttributeError, match=f"module 'be' has no attribute '{be_object}'"
    ):
        backend_caller.main([f"{be.name}:{be_object}", "build_wheel"])


def test_in_tree_backend_not_used(build_backend, build_backend_path):
    """Check if backend was not loaded from backend path"""
    be = build_backend("be")
    with pytest.raises(
        ValueError, match="backend code must be loaded from one of backend-path"
    ):
        backend_caller.main(
            [be.name, "build_wheel", "--backend-path", build_backend_path]
        )


@pytest.mark.parametrize("hook", ("build_wheel", "build_sdist"))
def test_missing_mandatory_hook(hook, build_backend):
    hooks = list(backend_caller.SUPPORTED_HOOKS)
    hooks.remove(hook)
    be = build_backend("be", hooks=hooks)
    with pytest.raises(
        ValueError, match=f"Missing mandatory hook in build backend: {hook}"
    ):
        backend_caller.main([be.name, hook])


@pytest.mark.parametrize(
    "hook,hook_result",
    (("build_wheel", "foo-1.0.whl"), ("build_sdist", "foo-1.0.tar.gz")),
    ids=["build_wheel", "build_sdist"],
)
def test_mandatory_hooks(hook, hook_result, build_backend, wheeldir):
    be = build_backend("be")
    result = backend_caller.call_hook(
        be.name,
        backend_path=None,
        hook=hook,
        hook_args=[str(wheeldir)],
        hook_kwargs={},
    )
    assert result == hook_result


def test_missing_get_requires_for_build_wheel(build_backend):
    hook = "get_requires_for_build_wheel"
    hooks = list(backend_caller.SUPPORTED_HOOKS)
    hooks.remove(hook)
    be = build_backend("be", hooks=hooks)
    hook_result = backend_caller.call_hook(
        be.name, backend_path=None, hook=hook, hook_args=[], hook_kwargs={}
    )
    assert hook_result == []


def test_get_requires_for_build_wheel(build_backend):
    be = build_backend("be")
    hook = "get_requires_for_build_wheel"
    hook_result = backend_caller.call_hook(
        be.name, backend_path=None, hook=hook, hook_args=[], hook_kwargs={}
    )
    assert hook_result == ["build_wheel_dep"]


def test_missing_get_requires_for_build_sdist(build_backend):
    hook = "get_requires_for_build_sdist"
    hooks = list(backend_caller.SUPPORTED_HOOKS)
    hooks.remove(hook)
    be = build_backend("be", hooks=hooks)
    hook_result = backend_caller.call_hook(
        be.name, backend_path=None, hook=hook, hook_args=[], hook_kwargs={}
    )
    assert hook_result == []


def test_get_requires_for_build_sdist(build_backend):
    be = build_backend("be")
    hook = "get_requires_for_build_sdist"
    hook_result = backend_caller.call_hook(
        be.name, backend_path=None, hook=hook, hook_args=[], hook_kwargs={}
    )
    assert hook_result == ["build_sdist_dep"]


@pytest.mark.parametrize(
    "be_object", (("be",), ("be", "obj")), ids=["module", "module:object"]
)
def test_backend_object(be_object, build_backend, wheeldir):
    build_backend(*be_object)
    hook_result = backend_caller.call_hook(
        ":".join(be_object),
        backend_path=None,
        hook="build_wheel",
        hook_args=[str(wheeldir)],
        hook_kwargs={},
    )
    assert hook_result == "foo-1.0.whl"


@pytest.mark.parametrize(
    "be_object", (("be",), ("be", "obj")), ids=["module", "module:object"]
)
def test_in_tree_backend_object(
    be_object, in_tree_build_backend, wheeldir, build_backend_path
):
    in_tree_build_backend(*be_object)

    hook_result = backend_caller.call_hook(
        ":".join(be_object),
        backend_path=[build_backend_path],
        hook="build_wheel",
        hook_args=[str(wheeldir)],
        hook_kwargs={},
    )
    assert hook_result == "foo-1.0.whl"


def test_write_result(mocker, build_backend, wheeldir):
    be = build_backend("be")
    expected_result = json.dumps({"result": "foo-1.0.whl"}).encode("utf-8")
    m = mocker.patch.object(
        backend_caller.os, "write", return_value=len(expected_result)
    )
    backend_caller.main(
        [
            be.name,
            "build_wheel",
            "--result-fd",
            str(3),
            "--hook-args",
            json.dumps([[str(wheeldir)], {}]),
        ],
    )
    m.assert_called_once_with(3, expected_result)


def test_no_write_result(mocker, build_backend, wheeldir):
    be = build_backend("be")
    m = mocker.patch.object(backend_caller.os, "write")
    backend_caller.main(
        [
            be.name,
            "build_wheel",
            "--hook-args",
            json.dumps([[str(wheeldir)], {}]),
        ],
    )
    m.assert_not_called()

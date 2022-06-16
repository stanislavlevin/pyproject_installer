from pathlib import Path
import logging
import subprocess
import sys
import textwrap

import pytest

from pyproject_installer import __version__ as project_version
from pyproject_installer import __main__ as project_main


@pytest.fixture
def mock_build_wheel(mocker):
    return mocker.patch.object(project_main, "build_wheel")


@pytest.fixture
def mock_build_sdist(mocker):
    return mocker.patch.object(project_main, "build_sdist")


@pytest.fixture
def mock_install_wheel(mocker):
    return mocker.patch.object(project_main, "install_wheel")


@pytest.fixture
def mock_read_tracker(mocker):
    return mocker.patch.object(
        project_main.Path,
        "read_text",
        autospec=True,
        return_value="foo.whl\n",
    )


def test_version():
    result = subprocess.run(
        args=[sys.executable, "-m", "pyproject_installer", "--version"],
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout.rstrip().decode("utf-8") == project_version
    assert result.stderr == b""


def test_help():
    result = subprocess.run(
        args=[sys.executable, "-m", "pyproject_installer", "--help"],
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout.rstrip().startswith(
        b"usage: python -m pyproject_installer "
    )
    assert result.stderr == b""


@pytest.mark.parametrize(
    "verbose, logging_kwargs",
    (
        (False, ("%(levelname)-8s : %(message)s", logging.INFO)),
        (True, ("%(levelname)-8s : %(name)s : %(message)s", logging.DEBUG)),
    ),
    ids=["default", "verbose"],
)
def test_logging(verbose, logging_kwargs, mock_build_wheel, mocker):
    """Check format and level of logging depending on verbosity"""
    m = mocker.patch.object(project_main.logging, "basicConfig")

    build_args = ["build"]
    if verbose:
        build_args.insert(0, "--verbose")

    project_main.main(build_args)

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
            import logging

            from pyproject_installer import __main__

            __main__.setup_logging(verbose=True)
            logging.getLogger().{level}("{level}")
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


def test_build_cli_default(mock_build_wheel):
    srcdir = Path.cwd()
    outdir = srcdir / "dist"
    build_args = ["build"]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": None,
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_srcdir(mock_build_wheel):
    srcdir = Path("/srcdir")
    outdir = srcdir / "dist"
    build_args = ["build", str(srcdir)]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": None,
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_outdir(mock_build_wheel):
    srcdir = Path.cwd()
    outdir = Path("/outdir")
    build_args = ["build", "--outdir", str(outdir)]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": None,
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_srcdir_outdir(mock_build_wheel):
    srcdir = Path("/srcdir")
    outdir = Path("/outdir")
    build_args = ["build", str(srcdir), "--outdir", str(outdir)]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": None,
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_verbose(mock_build_wheel):
    srcdir = Path.cwd()
    outdir = srcdir / "dist"
    build_args = ["--verbose", "build"]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": True,
        "config": None,
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_sdist(mock_build_sdist):
    srcdir = Path.cwd()
    outdir = srcdir / "dist"
    build_args = ["build", "--sdist"]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": None,
    }
    mock_build_sdist.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_backend_settings(mock_build_wheel):
    srcdir = Path.cwd()
    outdir = srcdir / "dist"
    build_args = ["build", "--backend-config-settings", '{"key": "value"}']
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": {"key": "value"},
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_backend_settings_complex(mock_build_wheel):
    srcdir = Path.cwd()
    outdir = srcdir / "dist"
    build_args = [
        "build",
        "--backend-config-settings",
        '{"key1": ["value11", "value12"], "key2": "value2"}',
    ]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": {"key1": ["value11", "value12"], "key2": "value2"},
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


def test_build_cli_backend_settings_empty(mock_build_wheel):
    srcdir = Path.cwd()
    outdir = srcdir / "dist"
    build_args = [
        "build",
        "--backend-config-settings",
        "{}",
    ]
    project_main.main(build_args)
    b_args = (srcdir,)
    b_kwargs = {
        "outdir": outdir,
        "verbose": False,
        "config": {},
    }
    mock_build_wheel.assert_called_once_with(*b_args, **b_kwargs)


@pytest.mark.parametrize(
    "config",
    ("key", '["val1", "val2"]'),
)
def test_build_cli_invalid_backend_settings(config, mock_build_wheel):
    build_args = ["build", "--backend-config-settings", config]

    with pytest.raises(ValueError) as exc:
        project_main.main(build_args)

    expected_err_msg = (
        f"Invalid value of --backend-config-settings: {config!r}, "
        "should be a dumped JSON dictionary"
    )
    assert str(exc.value) == expected_err_msg


def test_install_cli_default(mocker, mock_install_wheel, mock_read_tracker):
    install_args = ["install"]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    wheel_tracker = wheel.parent / project_main.WHEEL_TRACKER
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was read from tracker
    mock_read_tracker.assert_called_once_with(wheel_tracker, encoding="utf-8")


def test_install_cli_destdir(mocker, mock_install_wheel, mock_read_tracker):
    destdir = Path("/destdir")
    install_args = ["install", "--destdir", str(destdir)]

    wheel = Path.cwd() / "dist" / "foo.whl"
    wheel_tracker = wheel.parent / project_main.WHEEL_TRACKER
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was read from tracker
    mock_read_tracker.assert_called_once_with(wheel_tracker, encoding="utf-8")


def test_install_cli_wheel(mocker, mock_install_wheel, mock_read_tracker):
    wheel = Path("/wheel.whl")
    install_args = ["install", str(wheel)]

    destdir = Path("/")
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was not read from tracker
    mock_read_tracker.assert_not_called()


def test_install_cli_wheel_destdir(
    mocker, mock_install_wheel, mock_read_tracker
):
    wheel = Path("/wheel.whl")
    destdir = Path("/destdir")
    install_args = ["install", str(wheel), "--destdir", str(destdir)]

    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was not read from tracker
    mock_read_tracker.assert_not_called()


def test_install_cli_installer_tool(mock_install_wheel, mock_read_tracker):
    wheel = Path("/wheel.whl")
    installer_tool = "my_installer"
    install_args = ["install", str(wheel), "--installer", installer_tool]

    destdir = Path("/")
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": installer_tool,
        "strip_dist_info": True,
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was not read from tracker
    mock_read_tracker.assert_not_called()


def test_install_cli_no_strip_dist_info(mock_install_wheel, mock_read_tracker):
    install_args = ["install", "--no-strip-dist-info"]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": False,
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)


def test_install_default_wheel_missing_tracker(mocker, mock_read_tracker):
    """Check error if wheeltracker is missing and wheel is default"""

    def _mock_read_text(*args, **kwargs):
        raise FileNotFoundError()

    mock_read_tracker.side_effect = _mock_read_text
    install_args = ["install"]
    with pytest.raises(ValueError, match="Missing wheel tracker"):
        project_main.main(install_args)

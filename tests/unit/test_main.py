import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from pyproject_installer import __main__ as project_main
from pyproject_installer import __version__ as project_version
from pyproject_installer.codes import ExitCodes
from pyproject_installer.errors import RunCommandEnvError, RunCommandError


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
def mock_run_command(mocker):
    return mocker.patch.object(project_main, "run_command")


@pytest.fixture
def mock_deps_command(mocker):
    return mocker.patch.object(project_main, "deps_command")


@pytest.fixture
def mock_completion_command(mocker):
    return mocker.patch.object(project_main, "completion_command")


@pytest.fixture
def mock_main(mocker):
    return mocker.patch.object(project_main, "main")


@pytest.fixture
def mock_run_autocomplete(mocker):
    return mocker.patch.object(
        project_main,
        "run_autocomplete",
        side_effect=SystemExit,
    )


@pytest.fixture
def mock_read_tracker(mocker):
    return mocker.patch.object(
        project_main.Path,
        "read_text",
        autospec=True,
        return_value="foo.whl\n",
    )


@pytest.fixture
def preserve_cwd(monkeypatch):
    """Snapshot and restore the process cwd around a test."""
    monkeypatch.chdir(Path.cwd())


@pytest.fixture
def record_cwd():
    """Patch a mocked command to record its cwd"""
    command_cwd: list[Path] = []

    def _patch_mocked_cmd(mocked_cmd):
        def _record_cwd():
            command_cwd[:] = [Path.cwd()]

        def _cwd():
            return command_cwd[0] if command_cwd else None

        mocked_cmd.side_effect = lambda *_a, **_k: _record_cwd()
        return _cwd

    return _patch_mocked_cmd


def invalid_choice_messages(choice, *, choices):
    return (
        f"invalid choice: '{choice}' (choose from {msg})\n"
        for msg in [
            # Python 3.12.8/3.13.1+
            ", ".join(choices),
            # Python < 3.12.8/3.13.1
            ", ".join(f"'{x}'" for x in choices),
        ]
    )


DEFAULT_DEPS_ADD_CLI_KWARGS: dict[str, Any] = {
    "srctype": None,
    "srcargs": [],
    "candidates": None,
    "sources": None,
    "reconfigure": False,
    "sync": False,
    "verify": False,
    "verify_excludes": [],
    "verify_ignore_version": False,
}


def test_version():
    result = subprocess.run(
        args=[sys.executable, "-m", "pyproject_installer", "--version"],
        capture_output=True,
        check=True,
    )
    assert result.stdout.rstrip().decode("utf-8") == project_version
    assert result.stderr == b""


def test_help():
    result = subprocess.run(
        args=[sys.executable, "-m", "pyproject_installer", "--help"],
        capture_output=True,
        check=True,
    )
    assert result.stdout.rstrip().startswith(
        b"usage: python -m pyproject_installer ",
    )
    assert result.stderr == b""


@pytest.mark.usefixtures("mock_build_wheel")
def test_logging_default(mocker):
    """Check format and level of default logging"""
    m = mocker.patch.object(project_main.logging, "basicConfig")

    build_args = ["build"]
    project_main.main(build_args)

    m.assert_called_once()
    # args
    assert m.call_args.args == ()
    # kwargs
    kwargs = m.call_args.kwargs
    assert len(kwargs) == 3
    ## format
    assert kwargs["format"] == "%(levelname)-8s : %(message)s"
    ## root logger level
    assert kwargs["level"] == logging.INFO
    ## handlers
    actual_handlers = kwargs["handlers"]
    assert len(actual_handlers) == 1
    actual_handler = actual_handlers[0]
    assert isinstance(actual_handler, logging.StreamHandler)
    assert actual_handler.level == logging.NOTSET
    assert actual_handler.stream == sys.stderr


@pytest.mark.parametrize(
    "verbose_option",
    ("-v", "--verbose"),
    ids=("short", "long"),
)
@pytest.mark.usefixtures("mock_build_wheel")
def test_logging_verbose(verbose_option, mocker):
    """Check format and level of verbose logging"""
    m = mocker.patch.object(project_main.logging, "basicConfig")

    build_args = [verbose_option, "build"]
    project_main.main(build_args)

    m.assert_called_once()
    # args
    assert m.call_args.args == ()
    # kwargs
    kwargs = m.call_args.kwargs
    assert len(kwargs) == 3
    ## format
    assert kwargs["format"] == "%(levelname)-8s : %(name)s : %(message)s"
    ## root logger level
    assert kwargs["level"] == logging.DEBUG
    ## handlers
    actual_handlers = kwargs["handlers"]
    assert len(actual_handlers) == 1
    actual_handler = actual_handlers[0]
    assert isinstance(actual_handler, logging.StreamHandler)
    assert actual_handler.level == logging.NOTSET
    assert actual_handler.stream == sys.stderr


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
@pytest.mark.usefixtures("mock_build_wheel")
def test_build_cli_invalid_backend_settings(config, capsys):
    build_args = ["build", "--backend-config-settings", config]

    with pytest.raises(SystemExit) as exc:
        project_main.main(build_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE

    expected_err_msg = (
        f"Invalid value of --backend-config-settings: {config!r}, "
        "should be a dumped JSON dictionary"
    )
    captured = capsys.readouterr()
    assert not captured.out
    assert expected_err_msg in captured.err


def test_install_cli_default(mock_install_wheel, mock_read_tracker):
    install_args = ["install"]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    wheel_tracker = wheel.parent / project_main.WHEEL_TRACKER
    i_args = (wheel,)
    i_kwargs: dict[str, Any] = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was read from tracker
    mock_read_tracker.assert_called_once_with(wheel_tracker, encoding="utf-8")


def test_install_cli_destdir(mock_install_wheel, mock_read_tracker):
    destdir = Path("/destdir")
    install_args = ["install", "--destdir", str(destdir)]

    wheel = Path.cwd() / "dist" / "foo.whl"
    wheel_tracker = wheel.parent / project_main.WHEEL_TRACKER
    i_args = (wheel,)
    i_kwargs: dict[str, Any] = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was read from tracker
    mock_read_tracker.assert_called_once_with(wheel_tracker, encoding="utf-8")


def test_install_cli_wheel(mock_install_wheel, mock_read_tracker):
    wheel = Path("/wheel.whl")
    install_args = ["install", str(wheel)]

    destdir = Path("/")
    i_args = (wheel,)
    i_kwargs: dict[str, Any] = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was not read from tracker
    mock_read_tracker.assert_not_called()


def test_install_cli_wheel_destdir(mock_install_wheel, mock_read_tracker):
    wheel = Path("/wheel.whl")
    destdir = Path("/destdir")
    install_args = ["install", str(wheel), "--destdir", str(destdir)]

    i_args = (wheel,)
    i_kwargs: dict[str, Any] = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": [],
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
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)
    # check if wheel path was not read from tracker
    mock_read_tracker.assert_not_called()


@pytest.mark.usefixtures("mock_read_tracker")
def test_install_cli_no_strip_dist_info(mock_install_wheel):
    install_args = ["install", "--no-strip-dist-info"]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    i_args = (wheel,)
    i_kwargs: dict[str, Any] = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": False,
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)


def test_install_default_wheel_missing_tracker(mock_read_tracker, capsys):
    """Check error if wheeltracker is missing and wheel is default"""

    mock_read_tracker.side_effect = FileNotFoundError
    install_args = ["install"]
    with pytest.raises(SystemExit) as exc:
        project_main.main(install_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    captured = capsys.readouterr()
    assert not captured.out
    expected_msg = "Missing wheel tracker, re-run build steps or specify wheel"
    assert expected_msg in captured.err


@pytest.mark.usefixtures("mock_read_tracker")
def test_install_cli_rpm_filelist(mock_install_wheel, tmpdir):
    """
    Run install with --rpm-filelist.
    """
    filelist = tmpdir / "foo.files"
    install_args = ("install", "--rpm-filelist", str(filelist))

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": filelist,
        "force_site": None,
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)


@pytest.mark.usefixtures("mock_read_tracker")
def test_install_cli_platlib(mock_install_wheel):
    """
    Run install with --platlib.
    """
    install_args = ["install", "--platlib"]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    i_args = (wheel,)
    i_kwargs: dict[str, Any] = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": "platlib",
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)


@pytest.mark.usefixtures("mock_read_tracker")
def test_install_cli_purelib(mock_install_wheel):
    """
    Run install with --purelib.
    """
    install_args = ["install", "--purelib"]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    i_args = (wheel,)
    i_kwargs: dict[str, Any] = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": "purelib",
        "exclude_paths": [],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)


def test_install_cli_platlib_purelib_mutually_exclusive(
    mock_install_wheel,
    capsys,
):
    """
    Check --platlib and --purelib together is an argparse error.
    """
    install_args = ["install", "--platlib", "--purelib"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(install_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    captured = capsys.readouterr()
    assert not captured.out
    # actual error message is controlled by cpython,
    # so it's unreliable to check captured.err
    mock_install_wheel.assert_not_called()


@pytest.mark.usefixtures("mock_read_tracker")
def test_install_cli_exclude_paths_multiple(mock_install_wheel):
    """
    Run install with --exclude-paths passing multiple patterns.
    """
    install_args = [
        "install",
        "--exclude-paths",
        "tests/*",
        "*/tests/*",
        "test_*.py",
    ]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": ["tests/*", "*/tests/*", "test_*.py"],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)


@pytest.mark.usefixtures("mock_read_tracker")
def test_install_cli_exclude_paths_single(mock_install_wheel):
    """
    Run install with --exclude-paths passing a single pattern.
    """
    install_args = ["install", "--exclude-paths", "tests/*"]

    destdir = Path("/")
    wheel = Path.cwd() / "dist" / "foo.whl"
    i_args = (wheel,)
    i_kwargs = {
        "destdir": destdir,
        "installer": None,
        "strip_dist_info": True,
        "rpm_filelist": None,
        "force_site": None,
        "exclude_paths": ["tests/*"],
    }

    project_main.main(install_args)
    mock_install_wheel.assert_called_once_with(*i_args, **i_kwargs)


@pytest.mark.usefixtures("mock_read_tracker")
def test_install_cli_exclude_paths_requires_value(mock_install_wheel):
    """
    --exclude-paths requires at least one value (nargs='+').
    """
    install_args = ["install", "--exclude-paths"]

    with pytest.raises(SystemExit):
        project_main.main(install_args)
    # actual error message is controlled by cpython,
    # so it's unreliable to check stderr
    mock_install_wheel.assert_not_called()


def test_run_cli_default(mock_run_command, mock_read_tracker, caplog):
    """Run run without options

    - mock run_command and wheel tracker
    - check default wheel was used
    - check exit code
    - check outputs
    """
    run_args = ["run", "foo"]

    wheel = Path.cwd() / "dist" / "foo.whl"
    wheel_tracker = wheel.parent / project_main.WHEEL_TRACKER
    r_args = (wheel,)
    r_kwargs = {
        "command": ["foo"],
    }

    caplog.set_level(logging.INFO)

    with pytest.raises(SystemExit) as exc:
        project_main.main(run_args)
    assert exc.value.code == ExitCodes.OK

    assert "Command's result: OK" in caplog.text
    mock_run_command.assert_called_once_with(*r_args, **r_kwargs)
    # check if wheel path was read from tracker
    mock_read_tracker.assert_called_once_with(wheel_tracker, encoding="utf-8")


def test_run_cli_wheel(mock_run_command, mock_read_tracker, caplog):
    """Run run with `--wheel`

    - mock run_command and wheel tracker
    - check given wheel was used
    - check exit code
    - check outputs
    """
    wheel = Path("/wheel.whl")
    run_args = ["run", "--wheel", str(wheel), "foo"]

    r_args = (wheel,)
    r_kwargs = {
        "command": ["foo"],
    }

    caplog.set_level(logging.INFO)

    with pytest.raises(SystemExit) as exc:
        project_main.main(run_args)
    assert exc.value.code == ExitCodes.OK

    assert "Command's result: OK" in caplog.text
    mock_run_command.assert_called_once_with(*r_args, **r_kwargs)
    # check if wheel path was not read from tracker
    mock_read_tracker.assert_not_called()


def test_run_cli_default_wheel_missing_tracker(mock_read_tracker, capsys):
    """Check error if wheeltracker is missing and wheel is default

    - mock wheel tracker
    - emulate missing wheel tracker
    - check exit code
    - check outputs
    """

    mock_read_tracker.side_effect = FileNotFoundError
    run_args = ["run", "foo"]
    with pytest.raises(SystemExit) as exc:
        project_main.main(run_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    captured = capsys.readouterr()
    assert not captured.out
    expected_msg = "Missing wheel tracker, re-run build steps or specify wheel"
    assert expected_msg in captured.err


@pytest.mark.usefixtures("mock_read_tracker")
def test_run_cli_failed_result(mock_run_command, caplog):
    """Check error if command was failed

    - mock run command and wheel tracker
    - emulate missing command
    - check exit code
    - check outputs
    """
    exc_msg = "nonexistent command"

    mock_run_command.side_effect = RunCommandError(exc_msg)
    run_args = ["run", "nonexistent command"]
    caplog.set_level(logging.INFO)
    with pytest.raises(SystemExit) as exc:
        project_main.main(run_args)
    assert exc.value.code == ExitCodes.FAILURE
    assert "Command's result: FAILURE" in caplog.text
    assert f"Command's error: {exc_msg}" in caplog.text


@pytest.mark.usefixtures("mock_read_tracker")
def test_run_cli_venv_error(mock_run_command, caplog):
    """Check error if command was failed

    - mock run command and wheel tracker
    - emulate venv usage error
    - check exit code
    - check outputs
    """
    exc_msg = "venv error"

    mock_run_command.side_effect = RunCommandEnvError(exc_msg)
    run_args = ["run", "nonexistent command"]
    caplog.set_level(logging.INFO)
    with pytest.raises(SystemExit) as exc:
        project_main.main(run_args)
    assert exc.value.code == ExitCodes.FAILURE
    assert "Command's result: FAILURE (virtual env setup failed)" in caplog.text
    assert "Command's error:" in caplog.text
    assert exc_msg in caplog.text


@pytest.mark.usefixtures("mock_read_tracker")
def test_run_cli_internal_error(mock_run_command, caplog):
    """Check error if internal error happened

    - mock run command and wheel tracker
    - emulate internal error
    - check exit code
    - check outputs
    """
    exc_msg = "something went wrong"

    mock_run_command.side_effect = Exception(exc_msg)
    run_args = ["run", "nonexistent command"]
    caplog.set_level(logging.INFO)
    with pytest.raises(SystemExit) as exc:
        project_main.main(run_args)
    assert exc.value.code == ExitCodes.INTERNAL_ERROR
    assert (
        "Command's result: INTERNAL_ERROR (internal error happened)"
    ) in caplog.text
    assert "Command's error:" in caplog.text
    assert exc_msg in caplog.text


def test_deps_cli_help(capsys):
    """Run deps --help

    - check msg and exit code
    """
    deps_args = ["deps", "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.OK

    captured = capsys.readouterr()
    assert not captured.err
    expected_msg = "usage: python -m pyproject_installer deps "
    assert expected_msg in captured.out


def test_deps_cli_show_help(capsys):
    """Run deps show --help

    - check msg and exit code
    """
    action = "show"
    deps_args = ["deps", action, "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.OK

    captured = capsys.readouterr()
    assert not captured.err
    expected_msg = f"usage: python -m pyproject_installer deps {action} "
    assert expected_msg in captured.out


def test_deps_cli_show_default(mock_deps_command):
    """Run deps show

    - mock deps_command
    - check default depsconfig path
    - check args
    """
    action = "show"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action]

    r_args = (action, Path(depsconfig))
    r_kwargs: dict[str, Any] = {"srcnames": []}

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_show_depsconfig(mock_deps_command):
    """Run deps show with specified depsconfig path

    - mock deps_command
    - check args
    """
    action = "show"
    depsconfig = "foo.json"
    deps_args = ["deps", "--depsconfig", depsconfig, action]

    r_args = (action, Path(depsconfig))
    r_kwargs: dict[str, Any] = {"srcnames": []}

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.parametrize("srcnames", (["foo"], ["foo", "bar"]))
def test_deps_cli_show_selected(mock_deps_command, srcnames):
    """Run deps show with specified source names

    - mock deps_command
    - check args
    """
    action = "show"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action]
    deps_args.extend(srcnames)

    r_args = (action, Path(depsconfig))
    r_kwargs = {"srcnames": srcnames}

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_sync_help(capsys):
    """Run deps sync --help

    - check msg and exit code
    """
    action = "sync"
    deps_args = ["deps", action, "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.OK

    captured = capsys.readouterr()
    assert not captured.err
    expected_msg = f"usage: python -m pyproject_installer deps {action} "
    assert expected_msg in captured.out


def test_deps_cli_sync_default(mock_deps_command):
    """Run deps sync

    - mock deps_command
    - check default depsconfig path
    - check args
    """
    action = "sync"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action]

    r_args = (action, Path(depsconfig))
    r_kwargs = {
        "srcnames": [],
        "verify": False,
        "verify_excludes": [],
        "verify_ignore_version": False,
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_sync_depsconfig(mock_deps_command):
    """Run deps sync with specified depsconfig path

    - mock deps_command
    - check args
    """
    action = "sync"
    depsconfig = "foo.json"
    deps_args = ["deps", "--depsconfig", depsconfig, action]

    r_args = (action, Path(depsconfig))
    r_kwargs = {
        "srcnames": [],
        "verify": False,
        "verify_excludes": [],
        "verify_ignore_version": False,
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.parametrize("srcnames", (["foo"], ["foo", "bar"]))
def test_deps_cli_sync_selected(mock_deps_command, srcnames):
    """Run deps sync with specified source names

    - mock deps_command
    - check args
    """
    action = "sync"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action]
    deps_args.extend(srcnames)

    r_args = (action, Path(depsconfig))
    r_kwargs = {
        "srcnames": srcnames,
        "verify": False,
        "verify_excludes": [],
        "verify_ignore_version": False,
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_chdir_on_valid_dir(mock_build_wheel, record_cwd, tmp_path):
    """
    Pass -C with absolute path to valid directory and check if cwd is changed.
    """
    cwd = tmp_path.resolve()
    actual_cwd = record_cwd(mock_build_wheel)
    project_main.main(["-C", str(cwd), "build"])
    assert actual_cwd() == cwd
    mock_build_wheel.assert_called_once()


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_relative_path_resolves_against_original_cwd(
    mock_build_wheel,
    tmp_path,
    monkeypatch,
    record_cwd,
):
    """
    Pass -C with relative path to valid directory and check if cwd is changed.
    """
    rel_dirname = "pkg"
    cwd = tmp_path / rel_dirname
    cwd.mkdir()
    monkeypatch.chdir(tmp_path)
    actual_cwd = record_cwd(mock_build_wheel)
    project_main.main(["-C", rel_dirname, "build"])
    assert actual_cwd() == cwd
    mock_build_wheel.assert_called_once()


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_missing_dir_errors(mock_build_wheel, tmp_path, capsys):
    """Pass -C with nonexistent directory and check the error"""
    cwd = tmp_path / "does_not_exist"
    with pytest.raises(SystemExit) as exc:
        project_main.main(["-C", str(cwd), "build"])
    assert exc.value.code == ExitCodes.WRONG_USAGE
    captured = capsys.readouterr()

    # actual error message is controlled by cpython
    expected_err_msg = "-C: "
    assert expected_err_msg in captured.err
    mock_build_wheel.assert_not_called()


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_non_dir_errors(mock_build_wheel, tmp_path, capsys):
    """Pass -C with file (not directory) and check the error"""
    (cwd := tmp_path / "some_file").touch()
    with pytest.raises(SystemExit) as exc:
        project_main.main(["-C", str(cwd), "build"])
    assert exc.value.code == ExitCodes.WRONG_USAGE
    captured = capsys.readouterr()

    # actual error message is controlled by cpython
    expected_err_msg = "-C: "
    assert expected_err_msg in captured.err
    mock_build_wheel.assert_not_called()


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_empty_string_no_change(mock_build_wheel, record_cwd):
    """Pass -C "" and check if cwd is left unchanged"""
    cwd = ""
    actual_cwd = record_cwd(mock_build_wheel)
    project_main.main(["-C", str(cwd), "build"])
    assert actual_cwd() == Path.cwd()
    mock_build_wheel.assert_called_once()


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_unchanged_without_flag(mock_build_wheel, record_cwd):
    """Don't pass -C and check if cwd is left unchanged"""
    actual_cwd = record_cwd(mock_build_wheel)
    project_main.main(["build"])
    assert actual_cwd() == Path.cwd()
    mock_build_wheel.assert_called_once()


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_default_srcdir_build(mock_build_wheel, tmp_path, record_cwd):
    """
    Pass -C with valid absolute directory and check if default srcdir changed
    for build command.
    """
    cwd = tmp_path.resolve()
    actual_cwd = record_cwd(mock_build_wheel)
    project_main.main(["-C", str(cwd), "build"])
    assert actual_cwd() == cwd
    call_args, call_kwargs = mock_build_wheel.call_args
    assert call_args[0] == cwd
    assert call_kwargs["outdir"] == cwd / "dist"


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_rel_srcdir_build(mock_build_wheel, tmp_path, record_cwd):
    """
    Pass -C with valid absolute directory and check if relative srcdir is not
    changed for build command.
    """
    cwd = tmp_path.resolve()
    srcdir = Path("srcdir")
    actual_cwd = record_cwd(mock_build_wheel)
    project_main.main(["-C", str(cwd), "build", str(srcdir)])
    assert actual_cwd() == cwd
    call_args, call_kwargs = mock_build_wheel.call_args
    assert call_args[0] == srcdir
    assert call_kwargs["outdir"] == srcdir / "dist"


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_abs_srcdir_build(mock_build_wheel, tmp_path, record_cwd):
    """
    Pass -C with valid absolute directory and check if absolute srcdir is not
    changed for build command.
    """
    cwd = tmp_path.resolve()
    srcdir = Path("/srcdir")
    actual_cwd = record_cwd(mock_build_wheel)
    project_main.main(["-C", str(cwd), "build", str(srcdir)])
    assert actual_cwd() == cwd
    call_args, call_kwargs = mock_build_wheel.call_args
    assert call_args[0] == srcdir
    assert call_kwargs["outdir"] == srcdir / "dist"


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_default_depsconfig_deps(mock_deps_command, tmp_path, record_cwd):
    """
    Pass -C with valid absolute directory and check if default depsconfig
    changed for deps command.
    """
    cwd = tmp_path.resolve()
    actual_cwd = record_cwd(mock_deps_command)
    project_main.main(["-C", str(cwd), "deps", "show"])
    assert actual_cwd() == cwd
    call_args, _ = mock_deps_command.call_args
    assert call_args[1] == cwd / project_main.DEFAULT_CONFIG_NAME


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_rel_depsconfig_deps(mock_deps_command, tmp_path, record_cwd):
    """
    Pass -C with valid absolute directory and check if relative depsconfig
    is not changed for deps command.
    """
    cwd = tmp_path.resolve()
    depsconfig = Path("depsconfig")
    actual_cwd = record_cwd(mock_deps_command)
    project_main.main(
        ["-C", str(cwd), "deps", "--depsconfig", str(depsconfig), "show"],
    )
    assert actual_cwd() == cwd
    call_args, _ = mock_deps_command.call_args
    assert call_args[1] == depsconfig


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_abs_depsconfig_deps(mock_deps_command, tmp_path, record_cwd):
    """
    Pass -C with valid absolute directory and check if absolute depsconfig
    is not changed for deps command.
    """
    cwd = tmp_path.resolve()
    depsconfig = Path("/depsconfig")
    actual_cwd = record_cwd(mock_deps_command)
    project_main.main(
        ["-C", str(cwd), "deps", "--depsconfig", str(depsconfig), "show"],
    )
    assert actual_cwd() == cwd
    call_args, _ = mock_deps_command.call_args
    assert call_args[1] == depsconfig


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_default_wheel_install(
    mock_install_wheel,
    mock_read_tracker,
    tmp_path,
    record_cwd,
):
    """
    Pass -C with valid absolute directory and check default wheel for install
    command.
    """
    cwd = tmp_path.resolve()
    expected_wheel = cwd / "dist" / "foo.whl"
    expected_tracker = cwd / "dist" / project_main.WHEEL_TRACKER
    actual_cwd = record_cwd(mock_install_wheel)
    project_main.main(["-C", str(cwd), "install"])
    assert actual_cwd() == cwd
    mock_read_tracker.assert_called_once_with(
        expected_tracker,
        encoding="utf-8",
    )
    call_args, _ = mock_install_wheel.call_args
    assert call_args[0] == expected_wheel


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_rel_wheel_install(
    mock_install_wheel,
    mock_read_tracker,
    tmp_path,
    record_cwd,
):
    """
    Pass -C with valid absolute directory and check relative wheel for install
    command.
    """
    cwd = tmp_path.resolve()
    wheel = Path("wheel")
    actual_cwd = record_cwd(mock_install_wheel)
    project_main.main(["-C", str(cwd), "install", str(wheel)])
    assert actual_cwd() == cwd
    mock_read_tracker.assert_not_called()
    call_args, _ = mock_install_wheel.call_args
    assert call_args[0] == wheel


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_abs_wheel_install(
    mock_install_wheel,
    mock_read_tracker,
    tmp_path,
    record_cwd,
):
    """
    Pass -C with valid absolute directory and check absolute wheel for install
    command.
    """
    cwd = tmp_path.resolve()
    wheel = Path("/wheel")
    actual_cwd = record_cwd(mock_install_wheel)
    project_main.main(["-C", str(cwd), "install", str(wheel)])
    assert actual_cwd() == cwd
    mock_read_tracker.assert_not_called()
    call_args, _ = mock_install_wheel.call_args
    assert call_args[0] == wheel


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_default_wheel_run(
    mock_run_command,
    mock_read_tracker,
    tmp_path,
    record_cwd,
):
    """
    Pass -C with valid absolute directory and check default wheel for run
    command.
    """

    cwd = tmp_path.resolve()
    expected_wheel = cwd / "dist" / "foo.whl"
    expected_tracker = cwd / "dist" / project_main.WHEEL_TRACKER
    actual_cwd = record_cwd(mock_run_command)
    with pytest.raises(SystemExit) as exc:
        project_main.main(["-C", str(cwd), "run", "--", "true"])
    assert exc.value.code == ExitCodes.OK
    assert actual_cwd() == cwd
    mock_read_tracker.assert_called_once_with(
        expected_tracker,
        encoding="utf-8",
    )
    call_args, _ = mock_run_command.call_args
    assert call_args[0] == expected_wheel


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_rel_wheel_run(
    mock_run_command,
    mock_read_tracker,
    tmp_path,
    record_cwd,
):
    """
    Pass -C with valid absolute directory and check relative wheel for run
    command.
    """

    cwd = tmp_path.resolve()
    wheel = Path("wheel")
    actual_cwd = record_cwd(mock_run_command)
    with pytest.raises(SystemExit) as exc:
        project_main.main(
            ["-C", str(cwd), "run", "--wheel", str(wheel), "--", "true"],
        )
    assert exc.value.code == ExitCodes.OK
    assert actual_cwd() == cwd
    mock_read_tracker.assert_not_called()
    call_args, _ = mock_run_command.call_args
    assert call_args[0] == wheel


@pytest.mark.usefixtures("preserve_cwd")
def test_cwd_abs_wheel_run(
    mock_run_command,
    mock_read_tracker,
    tmp_path,
    record_cwd,
):
    """
    Pass -C with valid absolute directory and check absolute wheel for run
    command.
    """

    cwd = tmp_path.resolve()
    wheel = Path("/wheel")
    actual_cwd = record_cwd(mock_run_command)
    with pytest.raises(SystemExit) as exc:
        project_main.main(
            ["-C", str(cwd), "run", "--wheel", str(wheel), "--", "true"],
        )
    assert exc.value.code == ExitCodes.OK
    assert actual_cwd() == cwd
    mock_read_tracker.assert_not_called()
    call_args, _ = mock_run_command.call_args
    assert call_args[0] == wheel


def test_deps_cli_sync_verify(mock_deps_command):
    """Run deps sync with verify

    - mock deps_command
    - check args
    """
    action = "sync"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action, "--verify"]

    r_args = (action, Path(depsconfig))
    r_kwargs = {
        "srcnames": [],
        "verify": True,
        "verify_excludes": [],
        "verify_ignore_version": False,
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_sync_verify_fail(mock_deps_command):
    """Run deps sync with failed verify

    - mock deps_command
    - raise DepsUnsyncedError
    - check exit code
    """
    action = "sync"
    mock_deps_command.side_effect = project_main.DepsUnsyncedError
    deps_args = ["deps", action, "--verify"]
    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.SYNC_VERIFY_ERROR


@pytest.mark.parametrize("excludes", (["foo"], ["foo", "bar"]))
def test_deps_cli_sync_verify_excludes(excludes, mock_deps_command):
    """Run deps sync with verify and excludes

    - mock deps_command
    - check args
    """
    action = "sync"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action, "--verify", "--verify-exclude"]
    deps_args.extend(excludes)

    r_args = (action, Path(depsconfig))
    r_kwargs = {
        "srcnames": [],
        "verify": True,
        "verify_excludes": excludes,
        "verify_ignore_version": False,
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.usefixtures("mock_deps_command")
def test_deps_cli_sync_verify_excludes_without_verify(capsys):
    """Run deps sync with verify_excludes and without verify

    - mock deps_command
    - check error
    """
    action = "sync"
    deps_args = ["deps", action, "--verify-exclude", "foo.*"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.WRONG_USAGE

    captured = capsys.readouterr()
    assert not captured.out
    expected_msg = "--verify-exclude option must be used with --verify"
    assert expected_msg in captured.err


def test_deps_cli_sync_verify_ignore_version(mock_deps_command):
    """Run deps sync with verify and ignore-version

    - mock deps_command
    - check args
    """
    action = "sync"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action, "--verify", "--verify-ignore-version"]

    r_args = (action, depsconfig)
    r_kwargs = {
        "srcnames": [],
        "verify": True,
        "verify_excludes": [],
        "verify_ignore_version": True,
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.usefixtures("mock_deps_command")
def test_deps_cli_sync_verify_ignore_version_without_verify(capsys):
    """Run deps sync with ignore-version and without verify

    - mock deps_command
    - check error
    """
    action = "sync"
    deps_args = ["deps", action, "--verify-ignore-version"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.WRONG_USAGE

    captured = capsys.readouterr()
    assert not captured.out
    expected_msg = "--verify-ignore-version option must be used with --verify"
    assert expected_msg in captured.err


def test_deps_cli_eval_help(capsys):
    """Run deps eval --help

    - check msg and exit code
    """
    action = "eval"
    deps_args = ["deps", action, "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.OK

    captured = capsys.readouterr()
    assert not captured.err
    expected_msg = f"usage: python -m pyproject_installer deps {action} "
    assert expected_msg in captured.out


def test_deps_cli_eval_default(mock_deps_command):
    """Run deps eval

    - mock deps_command
    - check default depsconfig path
    - check args
    """
    action = "eval"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action]

    r_args = (action, Path(depsconfig))
    r_kwargs: dict[str, Any] = {
        "srcnames": [],
        "depformat": None,
        "depformatextra": None,
        "extra": None,
        "excludes": [],
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_eval_depsconfig(mock_deps_command):
    """Run deps eval with specified depsconfig path

    - mock deps_command
    - check args
    """
    action = "eval"
    depsconfig = "foo.json"
    deps_args = ["deps", "--depsconfig", depsconfig, action]

    r_args = (action, Path(depsconfig))
    r_kwargs: dict[str, Any] = {
        "srcnames": [],
        "depformat": None,
        "depformatextra": None,
        "extra": None,
        "excludes": [],
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.parametrize("srcnames", (["foo"], ["foo", "bar"]))
def test_deps_cli_eval_selected(mock_deps_command, srcnames):
    """Run deps eval with specified source names

    - mock deps_command
    - check args
    """
    action = "eval"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action]
    deps_args.extend(srcnames)

    r_args = (action, Path(depsconfig))
    r_kwargs = {
        "srcnames": srcnames,
        "depformat": None,
        "depformatextra": None,
        "extra": None,
        "excludes": [],
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_eval_depformat(mock_deps_command):
    """Run deps eval with depformat

    - mock deps_command
    - check args
    """
    action = "eval"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action, "--depformat", "$name"]

    r_args = (action, Path(depsconfig))
    r_kwargs: dict[str, Any] = {
        "srcnames": [],
        "depformat": "$name",
        "depformatextra": None,
        "extra": None,
        "excludes": [],
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_eval_depformat_depformatextra(mock_deps_command):
    """Run deps eval with depformat and depformatextra

    - mock deps_command
    - check args
    """
    action = "eval"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = [
        "deps",
        action,
        "--depformat",
        "$name$fextra",
        "--depformatextra",
        "+$extra",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs: dict[str, Any] = {
        "srcnames": [],
        "depformat": "$name$fextra",
        "depformatextra": "+$extra",
        "extra": None,
        "excludes": [],
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.usefixtures("mock_deps_command")
def test_deps_cli_eval_depformatextra_without_depformat(capsys):
    """Run deps eval with depformatextra and without depformat

    - mock deps_command
    - check error
    """
    action = "eval"
    deps_args = ["deps", action, "--depformatextra", "+$extra"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.WRONG_USAGE

    captured = capsys.readouterr()
    assert not captured.out
    expected_msg = "depformatextra option must be used with depformat"
    assert expected_msg in captured.err


def test_deps_cli_eval_extra(mock_deps_command):
    """Run deps eval with extra marker

    - mock deps_command
    - check args
    """
    action = "eval"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    extra = "foo"
    deps_args = ["deps", action, "--extra", extra]

    r_args = (action, Path(depsconfig))
    r_kwargs: dict[str, Any] = {
        "srcnames": [],
        "depformat": None,
        "depformatextra": None,
        "extra": extra,
        "excludes": [],
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.parametrize("excludes", (["foo"], ["foo", "bar"]))
def test_deps_cli_eval_exclude(excludes, mock_deps_command):
    """Run deps eval with exclude

    - mock deps_command
    - check args
    """
    action = "eval"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = ["deps", action, "--exclude"]
    deps_args.extend(excludes)

    r_args = (action, Path(depsconfig))
    r_kwargs = {
        "srcnames": [],
        "depformat": None,
        "depformatextra": None,
        "extra": None,
        "excludes": excludes,
    }

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_help(capsys):
    """Run deps add --help

    - check msg and exit code
    """
    action = "add"
    deps_args = ["deps", action, "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.OK

    captured = capsys.readouterr()
    assert not captured.err
    expected_msg = f"usage: python -m pyproject_installer deps {action} "
    assert expected_msg in captured.out


def test_deps_cli_add_default(mock_deps_command):
    """Run deps add

    - mock deps_command
    - check default depsconfig path
    - check args
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "foo"
    srctype = "metadata"
    deps_args = ["deps", action, srcname, srctype]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        srctype=srctype,
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_depsconfig(mock_deps_command):
    """Run deps add with specified depsconfig path

    - mock deps_command
    - check args
    """
    action = "add"
    depsconfig = "foo.json"
    srcname = "foo"
    srctype = "metadata"
    deps_args = ["deps", "--depsconfig", depsconfig, action, srcname, srctype]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        srctype=srctype,
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.usefixtures("mock_deps_command")
def test_deps_cli_add_wrong_srctype(capsys):
    """Run deps add with wrong srctype

    - mock deps_command
    - check args
    """
    action = "add"
    srcname = "foo"
    srctype = "bar"
    deps_args = ["deps", action, srcname, srctype]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE

    expected_err_msgs = invalid_choice_messages(
        srctype,
        choices=project_main.SUPPORTED_COLLECTORS,
    )
    captured = capsys.readouterr()
    assert not captured.out
    assert any(True for msg in expected_err_msgs if msg in captured.err)


@pytest.mark.parametrize("srcargs", (["foo"], ["foo", "bar"]))
def test_deps_cli_add_sourceargs(srcargs, mock_deps_command):
    """Run deps add with specific source args

    - mock deps_command
    - check args
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "foo"
    srctype = "metadata"
    deps_args = ["deps", action, srcname, srctype]
    deps_args.extend(srcargs)

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        srctype=srctype,
        srcargs=srcargs,
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_reconfigure(mock_deps_command):
    """Run deps add with reconfigure

    - mock deps_command
    - check args
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "foo"
    srctype = "metadata"
    deps_args = ["deps", action, "--reconfigure", srcname, srctype]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        srctype=srctype,
        reconfigure=True,
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_sync(mock_deps_command):
    """Run deps add with sync

    - mock deps_command
    - check args
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "foo"
    srctype = "metadata"
    deps_args = ["deps", action, "--sync", srcname, srctype]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        srctype=srctype,
        sync=True,
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_sync_verify(mock_deps_command):
    """Run deps add with sync and verify options

    - mock deps_command
    - check args
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "foo"
    srctype = "metadata"
    deps_args = [
        "deps",
        action,
        srcname,
        srctype,
        "--sync",
        "--verify",
        "--verify-ignore-version",
        "--verify-exclude",
        "wheel$",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        srctype=srctype,
        sync=True,
        verify=True,
        verify_ignore_version=True,
        verify_excludes=["wheel$"],
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.parametrize(
    "verify_command",
    (["--verify"], ["--verify-exclude", "x$"], ["--verify-ignore-version"]),
    ids=lambda x: x[0],
)
def test_deps_cli_add_verify_without_sync(
    verify_command,
    capsys,
    mock_deps_command,
):
    """Run deps add with verify commands

    - mock deps_command
    - check error
    """
    action = "add"
    srcname = "foo"
    srctype = "metadata"
    deps_args = ["deps", action, srcname, srctype, *verify_command]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "--verify options on add must be used with --sync"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_sync_verify_drift_exits(mock_deps_command):
    """Run deps add with sync and failed verify

    - mock deps_command
    - raise DepsUnsyncedError
    - check exit code
    """
    action = "add"
    srcname = "foo"
    srctype = "metadata"
    mock_deps_command.side_effect = project_main.DepsUnsyncedError
    deps_args = ["deps", action, srcname, srctype, "--sync", "--verify"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.SYNC_VERIFY_ERROR


def test_deps_cli_add_sources_sync_verify_drift_exits(mock_deps_command):
    """Run deps add --sources with sync and failed verify

    - mock deps_command to raise DepsUnsyncedError (an out-of-sync entry)
    - check the --sources path maps it to the same exit code
    """
    action = "add"
    mock_deps_command.side_effect = project_main.DepsUnsyncedError
    deps_args = [
        "deps",
        action,
        "--sources",
        "a metadata;b metadata",
        "--sync",
        "--verify",
    ]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.SYNC_VERIFY_ERROR


@pytest.mark.parametrize(
    "verify_subcommand",
    (["--verify-exclude", "x$"], ["--verify-ignore-version"]),
    ids=lambda x: x[0],
)
def test_deps_cli_add_sync_verify_options_require_verify(
    verify_subcommand,
    mock_deps_command,
    capsys,
):
    """Run deps add with sync and verify-* without verify

    - mock deps_command
    - check error
    """
    action = "add"
    srcname = "foo"
    srctype = "metadata"
    deps_args = [
        "deps",
        action,
        srcname,
        srctype,
        "--sync",
        *verify_subcommand,
    ]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected = f"{verify_subcommand[0]} option must be used with --verify"
    assert expected in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_candidates(mock_deps_command):
    """Run deps add with --candidates

    - mock deps_command
    - check the ;-list is parsed to a tuple of (type, *args) tuples
    - check srctype is None (no positional type)
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "check"
    deps_args = [
        "deps",
        action,
        srcname,
        "--candidates",
        "pep735 test;pip_reqfile r.txt",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        candidates=(("pep735", "test"), ("pip_reqfile", "r.txt")),
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_candidates_lenient_parsing(mock_deps_command):
    """Run deps add with a sloppy but valid --candidates list

    - mock deps_command
    - blank entries (trailing ';', whitespace-only) are dropped
    - a multi-arg entry is split into (type, *args)
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "check"
    deps_args = [
        "deps",
        action,
        srcname,
        "--candidates",
        " pep735  test ; tox tox.ini testenv ;; pip_reqfile r.txt ; ",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        candidates=(
            ("pep735", "test"),
            ("tox", "tox.ini", "testenv"),
            ("pip_reqfile", "r.txt"),
        ),
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_candidates_reconfigure_sync_verify(mock_deps_command):
    """Run deps add --candidates composed with --reconfigure/--sync/--verify

    - mock deps_command
    - check all options are forwarded with the parsed candidates
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "check"
    deps_args = [
        "deps",
        action,
        srcname,
        "--candidates",
        "pep735 test;pep735 tests",
        "--reconfigure",
        "--sync",
        "--verify",
        "--verify-exclude",
        "pytest-cov",
        "flake8$",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=srcname,
        candidates=(("pep735", "test"), ("pep735", "tests")),
        reconfigure=True,
        sync=True,
        verify=True,
        verify_excludes=["pytest-cov", "flake8$"],
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_candidates_with_type_is_error(mock_deps_command, capsys):
    """Run deps add with both --candidates and a positional type

    - mock deps_command
    - check mutual-exclusion usage error
    """
    action = "add"
    srcname = "check"
    srctype = "metadata"
    deps_args = [
        "deps",
        action,
        srcname,
        srctype,
        "--candidates",
        "pep735 test",
    ]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = (
        "srctype positional is mutually exclusive with --candidates"
    )
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_requires_type_or_candidates(mock_deps_command, capsys):
    """Run deps add with neither a positional type nor --candidates

    - mock deps_command
    - check usage error
    """
    action = "add"
    srcname = "check"
    deps_args = ["deps", action, srcname]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "either srctype or --candidates is required"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_candidates_empty_is_error(mock_deps_command, capsys):
    """Run deps add with an empty --candidates list

    - mock deps_command
    - check usage error
    """
    action = "add"
    srcname = "check"
    candidates = " ; "
    deps_args = ["deps", action, srcname, "--candidates", candidates]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = f"no candidates parsed from {candidates!r}"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_candidates_unknown_type_is_error(
    mock_deps_command,
    capsys,
):
    """Run deps add with an unknown type in --candidates

    - mock deps_command
    - an unknown type is a malformed list -> usage error, not a silent skip
    """
    action = "add"
    srcname = "check"
    deps_args = [
        "deps",
        action,
        srcname,
        "--candidates",
        "pep735 test;bogus x",
    ]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "invalid candidate type: 'bogus'"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_candidates_no_candidate_reports_and_exits(
    mock_deps_command,
):
    """Run deps add --candidates when no candidate matches

    - mock deps_command to raise DepsNoCandidateError
    - check the dedicated exit code is used
    """
    action = "add"
    srcname = "check"
    mock_deps_command.side_effect = project_main.DepsNoCandidateError
    deps_args = ["deps", action, srcname, "--candidates", "pep735 test"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.ADD_NO_CANDIDATE_ERROR


def test_deps_cli_add_sources(mock_deps_command):
    """Run deps add with --sources

    - the ;-list is parsed to (name, type, *args) tuples
    - no positional name/type (srcname is None)
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = [
        "deps",
        action,
        "--sources",
        "a metadata;b pip_reqfile r.txt",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=None,
        sources=(("a", "metadata"), ("b", "pip_reqfile", "r.txt")),
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_sources_lenient_parsing(mock_deps_command):
    """Run deps add with a sloppy but valid --sources list

    - blank entries (trailing ';', whitespace-only) are dropped
    - a multi-arg entry is split into (name, type, *args)
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = [
        "deps",
        action,
        "--sources",
        " a metadata ; b tox tox.ini testenv ;; c pip_reqfile r.txt ; ",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=None,
        sources=(
            ("a", "metadata"),
            ("b", "tox", "tox.ini", "testenv"),
            ("c", "pip_reqfile", "r.txt"),
        ),
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_add_sources_reconfigure_sync_verify(mock_deps_command):
    """Run deps add --sources composed with --reconfigure/--sync/--verify

    - check all options are forwarded with the parsed sources
    """
    action = "add"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    deps_args = [
        "deps",
        action,
        "--sources",
        "a metadata;b metadata",
        "--reconfigure",
        "--sync",
        "--verify",
        "--verify-exclude",
        "excluded-dep",
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(
        DEFAULT_DEPS_ADD_CLI_KWARGS,
        srcname=None,
        sources=(("a", "metadata"), ("b", "metadata")),
        reconfigure=True,
        sync=True,
        verify=True,
        verify_excludes=["excluded-dep"],
    )

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


@pytest.mark.parametrize(
    "positionals",
    (["foo"], ["foo", "metadata"], ["foo", "metadata", "x"]),
    ids=("name", "name-type", "name-type-args"),
)
def test_deps_cli_add_sources_with_positional_is_error(
    mock_deps_command,
    capsys,
    positionals,
):
    """Run deps add with --sources and any positional -> usage error"""
    action = "add"
    deps_args = ["deps", action, *positionals, "--sources", "a metadata"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "--sources takes no positional name/type/args"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_sources_with_candidates_is_error(
    mock_deps_command,
    capsys,
):
    """Run deps add with both --sources and --candidates -> usage error"""
    action = "add"
    deps_args = [
        "deps",
        action,
        "--sources",
        "a metadata",
        "--candidates",
        "pep735 test",
    ]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "--sources is mutually exclusive with --candidates"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_sources_empty_is_error(mock_deps_command, capsys):
    """Run deps add with an empty --sources list -> usage error"""
    action = "add"
    sources = " ; "
    deps_args = ["deps", action, "--sources", sources]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = f"no sources parsed from {sources!r}"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_sources_name_without_type_is_error(
    mock_deps_command,
    capsys,
):
    """Run deps add with an entry that has only a name -> usage error"""
    action = "add"
    deps_args = ["deps", action, "--sources", "a metadata;loner"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "missing source type for 'loner'"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_sources_unknown_type_is_error(mock_deps_command, capsys):
    """Run deps add with an unknown type in --sources -> usage error"""
    action = "add"
    deps_args = ["deps", action, "--sources", "a metadata;b bogus"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "invalid source type for 'b': 'bogus'"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_sources_duplicate_name_is_error(
    mock_deps_command,
    capsys,
):
    """Run deps add with a name repeated within --sources -> usage error"""
    action = "add"
    deps_args = ["deps", action, "--sources", "a metadata;a pip_reqfile r.txt"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = "duplicate source name in a given list: 'a'"
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_add_requires_name(mock_deps_command, capsys):
    """Run deps add without a name and without --sources -> usage error

    The name positional is optional now (omitted with --sources), so a
    missing name in the positional/candidates modes is caught here.
    """
    action = "add"
    deps_args = ["deps", action, "--candidates", "pep735 test"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)
    assert exc.value.code == ExitCodes.WRONG_USAGE
    expected_message = (
        "srcname positional is required with --candidates or srctype"
    )
    assert expected_message in capsys.readouterr().err
    mock_deps_command.assert_not_called()


def test_deps_cli_delete_help(capsys):
    """Run deps delete --help

    - check msg and exit code
    """
    action = "delete"
    deps_args = ["deps", action, "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(deps_args)

    assert exc.value.code == ExitCodes.OK

    captured = capsys.readouterr()
    assert not captured.err
    expected_msg = f"usage: python -m pyproject_installer deps {action} "
    assert expected_msg in captured.out


def test_deps_cli_delete_default(mock_deps_command):
    """Run deps delete

    - mock deps_command
    - check default depsconfig path
    - check args
    """
    action = "delete"
    depsconfig = Path.cwd() / project_main.DEFAULT_CONFIG_NAME
    srcname = "foo"
    deps_args = ["deps", action, srcname]

    r_args = (action, Path(depsconfig))
    r_kwargs = {"srcname": srcname}

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_deps_cli_delete_depsconfig(mock_deps_command):
    """Run deps delete with specified depsconfig path

    - mock deps_command
    - check args
    """
    action = "delete"
    depsconfig = "foo.json"
    srcname = "foo"
    deps_args = ["deps", "--depsconfig", depsconfig, action, srcname]

    r_args = (action, Path(depsconfig))
    r_kwargs = {"srcname": srcname}

    project_main.main(deps_args)
    mock_deps_command.assert_called_once_with(*r_args, **r_kwargs)


def test_completion_cli(mock_completion_command):
    """Run completion with 'bash' argument"""
    shell = "bash"
    completion_args = ["completion", shell]
    project_main.main(completion_args)
    b_args = (shell,)
    b_kwargs: dict[str, Any] = {}
    mock_completion_command.assert_called_once_with(*b_args, **b_kwargs)


def test_completion_unsupported_shell(capsys):
    """Run completion with unsupported shell"""
    shell = "zsh"
    completion_args = ["completion", shell]
    with pytest.raises(SystemExit) as exc:
        project_main.main(completion_args, prog="pyproject-installer")
    assert exc.value.code == ExitCodes.WRONG_USAGE

    expected_err_msgs = invalid_choice_messages(
        shell,
        choices=project_main.SUPPORTED_SHELLS,
    )
    captured = capsys.readouterr()
    assert not captured.out
    assert any(True for msg in expected_err_msgs if msg in captured.err)


def test_completion_cli_help(capsys):
    """Run completion --help

    - check msg and exit code
    """
    completion_args = ["completion", "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(completion_args)

    assert exc.value.code == ExitCodes.OK

    captured = capsys.readouterr()
    assert not captured.err
    expected_msg = "usage: python -m pyproject_installer completion "
    assert expected_msg in captured.out


def test_cli_entry(mock_main, mock_run_autocomplete, monkeypatch, mocker):
    """
    Run cli_entry in non-completion mode.

    Expected results:
    - run_autocomplete is not called
    - main is called
    """
    monkeypatch.delenv("_PYPROJECT_INSTALLER_COMPLETE", raising=False)
    main_args = ["any"]
    mocker.patch.object(project_main.sys, "argv", ["any-prog", *main_args])
    project_main.cli_entry()
    b_args = main_args
    b_kwargs = {"prog": "pyproject-installer"}
    mock_run_autocomplete.assert_not_called()
    mock_main.assert_called_once_with(b_args, **b_kwargs)


def test_cli_entry_run_completion(
    mock_main,
    mock_run_autocomplete,
    monkeypatch,
    mocker,
):
    """
    Run cli_entry in completion mode.

    Expected results:
    - run_autocomplete is called
    - main is not called
    """
    monkeypatch.setenv("_PYPROJECT_INSTALLER_COMPLETE", "1")
    main_args = ["any"]
    mocker.patch.object(project_main.sys, "argv", ["any-prog", *main_args])
    with pytest.raises(SystemExit):
        project_main.cli_entry()
    mock_run_autocomplete.assert_called_once()
    mock_main.assert_not_called()

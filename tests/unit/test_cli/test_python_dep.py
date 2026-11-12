from pathlib import Path
from typing import Any

import pytest

from pyproject_installer import __main__ as project_main
from pyproject_installer.codes import ExitCodes


@pytest.fixture
def mock_python_dep_command(mocker):
    """Replace the Python dependency command to check parsed arguments."""
    return mocker.patch.object(project_main, "python_dep_command")


DEFAULT_PYTHON_DEP_SYNC_CLI_KWARGS: dict[str, Any] = {
    "verify": False,
}


DEFAULT_PYTHON_DEP_PRINT_CLI_KWARGS: dict[str, Any] = {
    "depformat": None,
}


def test_python_dep_cli_sync_default(mock_python_dep_command):
    """Run python_dep sync

    - mock python_dep_command
    - check default depsconfig argument
    - check args
    """
    action = "sync"
    depsconfig = None
    python_dep_args = ["python_dep", action]

    r_args = (action, depsconfig)
    r_kwargs = dict(DEFAULT_PYTHON_DEP_SYNC_CLI_KWARGS)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_sync_verify(mock_python_dep_command):
    """Run python_dep sync with verify

    - mock python_dep_command
    - check args
    """
    action = "sync"
    depsconfig = None
    python_dep_args = ["python_dep", action, "--verify"]

    r_args = (action, depsconfig)
    r_kwargs = dict(DEFAULT_PYTHON_DEP_SYNC_CLI_KWARGS, verify=True)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_sync_depsconfig(mock_python_dep_command):
    """Run python_dep sync with specified depsconfig path

    - mock python_dep_command
    - check args
    """
    action = "sync"
    depsconfig = "custom.json"
    python_dep_args = ["python_dep", "--depsconfig", depsconfig, action]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(DEFAULT_PYTHON_DEP_SYNC_CLI_KWARGS)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_print_default(mock_python_dep_command):
    """Run python_dep print

    - mock python_dep_command
    - check default depsconfig argument
    - check args
    """
    action = "print"
    depsconfig = None
    python_dep_args = ["python_dep", action]

    r_args = (action, depsconfig)
    r_kwargs = dict(DEFAULT_PYTHON_DEP_PRINT_CLI_KWARGS)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_print_specifier(mock_python_dep_command):
    """Run python_dep print with a specifier format

    - mock python_dep_command
    - check args
    """
    action = "print"
    depsconfig = None
    depformat = "python3 $specifier"
    python_dep_args = ["python_dep", action, "--format", depformat]

    r_args = (action, depsconfig)
    r_kwargs = dict(DEFAULT_PYTHON_DEP_PRINT_CLI_KWARGS, depformat=depformat)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_print_rpmlowver(mock_python_dep_command):
    """Run python_dep print with an RPM lower version format

    - mock python_dep_command
    - check args
    """
    action = "print"
    depsconfig = None
    depformat = "python3$rpmlowver"
    python_dep_args = ["python_dep", action, "--format", depformat]

    r_args = (action, depsconfig)
    r_kwargs = dict(DEFAULT_PYTHON_DEP_PRINT_CLI_KWARGS, depformat=depformat)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_print_escaped_specifier(mock_python_dep_command):
    """Run python_dep print with an escaped specifier in the format

    - mock python_dep_command
    - check args
    """
    action = "print"
    depsconfig = None
    depformat = "$$specifier$rpmlowver"
    python_dep_args = ["python_dep", action, "--format", depformat]

    r_args = (action, depsconfig)
    r_kwargs = dict(DEFAULT_PYTHON_DEP_PRINT_CLI_KWARGS, depformat=depformat)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_print_empty_format(mock_python_dep_command):
    """Run python_dep print with an empty format

    - mock python_dep_command
    - check args
    """
    action = "print"
    depsconfig = None
    depformat = ""
    python_dep_args = ["python_dep", action, "--format", depformat]

    r_args = (action, depsconfig)
    r_kwargs = dict(DEFAULT_PYTHON_DEP_PRINT_CLI_KWARGS, depformat=depformat)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_print_depsconfig(mock_python_dep_command):
    """Run python_dep print with specified depsconfig path and format

    - mock python_dep_command
    - check args
    """
    action = "print"
    depsconfig = "custom.json"
    depformat = "python3"
    python_dep_args = [
        "python_dep",
        "--depsconfig",
        depsconfig,
        action,
        "--format",
        depformat,
    ]

    r_args = (action, Path(depsconfig))
    r_kwargs = dict(DEFAULT_PYTHON_DEP_PRINT_CLI_KWARGS, depformat=depformat)

    project_main.main(python_dep_args)
    mock_python_dep_command.assert_called_once_with(*r_args, **r_kwargs)


def test_python_dep_cli_sync_verify_fail(mock_python_dep_command):
    """Run python_dep sync with failed verify

    - mock python_dep_command
    - raise DepsUnsyncedError
    - check exit code
    """
    action = "sync"
    mock_python_dep_command.side_effect = project_main.DepsUnsyncedError
    python_dep_args = ["python_dep", action, "--verify"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(python_dep_args)

    actual_code = exc.value.code
    expected_code = ExitCodes.SYNC_VERIFY_ERROR
    assert actual_code == expected_code


def test_python_dep_cli_conflicting_format(capsys):
    """Run python_dep print with conflicting format substitutions

    - check msg and exit code
    """
    action = "print"
    depformat = "python3 $specifier$rpmlowver"
    python_dep_args = ["python_dep", action, "--format", depformat]

    with pytest.raises(SystemExit) as exc:
        project_main.main(python_dep_args)

    actual_code = exc.value.code
    expected_code = ExitCodes.WRONG_USAGE
    assert actual_code == expected_code
    actual_output = capsys.readouterr()
    assert not actual_output.out
    expected_msg = "$specifier and $rpmlowver"
    assert expected_msg in actual_output.err


def test_python_dep_cli_help(capsys):
    """Run python_dep --help

    - check msg and exit code
    """
    python_dep_args = ["python_dep", "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(python_dep_args)

    actual_code = exc.value.code
    expected_code = ExitCodes.OK
    assert actual_code == expected_code
    actual_output = capsys.readouterr()
    assert not actual_output.err
    expected_msg = "usage: python -m pyproject_installer python_dep "
    assert expected_msg in actual_output.out


def test_python_dep_cli_sync_help(capsys):
    """Run python_dep sync --help

    - check msg and exit code
    """
    action = "sync"
    python_dep_args = ["python_dep", action, "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(python_dep_args)

    actual_code = exc.value.code
    expected_code = ExitCodes.OK
    assert actual_code == expected_code
    actual_output = capsys.readouterr()
    assert not actual_output.err
    expected_msg = f"usage: python -m pyproject_installer python_dep {action} "
    assert expected_msg in actual_output.out


def test_python_dep_cli_print_help(capsys):
    """Run python_dep print --help

    - check msg and exit code
    """
    action = "print"
    python_dep_args = ["python_dep", action, "--help"]

    with pytest.raises(SystemExit) as exc:
        project_main.main(python_dep_args)

    actual_code = exc.value.code
    expected_code = ExitCodes.OK
    assert actual_code == expected_code
    actual_output = capsys.readouterr()
    assert not actual_output.err
    expected_msg = f"usage: python -m pyproject_installer python_dep {action} "
    assert expected_msg in actual_output.out

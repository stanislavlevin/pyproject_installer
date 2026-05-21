"""Tests for completion_cmd/__init__.py."""

import pytest

from pyproject_installer.completion_cmd import (
    SUPPORTED_SHELLS,
    completion_command,
)


def test_completion_command_unsupported_shell() -> None:
    """Dispatcher raises ValueError for unknown shells."""
    shell = "nonexistent_shell"
    with pytest.raises(ValueError, match=f"unsupported shell: '{shell}'"):
        completion_command(shell)


@pytest.mark.parametrize("shell", SUPPORTED_SHELLS)
def test_completion_command_supported_shell(
    shell: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dispatcher accepts supported shells and emits completion on stdout"""
    completion_command(shell)
    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out

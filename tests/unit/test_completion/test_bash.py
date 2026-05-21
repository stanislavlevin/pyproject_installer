"""Tests for completion_cmd/_bash.py.

The bash emitter is a fixed string literal targeting the
``pyproject-installer`` console script; these tests verify the
wrapper shape. The runtime dispatch logic lives in _autocomplete.py
and is tested in test_autocomplete.py.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pyproject_installer.completion_cmd import _bash


@pytest.fixture(scope="session")
def bash_completion():
    return subprocess.check_output(
        [sys.executable, "-m", "pyproject_installer", "completion", "bash"],
        text=True,
    )


def test_completion_content(bash_completion) -> None:
    """Check the content of generated completion"""
    assert bash_completion == _bash.SCRIPT_TEMPLATE


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
def test_completion_is_sourceable_in_bash(
    bash_completion,
    tmp_path: Path,
) -> None:
    """The generated script must source cleanly and register completion."""
    script = tmp_path / "wrapper.bash"
    script.write_text(bash_completion)
    cmd_str = f"source {script} && complete -p pyproject-installer"
    cmd = ["bash", "-c", cmd_str]
    completion_function = subprocess.check_output(cmd, text=True)
    expected = (
        "complete -o nosort -F _pyproject_installer pyproject-installer\n"
    )
    assert expected == completion_function

import subprocess
from collections.abc import Sequence
from pathlib import Path

from pyproject_installer.errors import RunCommandEnvError

from ._run_env import PyprojectVenv

__all__ = ["run_command"]


def run_command(
    wheel: str | Path,
    *,
    command: Sequence[str],
    venv_name: str = ".run_venv",
    capture_output: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    try:
        run_env = PyprojectVenv(wheel)
        run_env.create(venv_name)
    except RunCommandEnvError:
        raise
    except Exception as e:
        raise RunCommandEnvError(str(e)) from e
    return run_env.run(command, capture_output=capture_output)

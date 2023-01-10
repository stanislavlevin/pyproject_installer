from pyproject_installer.errors import RunCommandEnvError
from ._run_env import PyprojectVenv


__all__ = ["run_command"]


def run_command(wheel, *args, venv_name=".run_venv", **kwargs):
    try:
        run_env = PyprojectVenv(wheel)
        run_env.create(venv_name)
    except RunCommandEnvError:
        raise
    except Exception as e:
        raise RunCommandEnvError(str(e)) from e
    return run_env.run(*args, **kwargs)

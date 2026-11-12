"""Run commands for the project's Python version constraint."""

from pathlib import Path
from typing import Any

from .deps_config import PythonDepConfig


def python_dep_command(
    action: str,
    depsconfig: str | Path | None,
    **kwargs: Any,
) -> None:
    """Run a Python dependency action using the selected or default config."""
    config = PythonDepConfig(depsconfig)
    getattr(config, action)(**kwargs)

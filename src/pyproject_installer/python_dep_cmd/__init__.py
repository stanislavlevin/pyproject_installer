"""Collect, verify, and print the project's Python version constraint."""

from ._python_dep_command import python_dep_command
from .deps_config import PythonDepConfig

validate_format = PythonDepConfig.validate_format

__all__ = ["python_dep_command", "validate_format"]

from pathlib import Path
import sys

from .parser import Parser
from ...build_cmd._build import call_hook


class Pep517Parser(Parser):
    """Calls get_requires_for_build_wheel in cwd according to PEP517"""
    name = "pep517"

    def parse(self):
        return call_hook(
            python=sys.executable,
            srcdir=Path.cwd(),
            verbose=False,
            hook="get_requires_for_build_wheel",
        )["result"]

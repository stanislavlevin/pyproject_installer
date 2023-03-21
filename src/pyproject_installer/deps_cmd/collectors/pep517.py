from pathlib import Path
import sys

from packaging.requirements import Requirement, InvalidRequirement

from .collector import Collector
from ...build_cmd._build import call_hook


class Pep517Collector(Collector):
    """Calls get_requires_for_build_wheel in cwd according to PEP517"""
    name = "pep517"

    def collect(self):
        for req in call_hook(
            python=sys.executable,
            srcdir=Path.cwd(),
            verbose=False,
            hook="get_requires_for_build_wheel",
        )["result"]:
            try:
                Requirement(req)
            except InvalidRequirement:
                continue
            else:
                yield req

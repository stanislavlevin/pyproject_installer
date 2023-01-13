from pathlib import Path

from .collector import Collector
from ...lib import requirements
from ...lib.build_backend import parse_build_system_spec


class Pep518Collector(Collector):
    """Collect build requires from cwd/pyproject.toml on cwd according to PEP518

    Specification:
    https://peps.python.org/pep-0518/#specification
    """

    name = "pep518"

    def collect(self):
        build_system = parse_build_system_spec(Path.cwd())

        for req in build_system["requires"]:
            try:
                requirements.Requirement(req)
            except requirements.InvalidRequirement:
                continue
            else:
                yield req

from pathlib import Path

from ...lib import is_pep508_requirement
from ...lib.build_backend import parse_build_system_spec
from .collector import Collector


class Pep518Collector(Collector):
    """Collect build requires from cwd/pyproject.toml on cwd according to PEP518

    Specification:
    https://peps.python.org/pep-0518/#specification
    """

    name = "pep518"

    def collect(self):
        build_system = parse_build_system_spec(Path.cwd())

        for req in build_system["requires"]:
            if not is_pep508_requirement(req):
                err_msg = (
                    f"{self.name}: invalid PEP508 Dependency Specifier: {req}"
                )
                raise ValueError(err_msg) from None
            yield req

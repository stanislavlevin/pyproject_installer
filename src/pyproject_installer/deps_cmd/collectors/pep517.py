import sys
from pathlib import Path

from ...lib import is_pep508_requirement
from ...lib.build_backend import backend_hook
from .collector import Collector


class Pep517Collector(Collector):
    """Collect dependencies required to build wheel from cwd according to PEP517

    Specification:
    - `get_requires_for_build_wheel`:
      https://peps.python.org/pep-0517/#get-requires-for-build-wheel
    """

    name = "pep517"

    def collect(self):
        for req in backend_hook(
            python=sys.executable,
            srcdir=Path.cwd(),
            verbose=False,
            hook="get_requires_for_build_wheel",
        )["result"]:
            if not is_pep508_requirement(req):
                err_msg = (
                    f"{self.name}: invalid PEP508 Dependency Specifier: {req}"
                )
                raise ValueError(err_msg) from None
            yield req

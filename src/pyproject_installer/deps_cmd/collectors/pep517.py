from pathlib import Path
import sys

from .collector import Collector
from ...lib import requirements
from ...lib.build_backend import backend_hook


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
            try:
                requirements.Requirement(req)
            except requirements.InvalidRequirement:
                continue
            else:
                yield req

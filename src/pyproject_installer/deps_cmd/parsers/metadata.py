from importlib.metadata import PathDistribution
from pathlib import Path
import sys

from packaging.requirements import Requirement
from packaging.markers import Marker, default_environment, _evaluate_markers

from .parser import Parser
from ...lib.wheel import WheelFile


class MetadataParser(Parser):
    """Parse METADATA of wheel

    - build a wheel in cwd if it was not specified
    """
    name = "metadata"

    def __init__(self, wheel=None):
        super().__init__()
        self.wheel = wheel if wheel is None else Path(wheel)

    def parse(self):
        # TODO: support for build wheel
        if self.wheel is None:
            raise ValueError("Currently unsupported wheel option")

        parsed_reqs = []
        with WheelFile(self.wheel) as whl:
            distr = PathDistribution(whl.dist_info)

            for req in distr.requires:
                parsed_req = Requirement(req)
                parsed_reqs.append(req)
        return parsed_reqs

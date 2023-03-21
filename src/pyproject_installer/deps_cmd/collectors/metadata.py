from importlib.metadata import PathDistribution
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

from packaging.requirements import Requirement
from packaging.markers import Marker, default_environment, _evaluate_markers

from .collector import Collector
from ...build_cmd._build import call_hook
from ...lib.wheel import WheelFile


class MetadataCollector(Collector):
    """Parse METADATA of wheel

    - calls `prepare_metadata_for_build_wheel` (all required build deps should
      be installed)
    - parses produced metadata
    """
    name = "metadata"

    def collect(self):
        with TemporaryDirectory() as tmpdir:
            distinfo_dir = call_hook(
                python=sys.executable,
                srcdir=Path.cwd(),
                verbose=False,
                hook="prepare_metadata_for_build_wheel",
                hook_args=[((tmpdir),), {}]
            )["result"]
            if distinfo_dir == "":
                raise ValueError(
                    "Backend doesn't support prepare_metadata_for_build_wheel "
                    "hook"
                )

            distr = PathDistribution(Path(tmpdir) / distinfo_dir)
            for req in distr.requires:
                parsed_req = Requirement(req)
                yield req

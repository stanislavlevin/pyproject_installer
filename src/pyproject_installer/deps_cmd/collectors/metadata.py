from pathlib import Path
from tempfile import TemporaryDirectory
import email
import sys


from .collector import Collector
from ...lib import requirements
from ...lib.build_backend import backend_hook


class MetadataCollector(Collector):
    """Build wheel's METADATA for project on cwd and parse it

    Specification:
    - `prepare_metadata_for_build_wheel`:
      https://peps.python.org/pep-0517/#prepare-metadata-for-build-wheel
    - core metadata (2.1+):
      https://packaging.python.org/en/latest/specifications/core-metadata/
      https://packaging.python.org/en/latest/specifications/core-metadata/#requires-dist-multiple-use
    """

    name = "metadata"

    def collect(self):
        hook_name = "prepare_metadata_for_build_wheel"
        with TemporaryDirectory() as tmpdir:
            distinfo_dir = backend_hook(
                python=sys.executable,
                srcdir=Path.cwd(),
                verbose=False,
                hook=hook_name,
                hook_args=[((tmpdir),), {}],
            )["result"]
            if distinfo_dir == "":
                raise ValueError(f"Backend doesn't support {hook_name} hook")

            metadata_path = Path(tmpdir) / distinfo_dir / "METADATA"
            metadata_text = metadata_path.read_text(encoding="utf-8")
            msg = email.message_from_string(metadata_text)
            requires = msg.get_all("Requires-Dist", [])
            for req in requires:
                try:
                    requirements.Requirement(req)
                except requirements.InvalidRequirement:
                    continue
                else:
                    yield req

from pathlib import Path
from tempfile import TemporaryDirectory
import email


from .collector import Collector
from ...build_cmd import build_metadata
from ...lib import requirements


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
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            metadata_filename = build_metadata(Path.cwd(), outdir=tmp_path)
            metadata_path = tmp_path / metadata_filename
            metadata_text = metadata_path.read_text(encoding="utf-8")
        metadata_email = email.message_from_string(metadata_text)
        requires = metadata_email.get_all("Requires-Dist", [])
        for req in requires:
            try:
                requirements.Requirement(req)
            except requirements.InvalidRequirement:
                continue
            else:
                yield req

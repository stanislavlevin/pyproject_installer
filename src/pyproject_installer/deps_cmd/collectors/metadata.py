import email
from collections.abc import Iterator
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory

from ...build_cmd import build_metadata
from ...lib import is_pep508_requirement
from .collector import Collector


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

    def parsed_metadata(self) -> Message:
        """Build the project's core metadata on cwd and parse it once."""
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            metadata_filename = build_metadata(
                Path.cwd(),
                outdir=tmp_path,
            )
            metadata_path = tmp_path / metadata_filename
            metadata_text = metadata_path.read_text(encoding="utf-8")
        return email.message_from_string(metadata_text)

    def iter_requires(self, metadata: Message) -> Iterator[str]:
        """Parse and validate Requires-Dist from parsed metadata."""
        requires = metadata.get_all("Requires-Dist", [])
        for req in requires:
            if not is_pep508_requirement(req):
                err_msg = (
                    f"{self.name}: invalid PEP508 Dependency Specifier: {req}"
                )
                raise ValueError(err_msg) from None
            yield req

    def collect(self) -> Iterator[str]:
        yield from self.iter_requires(self.parsed_metadata())

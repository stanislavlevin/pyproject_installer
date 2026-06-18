import logging
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

from ...build_cmd import build_metadata
from ...lib import errors
from ...lib import metadata as core_metadata
from .collector import Collector

logger = logging.getLogger(__name__)


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

    # Built metadata cache, under the tree it was built from; delete to
    # force a rebuild.
    cache_path = Path("dist") / "metadata_cache"

    def parsed_metadata(self) -> core_metadata.Metadata:
        """Build the project's core metadata on cwd, cache it, and validate it.

        The metadata text is cached in ``dist/metadata_cache`` under the
        current working directory. If the cache is present it is read
        as-is and no build runs; otherwise the metadata is built the
        usual way (``prepare_metadata_for_build_wheel``, falling back to
        ``build_wheel``). Either way it is fully validated into a
        ``packaging.metadata.Metadata``, and a freshly built one is
        written to the cache only after it validates -- so invalid
        metadata is neither cached nor returned, whether it came from a
        build or a tampered cache file.
        """
        cache_path = Path.cwd() / self.cache_path
        if cache_path.is_file():
            logger.debug("Using cached metadata %s", cache_path)
            metadata_text = cache_path.read_text(encoding="utf-8")
            cached = True
        else:
            with TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                metadata_filename = build_metadata(
                    Path.cwd(),
                    outdir=tmp_path,
                )
                metadata_path = tmp_path / metadata_filename
                metadata_text = metadata_path.read_text(encoding="utf-8")
            cached = False

        metadata = self.validate_metadata(metadata_text)

        if not cached:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(metadata_text, encoding="utf-8")
            logger.debug("Cached metadata %s", cache_path)

        return metadata

    def validate_metadata(self, metadata_text: str) -> core_metadata.Metadata:
        """Fully validate the core metadata into a ``Metadata``.

        ``packaging.metadata`` validates every field against the core
        metadata specification and raises an ``ExceptionGroup`` of
        ``InvalidMetadata``; flatten it into one ``ValueError`` under
        this source's name so the existing error contract is kept.
        """
        try:
            return core_metadata.Metadata.from_email(
                metadata_text,
                validate=True,
            )
        except errors.ExceptionGroup as exc_group:
            detail = "; ".join(str(exc) for exc in exc_group.exceptions)
            err_msg = f"{self.name}: invalid core metadata: {detail}"
            raise ValueError(err_msg) from None

    def iter_requires(self, metadata: core_metadata.Metadata) -> Iterator[str]:
        """Yield Requires-Dist from the validated metadata."""
        yield from map(str, metadata.requires_dist or [])

    def collect(self) -> Iterator[str]:
        yield from self.iter_requires(self.parsed_metadata())

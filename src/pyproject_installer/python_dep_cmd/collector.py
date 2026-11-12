"""Collect and validate metadata for Python version constraints."""

from collections.abc import Iterator

from ..deps_cmd.collectors.metadata import MetadataCollector


class MetadataPythonCollector(MetadataCollector):
    """Collect metadata and report validation errors under python_dep."""

    name = "python_dep"

    def collect(self) -> Iterator[str]:
        """Yield normalized Requires-Python when it restricts versions."""
        requires_python = self.parsed_metadata().requires_python
        if requires_python:
            yield str(requires_python)

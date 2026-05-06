from collections.abc import Iterator
from pathlib import Path

from ...lib import dependency_groups, errors, requirements, tomllib
from .collector import Collector


class Pep735Collector(Collector):
    """Collect dependencies specified by Dependency Group according to PEP735.

    Parsing, name normalization, include resolution, cycle detection, and
    PEP 508 validation are delegated to packaging.dependency_groups.

    Specification:
    - https://peps.python.org/pep-0735/#specification
    """

    name = "pep735"

    def __init__(self, group: str) -> None:
        # group name can be non-normalized
        self.group = group

    def collect(self) -> Iterator[str]:
        pyproject_file = Path.cwd() / "pyproject.toml"

        with pyproject_file.open("rb") as f:
            pyproject_data = tomllib.load(f)

        table_name = "dependency-groups"
        try:
            groups_data = pyproject_data[table_name]
        except KeyError:
            raise ValueError(
                f"{self.name}: missing {table_name} table in "
                f"{pyproject_file.name}",
            ) from None

        if not isinstance(groups_data, dict):
            raise TypeError(
                f"{self.name}: Dependency Groups is not a dict: "
                f"{groups_data!r}",
            )

        try:
            yield from dependency_groups.resolve_dependency_groups(
                groups_data,
                self.group,
            )
        except errors.ExceptionGroup as eg:
            # Packaging's resolver accumulates per-item errors and
            # surfaces them as a single ExceptionGroup, so one bad
            # config may carry several inner exceptions. Re-raise
            # as a fresh group with our prefix on the outer
            # message; inner exceptions are preserved as-is.
            raise errors.ExceptionGroup(
                f"{self.name}: {eg.message}",
                eg.exceptions,
            ) from None
        except requirements.InvalidRequirement as e:
            raise ValueError(f"{self.name}: {e}") from None
        except TypeError as e:
            # Raised when an `include-group` value is not a string:
            # packaging propagates this raw rather than collecting
            # it into the ExceptionGroup above.
            raise TypeError(f"{self.name}: {e}") from None

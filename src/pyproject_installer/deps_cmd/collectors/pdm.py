from pathlib import Path

from .collector import Collector
from ...lib import requirements
from ...lib import tomllib


class PdmCollector(Collector):
    """Parses pdm's dependencies from its configuration

    Specification:
    - https://pdm.fming.dev/latest/usage/dependency/#add-development-only-dependencies

    Limitations:
    - supported only PEP508 requirements
    """

    name = "pdm"

    def __init__(self, group):
        self.group = group

    def collect(self):
        pyproject_file = Path.cwd() / "pyproject.toml"

        with pyproject_file.open("rb") as f:
            pyproject_data = tomllib.load(f)

        try:
            deps_data = pyproject_data["tool"]["pdm"]["dev-dependencies"]
        except KeyError:
            raise ValueError(
                "Pdm: missing tool.pdm.dev-dependencies table in "
                f"{pyproject_file.name}"
            ) from None

        try:
            deps = deps_data[self.group]
        except KeyError:
            raise ValueError(
                f"Pdm dependencies are not configured for group: {self.group}"
            ) from None

        for line in deps:
            line = line.strip()
            try:
                requirements.Requirement(line)
            except requirements.InvalidRequirement:
                continue
            else:
                yield line

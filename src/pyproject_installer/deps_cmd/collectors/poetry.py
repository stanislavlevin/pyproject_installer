from pathlib import Path

from packaging.markers import Marker, InvalidMarker
from packaging.requirements import Requirement, InvalidRequirement
from packaging.specifiers import SpecifierSet, InvalidSpecifier

from .collector import Collector

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from ...build_cmd._vendor import tomli as tomllib


class PoetryCollector(Collector):
    """Parses poetry dependencies

    - format:
      https://python-poetry.org/docs/dependency-specification/
      https://python-poetry.org/docs/managing-dependencies/

    - limitations:
      - poetry version format is not fully compatible with PEP440
      - `python` field is ignored
    """
    name = "poetry"

    def __init__(self, group):
        self.group = group

    def collect(self):
        pyproject_file = Path.cwd() / "pyproject.toml"

        with pyproject_file.open("rb") as f:
            pyproject_data = tomllib.load(f)

        poetry_data = pyproject_data["tool"]["poetry"]
        try:
            dependencies = poetry_data["group"][self.group]["dependencies"]
        except KeyError:
            if self.group == "dev":
                # Poetry < 1.2.0
                dependencies = poetry_data["dev-dependencies"]
            else:
                raise

        for req_name, req_spec in dependencies.items():
            try:
                Requirement(req_name)
            except InvalidRequirement:
                continue
            req_line = req_name

            if isinstance(req_spec, str):
                # poetry version format is not fully compatible with PEP440
                try:
                    SpecifierSet(req_spec)
                except InvalidSpecifier:
                    # unsupported version format
                    pass
                else:
                    req_line += req_spec
            elif isinstance(req_spec, dict):
                version = req_spec.get("version")
                if version is not None:
                    # poetry version format is not fully compatible with PEP440
                    try:
                        SpecifierSet(version)
                    except InvalidSpecifier:
                        # unsupported version format
                        pass
                    else:
                        req_line += version

                markers = req_spec.get("markers")
                if markers is not None:
                    try:
                        Marker(markers)
                    except InvalidMarker:
                        pass
                    else:
                        req_line += ";" + markers

            # make sure that produced req line is correct PEP508 requirement
            Requirement(req_line)
            yield req_line

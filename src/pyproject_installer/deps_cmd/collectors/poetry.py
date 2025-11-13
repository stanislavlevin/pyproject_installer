from pathlib import Path

from ...lib import is_pep508_requirement, markers, tomllib
from .collector import Collector

PEP508_ENV_MARK_SEP = ";"


class PoetryCollector(Collector):
    """Collect poetry dependencies in cwd/pyproject.toml

    Specification:
    -  https://python-poetry.org/docs/dependency-specification/
    -  https://python-poetry.org/docs/managing-dependencies/

    Limitations:
    - poetry version format is not compatible with PEP440
    - `python` field is ignored
    """

    name = "poetry"

    def __init__(self, group):
        self.group = group

    def collect(self):
        pyproject_file = Path.cwd() / "pyproject.toml"

        with pyproject_file.open("rb") as f:
            pyproject_data = tomllib.load(f)

        try:
            poetry_data = pyproject_data["tool"]["poetry"]
        except KeyError:
            raise ValueError(
                "Poetry is not configured: missing tool.poetry",
            ) from None

        if "group" in poetry_data and self.group in poetry_data["group"]:
            # dependencies is mandatory property
            if "dependencies" not in poetry_data["group"][self.group]:
                raise ValueError(
                    f"Dependencies are not configured for {self.group}: "
                    f"missing tool.poetry.group.{self.group}.dependencies",
                )
            dependencies = poetry_data["group"][self.group]["dependencies"]
        elif self.group == "dev":
            # Poetry < 1.2.0
            dependencies = poetry_data.get("dev-dependencies", [])
        else:
            raise ValueError(
                f"{self.group} is not configured: "
                f"missing tool.poetry.group.{self.group}",
            )

        for req_name, req_spec in dependencies.items():
            if not is_pep508_requirement(req_name):
                continue
            req_line = req_name

            if isinstance(req_spec, dict):
                req_markers = req_spec.get("markers")
                if req_markers is not None:
                    try:
                        markers.Marker(req_markers)
                    except markers.InvalidMarker:
                        pass
                    else:
                        req_line += PEP508_ENV_MARK_SEP + req_markers

            # make sure that produced req line is correct PEP508 requirement
            if not is_pep508_requirement(req_line):
                err_msg = (
                    f"{self.name}: invalid PEP508 Dependency Specifier: "
                    f"{req_line}"
                )
                raise ValueError(err_msg) from None
            yield req_line

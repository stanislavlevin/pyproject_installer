from pathlib import Path

from .collector import Collector
from ...lib import requirements, markers
from ...lib import tomllib


class PipenvCollector(Collector):
    """Parses pipenv's dependencies from its configuration

    Specification:
    - https://pipenv.pypa.io/en/latest/pipfile.html
    - https://pipenv.pypa.io/en/latest/specifiers.html

    Limitations:
    - standalone PEP 508 specifiers as keys are not supported
    """

    name = "pipenv"

    def __init__(self, pipfile, category):
        self.pipfile = Path(pipfile)
        self.category = category

    def collect(self):
        with self.pipfile.open("rb") as f:
            pipfile_data = tomllib.load(f)

        try:
            deps = pipfile_data[self.category]
        except KeyError:
            raise ValueError(
                "pipenv dependencies are not configured for category: "
                f"{self.category}"
            ) from None

        for req_name, req_spec in deps.items():
            try:
                requirements.Requirement(req_name)
            except requirements.InvalidRequirement:
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
                        req_line += ";" + req_markers

            # make sure that produced req line is correct PEP508 requirement
            requirements.Requirement(req_line)
            yield req_line

from pathlib import Path

from packaging.requirements import Requirement

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from ...build_cmd._vendor import tomli as tomllib
from .collector import Collector


class Pep518Collector(Collector):
    """Parses pyproject.toml in cwd according to PEP518"""
    name = "pep518"

    def collect(self):
        pyproject_file = Path.cwd() / "pyproject.toml"
        default_requires = ["setuptools", "wheel"]

        if not pyproject_file.is_file():
            return default_requires

        with pyproject_file.open("rb") as f:
            pyproject_data = tomllib.load(f)

        build_system = pyproject_data.get("build-system")

        if build_system is None:
            return default_requires

        try:
            requires = build_system["requires"]
        except KeyError:
            raise KeyError(
                f"Missing mandatory build-system.requires in {pyproject_file}"
            ) from None

        # requires: list of strings
        if not isinstance(requires, list):
            raise TypeError(
                f"requires should be a list of strings, given: {requires!r}"
            )

        for req in requires:
            if not isinstance(req, str):
                raise TypeError(
                    f"requires should be a list of strings, given: {requires!r}"
                )
            parsed_req = Requirement(req)
            yield req

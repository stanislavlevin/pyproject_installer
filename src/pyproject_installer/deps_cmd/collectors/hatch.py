from pathlib import Path

from .collector import Collector
from ...lib import requirements
from ...lib import tomllib


class HatchCollector(Collector):
    """Parses hatch's dependencies from its configuration

    Specification:
    - https://hatch.pypa.io/latest/config/environment/overview/#dependencies
    - config reference:
      https://hatch.pypa.io/latest/intro/#configuration

    Limitations:
    - supported only PEP508 requirements (dependencies and extra-dependencies)
    - env inheritance is not supported
    - context formatting is not supported
    - features(extra) is not supported
    """

    name = "hatch"

    def __init__(self, hatchconfig, hatchenv):
        self.hatchconfig = Path(hatchconfig)
        self.hatchenv = hatchenv

    def _hatchenv_data(self):
        with self.hatchconfig.open("rb") as f:
            hatch_data = tomllib.load(f)
        if self.hatchconfig.name == "pyproject.toml":
            try:
                env_data = hatch_data["tool"]["hatch"]["envs"][self.hatchenv]
            except KeyError:
                raise ValueError(
                    f"Hatch: missing tool.hatch.envs.{self.hatchenv} table in "
                    f"{self.hatchconfig.name}"
                ) from None
        else:
            # hatch.toml or custom config
            try:
                env_data = hatch_data["envs"][self.hatchenv]
            except KeyError:
                raise ValueError(
                    f"Hatch: missing envs.{self.hatchenv} table in "
                    f"{self.hatchconfig.name}"
                ) from None
        return env_data

    def collect(self):
        data = self._hatchenv_data()
        try:
            deps = data["dependencies"]
        except KeyError:
            try:
                deps = data["extra-dependencies"]
            except KeyError:
                raise ValueError(
                    f"Hatch dependencies are not configured for {self.hatchenv}"
                    f": missing {self.hatchenv}.dependencies and "
                    f"{self.hatchenv}.extra-dependencies"
                ) from None

        for line in deps:
            line = line.strip()
            try:
                requirements.Requirement(line)
            except requirements.InvalidRequirement:
                continue
            else:
                yield line

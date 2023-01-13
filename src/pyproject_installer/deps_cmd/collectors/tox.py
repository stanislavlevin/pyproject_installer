from configparser import ConfigParser
from pathlib import Path

from .collector import Collector
from ...lib import requirements
from ...lib import tomllib


class ToxCollector(Collector):
    """Parses tox' dependencies from tox configuration

    Specification:
    - https://tox.wiki/en/latest/config.html#deps
    - config formats:
      https://tox.wiki/en/latest/config.html#discovery-and-file-types

    Limitations:
    - supported only PEP508 requirements
    - config substitutions are not supported
    - testenv inheritance is not supported
    - pip's req files or options are not supported
    """

    name = "tox"

    def __init__(self, toxconfig, testenv):
        self.toxconfig = Path(toxconfig)
        self.testenv = testenv

    def _tox_config(self):
        config = ConfigParser(interpolation=None)
        if self.toxconfig.suffix in (".toml",):
            # pyproject.toml
            with self.toxconfig.open("rb") as f:
                pyproject_data = tomllib.load(f)
            try:
                tox_data = pyproject_data["tool"]["tox"]["legacy_tox_ini"]
            except KeyError:
                raise ValueError(
                    "Tox is not configured: missing tool.tox.legacy_tox_ini"
                ) from None

            config.read_string(tox_data)
        else:
            # setup.cfg or tox.ini
            with self.toxconfig.open(encoding="utf-8") as f:
                config.read_file(f)
        return config

    def collect(self):
        config = self._tox_config()
        try:
            testenv = config[self.testenv]
        except KeyError:
            raise ValueError(
                f"Test environment is not configured: {self.testenv}"
            ) from None
        try:
            deps = testenv["deps"]
        except KeyError:
            raise ValueError(
                f"Dependencies are not configured for {self.testenv}: "
                f"missing {self.testenv}.deps"
            ) from None

        for line in deps.splitlines():
            line = line.strip()
            try:
                requirements.Requirement(line)
            except requirements.InvalidRequirement:
                continue
            else:
                yield line

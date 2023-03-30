from configparser import ConfigParser
from pathlib import Path

from packaging.requirements import Requirement, InvalidRequirement

from .collector import Collector

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from ...build_cmd._vendor import tomli as tomllib


class ToxCollector(Collector):
    """Parses tox' dependencies

    - deps format:
      https://tox.wiki/en/latest/config.html#deps
    - config formats:
      https://tox.wiki/en/latest/config.html#discovery-and-file-types
    - limitations:
      - supported only PEP508 requirements
      - config substitutions are no supported
      - pip's req files are not included (use PipReqFileCollector for that)
    """
    name = "tox"

    def __init__(self, toxconfig, toxsection):
        self.toxconfig = Path(toxconfig)
        self.toxsection = toxsection

    def _tox_config(self):
        config = ConfigParser(interpolation=None)
        if self.toxconfig.suffix in (".toml",):
            with self.toxconfig.open("rb") as f:
                pyproject_data = tomllib.load(f)
            tox_data = pyproject_data["tool"]["tox"]["legacy_tox_ini"]
            config.read_string(tox_data)
        else:
            with self.toxconfig.open(encoding="utf-8") as f:
                config.read_file(f)
        return config

    def collect(self):
        config = self._tox_config()
        deps = config[self.toxsection]["deps"].splitlines()

        for line in deps:
            line = line.strip()
            try:
                Requirement(line)
            except InvalidRequirement:
                continue
            else:
                yield line

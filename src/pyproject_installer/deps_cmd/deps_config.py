from copy import deepcopy
from pathlib import Path
from string import Template
import json
import re
import sys

from .collectors import get_collector
from ..errors import DepsUnsyncedError, DepsSourcesConfigError
from ..lib import requirements
from ..lib.normalization import pep503_normalized_name


DEFAULT_CONFIG_NAME = "pyproject_deps.json"


def get_identifiers(template):
    """Compat get_identifiers (added in Python 3.11)"""
    if hasattr(template, "get_identifiers"):
        return template.get_identifiers()

    # taken from CPython 3.11
    ids = []
    for mo in template.pattern.finditer(template.template):
        named = mo.group("named") or mo.group("braced")
        if named is not None and named not in ids:
            ids.append(named)
        elif (
            named is None
            and mo.group("invalid") is None
            and mo.group("escaped") is None
        ):
            raise ValueError(
                "Unrecognized named group in pattern", template.pattern
            )
    return ids


class DepsSourcesConfig:
    def __init__(self, file=Path.cwd() / DEFAULT_CONFIG_NAME):
        self.file = Path(file)
        self._config = None

    def validate_config(self, config):
        """Very basic validation of required fields"""
        if not isinstance(config, dict):
            raise DepsSourcesConfigError(
                f"Config should be dict, given: {config!r}"
            )

        if "sources" not in config:
            raise DepsSourcesConfigError("Missing 'sources' field in config")

        sources = config["sources"]
        if not isinstance(sources, dict):
            raise DepsSourcesConfigError(
                f"'sources' field should be dict, given: {sources!r}"
            )

        for src in sources.values():
            if not isinstance(src, dict):
                raise DepsSourcesConfigError(
                    f"Source definition should be dict, given: {src!r}"
                )

            if "srctype" not in src:
                raise DepsSourcesConfigError(
                    "Missing 'srctype' field in source definition"
                )
            self.validate_collector(src["srctype"], src.get("srcargs", ()))

            for req in src.get("deps", ()):
                try:
                    requirements.Requirement(req)
                except requirements.InvalidRequirement:
                    raise DepsSourcesConfigError(
                        f"Invalid stored PEP508 requirement: {req}"
                    ) from None

    @property
    def config(self):
        if self._config is None:
            with self.file.open(encoding="utf-8") as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError as e:
                    raise DepsSourcesConfigError(
                        f"Invalid config file: {self.file}"
                    ) from e
                self.validate_config(config)
                self._config = config
        return self._config

    @config.setter
    def config(self, value):
        self._config = deepcopy(value)
        self.save()

    def set_default(self):
        # default config
        self.config = {"sources": {}}

    def save(self):
        self.validate_config(self.config)
        # first parse the whole config
        json_config = self._to_json(self.config)
        self.file.write_text(json_config, encoding="utf-8")

    def show(self, srcnames=[]):
        show_conf = {"sources": {}}
        for srcname, source in self.iter_sources(srcnames):
            show_conf["sources"][srcname] = source
        self._show(show_conf)

    def _to_json(self, conf):
        return json.dumps(conf, indent=2, sort_keys=True) + "\n"

    def _show(self, conf):
        sys.stdout.write(self._to_json(conf))

    @property
    def sources(self):
        return self.config["sources"]

    def add(self, srcname, srctype, srcargs=[]):
        if not self.file.is_file():
            # allow new file
            self.set_default()
        srcargs = tuple(srcargs)
        self.validate_collector(srctype, srcargs)

        if srcname in self.sources:
            raise ValueError(f"Source {srcname} already exists")
        self.sources[srcname] = {"srctype": srctype}
        if srcargs:
            self.sources[srcname]["srcargs"] = srcargs
        self.save()

    def delete(self, srcname):
        if srcname not in self.sources:
            raise ValueError(f"Source {srcname} doesn't exist")
        del self.sources[srcname]
        self.save()

    def iter_sources(self, srcnames=[]):
        missing_srcnames = [x for x in srcnames if x not in self.sources]
        if missing_srcnames:
            raise ValueError(
                "Nonexistent sources: {}".format(", ".join(missing_srcnames))
            )

        for srcname in srcnames or self.sources:
            yield srcname, self.sources[srcname]

    def validate_collector(self, srctype, srcargs):
        collector_cls = get_collector(srctype)
        if collector_cls is None:
            raise DepsSourcesConfigError(
                f"Unsupported collector type: {srctype}"
            )
        try:
            return collector_cls(*srcargs)
        except TypeError as e:
            raise DepsSourcesConfigError(
                f"Unsupported arguments of collector {srctype}: {e!s}"
            ) from None

    def collect(self, srctype, srcargs):
        collector = self.validate_collector(srctype, srcargs)
        return collector.collect()

    def sync(self, srcnames=[], verify=False):
        """Sync sources

        verify: do sync of selected sources, but print the diff on
        stdout and raise DepsUnsyncedError if sources were unsynced before
        """
        diff = {}
        for srcname, source in self.iter_sources(srcnames):
            synced_deps = set(
                map(
                    requirements.Requirement,
                    self.collect(
                        source["srctype"],
                        srcargs=source.get("srcargs", ()),
                    ),
                )
            )

            stored_deps = set(
                map(requirements.Requirement, source.get("deps", ()))
            )

            if stored_deps == synced_deps:
                continue

            new_deps = synced_deps - stored_deps
            if new_deps:
                if srcname not in diff:
                    diff[srcname] = {}
                diff[srcname]["new_deps"] = sorted(map(str, new_deps))

            extra_deps = stored_deps - synced_deps
            if extra_deps:
                if srcname not in diff:
                    diff[srcname] = {}
                diff[srcname]["extra_deps"] = sorted(map(str, extra_deps))

            source["deps"] = sorted(map(str, synced_deps))

        self.save()

        if verify and diff:
            self._show(diff)
            raise DepsUnsyncedError

    def depformat(self, req, depformat, depformatextra):
        template = Template(depformat)
        identifiers = get_identifiers(template)

        depsubsts = {
            "name": req.name,
            "nname": pep503_normalized_name(req.name),
            "fextra": "",
        }

        if (
            depformatextra is not None
            and "fextra" in identifiers
            and req.extras
        ):
            extratemplate = Template(depformatextra)
            for extra in req.extras:
                yield template.safe_substitute(
                    depsubsts,
                    fextra=extratemplate.safe_substitute(extra=extra),
                )
        else:
            yield template.safe_substitute(depsubsts)

    def eval(
        self,
        srcnames=[],
        depformat=None,
        depformatextra=None,
        extra=None,
        excludes=[],
    ):
        if depformatextra is not None and depformat is None:
            raise ValueError("depformatextra must be used with depformat")
        deps = set()
        exclude_regexes = {re.compile(x) for x in excludes}

        for _, source in self.iter_sources(srcnames):
            for req in source.get("deps", ()):
                parsed_req = requirements.Requirement(req)

                # evaluating markers
                marker = parsed_req.marker
                if marker is not None:
                    env = None
                    if extra is not None:
                        env = {"extra": extra}
                    marker_res = marker.evaluate(env)
                    if not marker_res:
                        continue

                # filtering
                normalized_name = pep503_normalized_name(parsed_req.name)
                if any(reg.match(normalized_name) for reg in exclude_regexes):
                    continue

                # formatting
                if depformat is not None:
                    deps.update(
                        set(
                            self.depformat(
                                parsed_req, depformat, depformatextra
                            )
                        )
                    )
                else:
                    deps.add(str(parsed_req))

        for dep in sorted(deps):
            sys.stdout.write(dep + "\n")

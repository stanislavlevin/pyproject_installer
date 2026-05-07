import json
import re
import sys
from collections.abc import Iterator, Mapping
from copy import deepcopy
from pathlib import Path
from string import Template
from typing import Any, TypedDict

from ..errors import DepsSourcesConfigError, DepsUnsyncedError
from ..lib import is_pep508_requirement, requirements
from ..lib.normalization import pep503_normalized_name
from .collectors import get_collector
from .collectors.collector import Collector

DEFAULT_CONFIG_NAME = "pyproject_deps.json"


class DepsConfigSourceBaseType(TypedDict):
    srctype: str


class DepsConfigSourceOptType(TypedDict, total=False):
    deps: tuple[str, ...]
    srcargs: tuple[str, ...]


class DepsConfigSourceSpec(DepsConfigSourceBaseType, DepsConfigSourceOptType):
    pass


class DepsConfigType(TypedDict):
    sources: dict[str, DepsConfigSourceSpec]


def _get_identifiers_py310(template: Template) -> list[str]:  # pragma: no cover
    """Backport of CPython 3.11 Template.get_identifiers for Python 3.10."""
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
                "Unrecognized named group in pattern",
                template.pattern,
            )
    return ids


def get_identifiers(template: Template) -> list[str]:
    """Compat get_identifiers (added in Python 3.11)"""
    if hasattr(template, "get_identifiers"):  # pragma: no cover
        return template.get_identifiers()  # type: ignore[no-any-return]
    return _get_identifiers_py310(template)  # pragma: no cover


class DepsSourcesConfig:
    def __init__(self, file: str | Path | None = None) -> None:
        self.file = (
            Path.cwd() / DEFAULT_CONFIG_NAME if file is None else Path(file)
        )
        self._config: DepsConfigType | None = None

    def validate_config(self, config: DepsConfigType) -> None:
        """Very basic validation of required fields"""
        if not isinstance(config, dict):
            raise DepsSourcesConfigError(
                f"Config should be dict, given: {config!r}",
            )

        if "sources" not in config:
            raise DepsSourcesConfigError("Missing 'sources' field in config")

        sources = config["sources"]
        if not isinstance(sources, dict):
            raise DepsSourcesConfigError(
                f"'sources' field should be dict, given: {sources!r}",
            )

        for src in sources.values():
            if not isinstance(src, dict):
                raise DepsSourcesConfigError(
                    f"Source definition should be dict, given: {src!r}",
                )

            if "srctype" not in src:
                raise DepsSourcesConfigError(
                    "Missing 'srctype' field in source definition",
                )
            self.validate_collector(src["srctype"], src.get("srcargs", ()))

            for req in src.get("deps", ()):
                if not is_pep508_requirement(req):
                    raise DepsSourcesConfigError(
                        f"Invalid stored PEP508 requirement: {req}",
                    ) from None

    @property
    def config(self) -> DepsConfigType:
        if self._config is None:
            with self.file.open(encoding="utf-8") as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError as e:
                    raise DepsSourcesConfigError(
                        f"Invalid config file: {self.file}",
                    ) from e
                self.validate_config(config)
                self._config = config
        return self._config

    @config.setter
    def config(self, value: DepsConfigType) -> None:
        self._config = deepcopy(value)
        self.save()

    def set_default(self) -> None:
        # default config
        self.config = {"sources": {}}

    def save(self) -> None:
        self.validate_config(self.config)
        # first parse the whole config
        json_config = self._to_json(self.config)
        self.file.write_text(json_config, encoding="utf-8")

    def show(self, srcnames: tuple[str, ...] = ()) -> None:
        show_conf: DepsConfigType = {"sources": {}}
        for srcname, source in self.iter_sources(srcnames):
            show_conf["sources"][srcname] = source
        self._show(show_conf)

    def _to_json(self, conf: Mapping[str, Any]) -> str:
        return json.dumps(conf, indent=2, sort_keys=True) + "\n"

    def _show(self, conf: Mapping[str, Any]) -> None:
        sys.stdout.write(self._to_json(conf))

    @property
    def sources(self) -> dict[str, DepsConfigSourceSpec]:
        return self.config["sources"]

    def add(
        self,
        srcname: str,
        srctype: str,
        srcargs: tuple[str, ...] = (),
    ) -> None:
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

    def delete(self, srcname: str) -> None:
        if srcname not in self.sources:
            raise ValueError(f"Source {srcname} doesn't exist")
        del self.sources[srcname]
        self.save()

    def iter_sources(
        self,
        srcnames: tuple[str, ...] = (),
    ) -> Iterator[tuple[str, DepsConfigSourceSpec]]:
        if missing_srcnames := [x for x in srcnames if x not in self.sources]:
            raise ValueError(
                f"Nonexistent sources: {', '.join(missing_srcnames)}",
            )

        for srcname in srcnames or self.sources:
            yield srcname, self.sources[srcname]

    def validate_collector(
        self,
        srctype: str,
        srcargs: tuple[str, ...],
    ) -> Collector:
        collector_cls = get_collector(srctype)
        if collector_cls is None:
            raise DepsSourcesConfigError(
                f"Unsupported collector type: {srctype}",
            )
        try:
            return collector_cls(*srcargs)
        except TypeError as e:
            raise DepsSourcesConfigError(
                f"Unsupported arguments of collector {srctype}: {e!s}",
            ) from None

    def collect(self, srctype: str, srcargs: tuple[str, ...]) -> Iterator[str]:
        collector = self.validate_collector(srctype, srcargs)
        return collector.collect()

    def sync(
        self,
        *,
        srcnames: tuple[str, ...] = (),
        verify: bool = False,
        verify_excludes: tuple[str, ...] = (),
    ) -> None:
        """Sync sources

        verify: do sync of selected sources, but print the diff on
        stdout and raise DepsUnsyncedError if sources were unsynced before

        verify_excludes: filter out dependencies from diff output
        normalized names of those match given regexes (requires verify=True).
        """
        if verify_excludes and not verify:
            raise ValueError("verify_excludes must be used with verify")

        diff: dict[str, dict[str, list[str]]] = {}
        verify_excludes_regs = {re.compile(x) for x in verify_excludes}

        def filter_verify_excludes(req: requirements.Requirement) -> bool:
            """filter diff output"""
            req_name = pep503_normalized_name(req.name)
            return not any(reg.match(req_name) for reg in verify_excludes_regs)

        for srcname, source in self.iter_sources(srcnames):
            synced_deps = set(
                map(
                    requirements.Requirement,
                    self.collect(
                        source["srctype"],
                        srcargs=source.get("srcargs", ()),
                    ),
                ),
            )

            stored_deps = set(
                map(requirements.Requirement, source.get("deps", ())),
            )

            if stored_deps == synced_deps:
                continue

            source["deps"] = tuple(sorted(map(str, synced_deps)))

            if not verify:
                continue

            for field_name, diff_deps in (
                ("new_deps", synced_deps - stored_deps),
                ("extra_deps", stored_deps - synced_deps),
            ):
                filtered_diff_deps = set(
                    filter(filter_verify_excludes, diff_deps),
                )

                if not filtered_diff_deps:
                    continue

                if srcname not in diff:
                    diff[srcname] = {}
                diff[srcname][field_name] = sorted(map(str, filtered_diff_deps))

        self.save()

        if verify and diff:
            self._show(diff)
            raise DepsUnsyncedError

    def depformat(
        self,
        req: requirements.Requirement,
        depformat: str,
        depformatextra: str | None,
    ) -> Iterator[str]:
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
        *,
        srcnames: tuple[str, ...] = (),
        depformat: str | None = None,
        depformatextra: str | None = None,
        extra: str | None = None,
        excludes: tuple[str, ...] = (),
    ) -> None:
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
                                parsed_req,
                                depformat,
                                depformatextra,
                            ),
                        ),
                    )
                else:
                    deps.add(str(parsed_req))

        for dep in sorted(deps):
            sys.stdout.write(dep + "\n")

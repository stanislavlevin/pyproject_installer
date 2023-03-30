from copy import deepcopy
from pathlib import Path
import json
import sys

from packaging.requirements import Requirement

from ..lib.normalization import pep503_normalized_name
from .collectors import get_collector


class DepsSourcesConfig:
    def __init__(self, file, create=False):
        self.file = Path(file)
        self.read(create=create)

    def set_default(self):
        # default config
        self.config = {}
        self.sources = {}

    def read(self, create):
        if not self.file.is_file():
            if create:
                # new file
                self.set_default()
                return
            raise FileNotFoundError(f"Missing deps config file: {self.file}")

        with self.file.open(encoding="utf-8") as f:
            try:
                self.config = json.load(f)
            except json.JSONDecodeError:
                raise ValueError(
                    f"Invalid dependencies file: {f}"
                ) from None

    def save(self):
        # first parse the whole config
        json_config = json.dumps(self.config, indent=2) + "\n"
        self.file.write_text(json_config, encoding="utf-8")

    def show(self, srcnames=()):
        show_conf = {"sources": {}}
        for source_name in self.find_sources(srcnames):
            source = self.get_source(source_name)
            show_conf["sources"][source_name] = source
        self._show(show_conf)

    def _show(self, conf):
        out = json.dumps(conf, indent=2) + "\n"
        sys.stdout.write(out)

    @property
    def sources(self):
        return self.config["sources"]

    @sources.setter
    def sources(self, value):
        self.config["sources"] = deepcopy(value)

    def get_source(self, srcname):
        if srcname not in self.sources:
            raise ValueError(f"Source '{srcname}' doesn't exist")
        return self.sources[srcname]

    def add(self, srcname, srctype, srcargs):
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

    def find_sources(self, srcnames=()):
        missing_sources = set(srcnames) - set(self.sources)
        if missing_sources:
            raise ValueError(
                "Non existent sources: {}".format(', '.join(missing_sources))
            )

        if srcnames:
            yield from srcnames
        else:
            yield from self.sources

    def validate_collector(self, srctype, srcargs):
        collector_cls = get_collector(srctype)
        if collector_cls is None:
            raise ValueError(f"Unsupported collector type: {srctype}")
        try:
            return collector_cls(*srcargs)
        except TypeError as e:
            raise ValueError(
                f"Unsupported arguments of collector {srctype}: {e!s}"
            ) from None

    def collect(self, srctype, srcargs):
        collector = self.validate_collector(srctype, srcargs)
        return collector.collect()

    def sync(self, srcnames=(), verify=False):
        """Sync sources

        With enabled `verify` DepsUnsyncedError is raised if sources are not
        synced and the diff is printed.
        """
        for srcname in self.find_sources(srcnames):
            source = self.get_source(srcname)
            diff = {srcname: {}}

            synced_deps = set(
                self.collect(
                    source["srctype"],
                    srcargs=source.get("srcargs", ()),
                )
            )

            stored_deps = set(source.get("deps", ()))

            if stored_deps == synced_deps:
                continue

            new_deps = synced_deps - stored_deps
            if new_deps:
                diff[srcname]["new_deps"] = tuple(new_deps)

            extra_deps = stored_deps - synced_deps
            if extra_deps:
                diff[srcname]["extra_deps"] = tuple(extra_deps)

            source["deps"] = sorted(synced_deps)
            self.save()

            if verify and diff[srcname]:
                out = json.dumps(diff, indent=2) + "\n"
                sys.stdout.write(out)
                raise DepsUnsyncedError

    def eval(self, srcnames=(), namesonly=True, extra=None, excludes=[]):
        deps = set()
        exclude_regexes = {re.compile(x) for x in excludes}

        for srcname in self.find_sources(srcnames):
            source = self.get_source(srcname)
            for req in source.get("deps", ()):
                parsed_req = Requirement(req)
                marker = parsed_req.marker
                if marker is not None:
                    env = None
                    if extra is not None:
                        env = {"extra": extra}
                    marker_res = marker.evaluate(env)
                    if not marker_res:
                        continue
                normalized_name = pep503_normalized_name(parsed_req.name)
                if any(reg.match(normalized_name) for reg in exclude_regexes):
                    continue
                if namesonly:
                    deps.add(normalized_name)
                else:
                    deps.add(req)

        for dep in deps:
            sys.stdout.write(dep + "\n")

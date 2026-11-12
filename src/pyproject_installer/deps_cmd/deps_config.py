"""Manage dependency sources stored in the shared configuration."""

import logging
import re
import sys
from collections import deque
from collections.abc import Collection, Iterator
from string import Template

from ..errors import (
    DepsNoCandidateError,
    DepsSourcesConfigError,
    DepsUnsyncedError,
)
from ..lib import (
    is_pep508_requirement,
    requirements,
    specifiers,
    utils,
    version,
)
from ..lib.normalization import pep503_normalized_name
from .collectors import get_collector
from .collectors.collector import Collector
from .deps_config_base import DepsConfig, DepsConfigSourceSpec, DepsConfigType

logger = logging.getLogger(__name__)


def rpm_lower_limit(version_specs: specifiers.SpecifierSet) -> str:
    """
    Fold the lower limits of PEP 440 specifiers into the strictest one and
    convert it for RPM, e.g. '>= 1.3'; '' if there is no lower limit.

    RPM compares versions differently from PEP 440 (it treats 1.0rc1 and
    1.0.0 as newer than 1.0), so only the release numbers without trailing
    zeros are kept and the printed limit never rejects a version PEP 440
    accepts.
    """
    picked: specifiers.Specifier | None = None
    for spec in version_specs:
        if spec.operator in (">=", ">"):
            limit = spec
        elif spec.operator == "~=":
            limit = specifiers.Specifier(f">={spec.version}")
        elif spec.operator == "==" and spec.version.endswith(".*"):
            limit = specifiers.Specifier(f">={spec.version[:-2]}")
        else:
            continue

        # keep the strictest limit: the one whose allowed versions are
        # inside the allowed versions of the other (>=1.5 for >=1.2,>=1.5)
        if picked is None or specifiers.SpecifierSet([limit]).is_subset(
            specifiers.SpecifierSet([picked]),
        ):
            picked = limit

    if picked is None:
        return ""

    picked_version = version.Version(picked.version)
    if (operator := picked.operator) == ">" and (
        picked_version.is_prerelease or picked_version.is_postrelease
    ):
        # > 1.3 would reject 1.3, which >1.3a1 accepts
        operator = ">="

    release = ".".join(str(x) for x in picked_version.release)
    # PEP 440 treats 2.0 and 2.0.0 as equal, RPM treats 2.0 as older;
    # >= 2 accepts both
    release = utils.canonicalize_version(release, strip_trailing_zero=True)
    return f"{operator} {release}"


class DepsSourcesConfig(DepsConfig):
    """Manage dependency sources using shared config storage and validation."""

    def validate_config(self, config: DepsConfigType) -> None:
        """Validate dependency sources and their stored requirements."""
        super().validate_config(config)
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

    def validate_collector(
        self,
        srctype: str,
        srcargs: tuple[str, ...],
    ) -> Collector:
        """Validate a source type and its arguments and create its collector."""
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

    def show(self, srcnames: tuple[str, ...] = ()) -> None:
        """Show configuration and stored dependencies for selected sources."""
        show_conf: DepsConfigType = {"sources": {}}
        for srcname, source in self.iter_sources(srcnames):
            show_conf["sources"][srcname] = source
        self._show(show_conf)

    @property
    def sources(self) -> dict[str, DepsConfigSourceSpec]:
        """Return the configured dependency sources."""
        return self.config["sources"]

    def _resolve_candidate(
        self,
        candidates: tuple[tuple[str, ...], ...],
    ) -> tuple[str, tuple[str, ...]] | None:
        """First candidate that collects successfully, as (srctype, srcargs)

        The candidate list is validated up front: an unknown type or the
        wrong number of arguments means the candidate list itself is
        malformed and raises DepsSourcesConfigError -- it is not a silently
        skipped entry. The validated entries are then walked left to right
        and the first that collects successfully wins -- its source is
        present and collectable -- even if it yields zero dependencies. A
        candidate is skipped when its collect fails for any reason (a
        missing file or group, or data that cannot be parsed): a source that
        cannot be collected is not a usable source. Returns None when no
        candidate collects.
        """
        logger.info("Resolving source candidates")
        validated: list[tuple[str, tuple[str, ...], Collector]] = []
        for candidate in candidates:
            srctype, srcargs = candidate[0], candidate[1:]
            # Raises DepsSourcesConfigError on an unknown type or the wrong
            # number of arguments: a malformed list is an error, not a skip.
            collector = self.validate_collector(srctype, srcargs)
            validated.append((srctype, srcargs, collector))

        for srctype, srcargs, collector in validated:
            try:
                # collectors collect lazily
                deque(collector.collect(), maxlen=0)
            except Exception as e:  # noqa: BLE001 - uncollectable: try next
                logger.debug(
                    "Skipped candidate source: %s (%s)",
                    " ".join((srctype, *srcargs)),
                    e,
                )
                continue
            logger.info(
                "Picked candidate source: %s",
                " ".join((srctype, *srcargs)),
            )
            return srctype, srcargs
        return None

    def add(
        self,
        srcname: str | None = None,
        srctype: str | None = None,
        srcargs: tuple[str, ...] = (),
        *,
        candidates: tuple[tuple[str, ...], ...] | None = None,
        sources: tuple[tuple[str, ...], ...] | None = None,
        reconfigure: bool = False,
        sync: bool = False,
        verify: bool = False,
        verify_excludes: tuple[str, ...] = (),
        verify_ignore_version: bool = False,
    ) -> None:
        """Configure a source of dependencies, optionally syncing it

        candidates: an ordered list of (srctype, *srcargs) candidates,
        mutually exclusive with srctype/srcargs -- exactly one of srctype
        or candidates is required; the source is taken from the first
        candidate that collects successfully (its source is present and
        collectable). When no candidate is picked, DepsNoCandidateError
        is raised in every case and any existing srcname is left untouched.

        reconfigure: if the source already exists, keep it when its type
        and args are unchanged, or replace it (dropping its stored deps)
        when they differ, instead of raising. Without it an existing
        source raises ValueError.

        sync: after configuring the source (newly added, kept or
        replaced), sync it in the same process. The verify options
        (verify, verify_excludes, verify_ignore_version) are forwarded to
        sync() and only apply when sync=True.

        sources: an ordered tuple of (srcname, srctype, *srcargs) tuples for
        adding a batch in one call. It cannot be combined with single source
        configuration or candidates. Each entry is configured -- and, when
        sync=True, synced and optionally verified -- in turn via this same
        single-source path, so the first DepsUnsyncedError stops the rest (later
        entries are left unconfigured).
        """
        if sources is not None:
            if any((srcname, srctype, srcargs, candidates)):
                raise ValueError(
                    "'sources' is mutually exclusive with "
                    "single source configuration or 'candidates'",
                )
            for src_name, src_type, *src_args in sources:
                self.add(
                    src_name,
                    src_type,
                    tuple(src_args),
                    reconfigure=reconfigure,
                    sync=sync,
                    verify=verify,
                    verify_excludes=verify_excludes,
                    verify_ignore_version=verify_ignore_version,
                )
            return

        if srcname is None:
            raise ValueError(
                "'srcname' is required with 'candidates' or single source "
                "configuration",
            )

        logger.info("Configuring source %s", srcname)

        if all((candidates, srctype)):
            raise ValueError(
                "'srctype' is mutually exclusive with 'candidates'",
            )

        if candidates is not None:
            if (picked := self._resolve_candidate(candidates)) is None:
                logger.error(
                    "Autodiscovery failed for source %s: no candidate "
                    "source could be collected (tried: %s)",
                    srcname,
                    ", ".join(" ".join(c) for c in candidates),
                )
                raise DepsNoCandidateError(
                    f"No candidate source matched for {srcname}",
                )

            srctype, srcargs = picked
        elif srctype is None:
            raise ValueError(
                "Either 'srctype' or 'candidates' is required for add",
            )

        if not self.file.is_file():
            # allow new file
            self.set_default()
        srcargs = tuple(srcargs)
        self.validate_collector(srctype, srcargs)

        keep_existing = False
        if srcname in self.sources:
            if not reconfigure:
                raise ValueError(f"Source {srcname} already exists")
            if (
                self.sources[srcname]["srctype"] == srctype
                and tuple(self.sources[srcname].get("srcargs", ())) == srcargs
            ):
                logger.info(
                    "Source %s already configured, keeping unchanged",
                    srcname,
                )
                keep_existing = True
            else:
                logger.info(
                    "Source %s differs, reconfiguring (stored deps dropped)",
                    srcname,
                )
                del self.sources[srcname]

        if not keep_existing:
            self.sources[srcname] = {"srctype": srctype}
            if srcargs:
                self.sources[srcname]["srcargs"] = srcargs
            self.save()
            logger.info(
                "Configured source %s: %s",
                srcname,
                " ".join((srctype, *srcargs)),
            )

        if sync:
            self.sync(
                srcnames=(srcname,),
                verify=verify,
                verify_excludes=verify_excludes,
                verify_ignore_version=verify_ignore_version,
            )

    def delete(self, srcname: str) -> None:
        if srcname not in self.sources:
            raise ValueError(f"Source {srcname} doesn't exist")
        logger.info("Deleting source %s", srcname)
        del self.sources[srcname]
        self.save()
        logger.info("Deleted source %s", srcname)

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

    def collect(self, srctype: str, srcargs: tuple[str, ...]) -> Iterator[str]:
        collector = self.validate_collector(srctype, srcargs)
        return collector.collect()

    def sync(
        self,
        *,
        srcnames: tuple[str, ...] = (),
        verify: bool = False,
        verify_excludes: tuple[str, ...] = (),
        verify_ignore_version: bool = False,
    ) -> None:
        """Sync sources

        verify: do sync of selected sources, but print the diff on
        stdout and raise DepsUnsyncedError if sources were unsynced before

        verify_excludes: filter out from diff output dependencies whose
        normalized names match given regexes (requires verify=True).

        verify_ignore_version: filter out from diff output dependencies that
        differ only in their version specifier, i.e. a dependency with the same
        normalized name, extras, marker and url is present on both sides of the
        diff (requires verify=True).
        """
        if verify_excludes and not verify:
            raise ValueError(
                "'verify_excludes' must be used with 'verify'",
            )

        if verify_ignore_version and not verify:
            raise ValueError(
                "'verify_ignore_version' must be used with 'verify'",
            )

        logger.info("Syncing sources")

        diff: dict[str, dict[str, list[str]]] = {}
        verify_excludes_regs = {re.compile(x) for x in verify_excludes}

        def matching_verify_exclude(
            req: requirements.Requirement,
        ) -> re.Pattern[str] | None:
            """The first verify-exclude regex matching req's name, if any."""
            req_name = pep503_normalized_name(req.name)
            return next(
                (reg for reg in verify_excludes_regs if reg.match(req_name)),
                None,
            )

        def version_less_req(
            req: requirements.Requirement,
        ) -> requirements.Requirement:
            """New requirement equal to req but without its version specifier

            Lets two requirements that differ only in their specifier compare
            and hash equal through Requirement's own __eq__/__hash__, instead of
            rebuilding their identity from hand-picked fields.
            """
            versionless = requirements.Requirement(str(req))
            versionless.specifier = specifiers.SpecifierSet()
            return versionless

        total = 0
        updated = 0
        for srcname, source in self.iter_sources(srcnames):
            total += 1
            srctype = source["srctype"]
            srcargs = source.get("srcargs", ())
            logger.info("Syncing source %s", srcname)
            synced_deps = set(
                map(
                    requirements.Requirement,
                    self.collect(srctype, srcargs=srcargs),
                ),
            )

            stored_deps = set(
                map(requirements.Requirement, source.get("deps", ())),
            )

            if stored_deps == synced_deps:
                logger.info("Source %s is in sync", srcname)
                continue

            updated += 1
            logger.info("Updated source %s", srcname)
            source["deps"] = tuple(sorted(map(str, synced_deps)))

            if not verify:
                continue

            new_deps = synced_deps - stored_deps
            extra_deps = stored_deps - synced_deps

            if verify_ignore_version:
                # Reuse one version-less form per requirement instead of
                # reparsing it for every membership test below.
                versionless = {
                    req: version_less_req(req) for req in new_deps | extra_deps
                }
                # A version-less form on both sides of the diff means the dep
                # was both added and removed, so only its version changed; the
                # originals with such a form are dropped. A form on one side is
                # a genuine add or removal and is kept.
                both_sides = {versionless[req] for req in new_deps} & {
                    versionless[req] for req in extra_deps
                }
                version_changed_deps = {
                    req for req, vl in versionless.items() if vl in both_sides
                }
            else:
                version_changed_deps = set()

            for field_name, diff_deps in (
                ("new_deps", new_deps),
                ("extra_deps", extra_deps),
            ):
                filtered_diff_deps: set[requirements.Requirement] = set()
                for req in diff_deps:
                    exclude_match = matching_verify_exclude(req)
                    if exclude_match is not None:
                        logger.debug(
                            "Excluded %s from %s diff: "
                            "matches 'verify_excludes' pattern '%s'",
                            req,
                            srcname,
                            exclude_match.pattern,
                        )
                        continue
                    if req in version_changed_deps:
                        logger.debug(
                            "Excluded %s from %s diff: version-only change",
                            req,
                            srcname,
                        )
                        continue
                    filtered_diff_deps.add(req)

                if not filtered_diff_deps:
                    continue

                if srcname not in diff:
                    diff[srcname] = {}
                diff[srcname][field_name] = sorted(map(str, filtered_diff_deps))

        self.save()

        if verify and diff:
            logger.info("%d sources unsynced", len(diff))
            self._show(diff)
            logger.error(
                "Dependencies of %d source(s) changed since last check: %s.\n"
                'The configuration was synced and saved into "%s"',
                len(diff),
                ", ".join(sorted(diff)),
                self.file,
            )
            raise DepsUnsyncedError

        logger.info(
            "Synced %d sources (%d updated, %d in sync)",
            total,
            updated,
            total - updated,
        )

    def depsformat(
        self,
        kept_reqs: Collection[tuple[str, requirements.Requirement]],
        *,
        depformat: str,
        depformatextra: str | None,
        ignore_rpmlowvers: Collection[str] = (),
    ) -> Iterator[str]:
        """
        Format requirements.

        'kept_reqs' are the requirements of all evaluated sources, as
        (normalized name, requirement) pairs; $rpmlowver folds the lower
        limits of all requirements with the same name into one.
        'ignore_rpmlowvers' are PEP503-normalized names whose $rpmlowver
        substitution is empty.
        """
        template = Template(depformat)
        identifiers = template.get_identifiers()

        rpmlowvers = {}
        if "rpmlowver" in identifiers:
            rpmlowvers = {
                name: rpm_lower_limit(
                    specifiers.SpecifierSet(
                        spec
                        for other_name, req in kept_reqs
                        if other_name == name
                        for spec in req.specifier
                    ),
                )
                for name in {name for name, _ in kept_reqs}
                if name not in ignore_rpmlowvers
            }

        for normalized_name, req in kept_reqs:
            rpmlowver = rpmlowvers.get(normalized_name, "")
            depsubsts = {
                "name": req.name,
                "nname": normalized_name,
                "fextra": "",
                "rpmlowver": f" {rpmlowver}" if rpmlowver else "",
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
                        fextra=extratemplate.safe_substitute(
                            extra=extra,
                            # PEP685 normalizes an extra with the PEP503 rules
                            nextra=pep503_normalized_name(extra),
                        ),
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
        ignore_rpmlowvers: tuple[str, ...] = (),
    ) -> None:
        if depformatextra is not None and depformat is None:
            raise ValueError(
                "'depformatextra' must be used with 'depformat'",
            )
        if ignore_rpmlowvers and depformat is None:
            raise ValueError(
                "'ignore_rpmlowvers' must be used with 'depformat'",
            )
        logger.info("Evaluating dependencies")
        nsources = 0
        exclude_regexes = {re.compile(x) for x in excludes}
        kept_reqs: set[tuple[str, requirements.Requirement]] = set()

        for srcname, source in self.iter_sources(srcnames):
            nsources += 1
            # instantiate the collector for its eval_env() marker contribution;
            # the type and args were already validated at config load
            collector = self.validate_collector(
                source["srctype"],
                tuple(source.get("srcargs", ())),
            )
            source_env = collector.eval_env()
            for req in source.get("deps", ()):
                parsed_req = requirements.Requirement(req)

                # evaluating markers
                marker = parsed_req.marker
                if marker is not None:
                    # build an override mapping only when there is something
                    # to override; pass None otherwise so the marker is
                    # evaluated against packaging's default environment (its
                    # documented contract for None). A source's recorded extra
                    # (via eval_env) takes precedence over a command-line
                    # --extra.
                    env = None
                    if extra is not None:
                        env = {"extra": extra}

                    if source_env:
                        env = (env or {}) | source_env
                    marker_res = marker.evaluate(env)
                    if not marker_res:
                        logger.debug(
                            "Filtered out %s from %s: marker '%s' is false",
                            parsed_req,
                            srcname,
                            marker,
                        )
                        continue

                # filtering
                normalized_name = pep503_normalized_name(parsed_req.name)
                exclude_match = next(
                    (
                        reg
                        for reg in exclude_regexes
                        if reg.match(normalized_name)
                    ),
                    None,
                )
                if exclude_match is not None:
                    logger.debug(
                        "Filtered out %s from %s: "
                        "matches 'excludes' pattern '%s'",
                        parsed_req,
                        srcname,
                        exclude_match.pattern,
                    )
                    continue

                kept_reqs.add((normalized_name, parsed_req))

        # formatting
        if depformat is None:
            deps = {str(parsed_req) for _, parsed_req in kept_reqs}
        else:
            deps = set(
                self.depsformat(
                    kept_reqs,
                    depformat=depformat,
                    depformatextra=depformatextra,
                    ignore_rpmlowvers={
                        pep503_normalized_name(x) for x in ignore_rpmlowvers
                    },
                ),
            )

        for dep in sorted(deps):
            sys.stdout.write(dep + "\n")
        # flush data (stdout) so it precedes the diagnostic below (stderr) in a
        # merged stream, regardless of stdout block-buffering when piped
        sys.stdout.flush()

        logger.info(
            "Evaluated %d dependencies from %d sources",
            len(deps),
            nsources,
        )

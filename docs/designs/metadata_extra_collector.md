## Abstract
This RFE proposes a new `metadata_extra` collector type that takes
an extra name, validates it against the project's `Provides-Extra`,
and stores the project's full `Requires-Dist` list independently of
the base `metadata` source. `eval` recognizes this source type and
evaluates its stored deps with the source's own recorded extra,
ignoring any `--extra` given on the command line. This lets an
optional-dependency group (for example a `tests` extra) be
configured through `deps add --candidates`, synced, and evaluated
uniformly, without the caller needing to know which candidate won.

## Motivation
A project's test (or other optional) dependencies often live in an
extra. Today a consumer can only select an extra at `eval` time via
`--extra`, so "the deps of the `tests` extra" cannot be a configured
source and cannot take part in `deps add --candidates` discovery. A
candidates list like

```
'pep735 tests;metadata_extra tests;metadata_extra dev'
```

should pick the first that exists and record it, so the downstream
`eval` is the same command regardless of which candidate matched.
The caller cannot know the winner — only the config does — so the
selected extra must be carried in the config and applied by `eval`
itself.

Why a full list instead of just the extra's delta: isolating "only
the deps that apply under extra E, with the `extra == E` marker
stripped" requires inspecting and rewriting markers, which the
public `packaging` API does not offer. Storing the full
`Requires-Dist` and evaluating with the extra set avoids changing
markers at all, using only public API.

## Specification

### Collector
New type `metadata_extra`, `name = "metadata_extra"`, registered in
`SUPPORTED_COLLECTORS`, implemented as a subclass of
`MetadataCollector` — it reuses the base's build-and-parse logic
instead of reimplementing it.

Building METADATA is the expensive step (it may build a wheel), and
the subclass needs two things out of it: the `Provides-Extra`
headers to validate the extra, and the `Requires-Dist` list to
yield. To build and parse the metadata only once per `collect()`,
split the base's current `collect()` into reusable methods on
`MetadataCollector`:

- `parsed_metadata() -> email.message.Message` — the expensive part:
  build METADATA into a temp dir, read its text, and parse it once
  with stdlib `email`, returning the parsed message.
- `iter_requires(metadata) -> Iterator[str]` — the cheap part: take
  the parsed message, read its `Requires-Dist`, run the base's
  `is_pep508_requirement` validation, and yield the same requirement
  strings (and the same error) as today.

The base `collect()` becomes `iter_requires(parsed_metadata())` —
behavior and error message unchanged. The subclass calls
`parsed_metadata()` once, reads `Provides-Extra` from that same
message to validate the extra, then reuses `iter_requires()` on it —
so the metadata text is parsed only once.

Requirement parsing deliberately stays on the base's stdlib `email`
path rather than `packaging.metadata.Metadata`: `Metadata`'s
`requires_dist` raises `InvalidMetadata` on a bad dependency, which
would replace the base collector's established `"<name>: invalid
PEP508 Dependency Specifier: ..."` error. `Provides-Extra` is parsed
the same way (`email` + `utils.canonicalize_name` for PEP 503/685
normalization), so no new `_vendor` re-export is needed.

`MetadataExtraCollector(extra: str)` — `srcargs = (extra,)`,
required (exactly one argument; zero or more than one is a config
error, caught by the existing `validate_collector`).

`collect()`:
1. Call `parsed_metadata()` once (one build, one parse).
2. Raise `ValueError` if the normalized extra is not among the
   normalized `Provides-Extra` headers. This makes a typo loud, and
   during `--candidates` discovery it lets a project that does not
   declare the extra be skipped so the next candidate is tried.
3. `yield from iter_requires(metadata)` — the full `Requires-Dist`
   list unchanged (markers intact), reusing the base's logic rather
   than duplicating it.

### eval
`eval` must apply the source's recorded extra to that source's
stored deps. So `eval` does not need to know about specific
collector types, it asks each collector for its marker-environment
contribution instead of checking the source type name:

- New instance method on the `Collector` base:
  `eval_env(self) -> dict[str, str]`, default `{}`.
- `MetadataExtraCollector.eval_env` returns `{"extra": self.extra}`,
  reusing the extra already parsed from `srcargs` in `__init__` — so
  the meaning of `srcargs` lives only in the constructor, not
  re-derived here.
- In `eval`, for each source, instantiate the collector via the
  existing `validate_collector(srctype, srcargs)` (same call used by
  `collect`/`sync`; no build), call `eval_env()`, and merge the
  result into the marker environment used to evaluate that source's
  deps.

For a `metadata_extra` source the recorded extra **takes
precedence**: a CLI `--extra` is ignored for that source's deps (it
still applies to other sources as today).

Why ignore a given `--extra`: the source stores the *full*
`Requires-Dist`, so its extra-gated deps only surface when evaluated
with that one recorded extra. A different `--extra` (or none) would
silently emit the wrong subset — a different extra's deps, or none
of them. And the whole point of recording the extra in config is
that the caller does not know which candidate won (`metadata_extra
tests` vs `dev` vs a `pep735` group), so it cannot supply the right
`--extra` anyway. The stored extra is therefore the only correct one
for that source, and honoring an external override could only break
it.

### Config validation
A `metadata_extra` source takes exactly one `srcargs` entry (the
extra name). No reference to other sources is stored; the source is
self-contained.

## Accepted trade-offs
- The stored deps duplicate the base `metadata` source's deps. The
  config is machine-generated, so this is cosmetic.
- `sync --verify` on a `metadata_extra` source reports drift when
  *any* extra's deps change, not only the recorded one, since the
  full list is stored.
- No caching of METADATA builds: each `metadata_extra` probe/sync
  triggers its own build. List cheaper source types first in
  candidate lists, so `metadata_extra` is reached only when needed.

## Rejected ideas

### Reuse an existing `metadata` source instead of storing deps independently
Rather than building and storing its own full `Requires-Dist`,
`metadata_extra` could point at a configured `metadata` source and
reuse its stored deps (storing only a reference and the extra,
`metadata_extra <metadata_src> <extra>`). This removes the
duplication and the second METADATA build, but was rejected because:

- **Coupling.** `srcargs` must carry the target source name, and
  config validation must check the target exists and is a `metadata`
  source — the source is no longer self-contained.
- **Coherence.** `eval` would read the target's stored deps, so the
  target must be fresh; an unsynced or absent target yields stale or
  missing deps. This forces a "sync pulls the target in" rule that
  complicates `sync`.
- **Validation gap.** The extra-existence check needs
  `Provides-Extra`, which a `metadata` source's *stored deps* do not
  carry. So `--candidates` discovery would either lose its cheap
  "does this extra exist?" check or have to build METADATA anyway —
  removing the main saving.

In summary, it trades duplication for cross-source coupling plus a
gap in discovery validation. Independent storage keeps
`metadata_extra` a normal, self-contained source that works in
`--candidates` without referencing anything.

## Example

```
# discover the tests extra; the first candidate that exists wins
python -m pyproject_installer deps add check \
    --candidates 'pep735 tests;metadata_extra tests' \
    --sync

# same command regardless of which candidate won:
python -m pyproject_installer deps eval check
```

With no `tests` dependency group, `pep735 tests` is skipped and
`metadata_extra tests` wins. Given `Provides-Extra: tests` and
`Requires-Dist: pytest; extra == "tests"`, the `check` source
stores the full `Requires-Dist` and records extra `tests`; `eval`
evaluates each marker with `extra == "tests"` set, so the
`pytest` requirement is included and printed as
`pytest; extra == "tests"`. If a `pep735` `tests` group existed
instead, it would have won and `eval_env` would contribute nothing —
the same `eval check` works.

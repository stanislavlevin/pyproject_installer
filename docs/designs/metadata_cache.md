## Abstract
This RFE proposes caching the project's built core metadata to a
single file, `dist/metadata_cache`, so that repeated metadata builds
for the same source tree happen once instead of once per `deps`
command. The metadata still gets built the same way it does today
(including the full-wheel fallback for backends without
`prepare_metadata_for_build_wheel`); the cache only removes the
repeated rebuilds.

## Motivation
The `metadata` and `metadata_extra` sources collect a project's
dependencies from its built core metadata. Building that metadata
runs the PEP 517 `prepare_metadata_for_build_wheel` hook, and when
the backend does not implement it, falls back to a full
`build_wheel` -- which for a binary package compiles the project.
That build is the single most expensive thing the `deps` command
does.

Today each `collect()` rebuilds the metadata from scratch and shares
nothing, so the build is repeated whenever more than one metadata
build would otherwise happen for the same tree:

- Within one `deps add --candidates '...' --sync`, candidate
  resolution collects each candidate it tries (every `metadata_extra`
  candidate builds the metadata to check `Provides-Extra`), then
  `--sync` collects again -- two or three builds for one command.
- Across several `deps` commands run in sequence against the same tree
  (one per source), every metadata-derived source builds the metadata
  independently.

The metadata is mandatory -- there is no way to record
metadata-derived dependencies without it -- so the goal is not to
avoid the build but to do it exactly once per tree.

## Specification

### Cache file
A single file, `dist/metadata_cache`, holding the project's core
metadata text (the `METADATA` content). It lives under the working
directory the metadata is built from (`cwd`), so it is bound to that
tree by location:

- it sits inside the build tree and is removed when the tree (or
  `dist/`) is cleaned;
- a different tree is a different `cwd/dist/metadata_cache`, so two
  trees never share a cache.

It is a build artifact and is not committed (it belongs with the
other `dist/` output).

### Cache lookup in `parsed_metadata()`
`MetadataCollector.parsed_metadata()` is the single place every
metadata build goes through: both the `metadata` and `metadata_extra`
collectors reach the build through it, and so does `--candidates`
probing (which collects each candidate).
It reads the cache file when it exists and builds only when it is
missing:

- if `dist/metadata_cache` exists -> read it, no build;
- otherwise build the metadata the existing way (the
  `prepare_metadata_for_build_wheel` hook into a temporary directory,
  falling back to `build_wheel`).

In both cases the metadata text is then validated into a
`packaging.metadata.Metadata` (a single parse, which `parsed_metadata()`
returns), and a freshly built one is written to `dist/metadata_cache`
(creating `dist/` if needed) only after it validates. The collectors
read that object's typed fields directly -- `requires_dist` for both,
and `provides_extra` (already PEP 503/685-normalized) for
`metadata_extra` -- instead of re-parsing the text.

The cache stores only the metadata text regardless of how it was
obtained; on the fallback path the wheel itself is still left in its
own temporary directory and discarded, exactly as today.

Validation is full, via `packaging.metadata`
(`Metadata.from_email(validate=True)`): it checks every field against
the core metadata specification, not just `Requires-Dist`, and its
`ExceptionGroup` of errors is flattened into a single error under the
source's name. So an invalid build result is never persisted, and a
cache file that has become invalid (hand-edited or truncated) is
rejected on read rather than used.

### Scope and refresh
The cache is always on; there are no new command-line options. Its
lifetime is the tree: one build per `dist/metadata_cache`. The cache
is the caller's to refresh -- to force a fresh build, delete the file
(or clean `dist/`). There is no automatic invalidation (see the
trade-off below).

### Behaviour
- The wheel fallback is unchanged and still allowed -- the metadata is
  required regardless of how cheaply the backend can produce it. The
  cache makes that fallback happen at most once per tree instead of
  once per `deps` command.
- A single `deps` command on a tree with no cache builds and validates
  as today, then leaves the file behind for the next one. The one
  behaviour change is validation: it is now full (see below) rather
  than `Requires-Dist`-only, so it rejects more, and the error for
  invalid metadata is reported under the source's name as a single
  `ValueError`.

## Accepted trade-offs

### A stale cache is possible when the tree changes
If `dist/metadata_cache` persists while the tree's
metadata-determining inputs change between runs, the next `deps`
command reads stale metadata. The cache is the caller's to refresh:
the fix is to delete the file (or clean `dist/`). This is accepted
because the tool cannot reliably detect such a change on its own --
PEP 517 gives no way to enumerate a backend's metadata inputs, so
dynamic metadata (version files, build-time dependencies) cannot be
detected as changed -- and because a caller that builds metadata
against a stable tree never hits it.

### Validation is strict
`Metadata.from_email(validate=True)` rejects metadata that is not
spec-conforming -- an unrecognized field, a missing required field, a
field newer than the declared `Metadata-Version` -- even when its
`Requires-Dist` is fine. This is intentional: only spec-valid metadata
is trusted and cached. A backend that emits non-conforming metadata is
rejected rather than silently used.

## Example

```
# Two deps commands run against the same tree:
python -m pyproject_installer deps add metadata metadata --reconfigure --sync
python -m pyproject_installer deps add check \
    --candidates 'metadata_extra tests;metadata_extra test' \
    --reconfigure --sync
```

- first command: `dist/metadata_cache` is absent -> the project's
  metadata is built once (via the `prepare_metadata_for_build_wheel`
  hook, or a full wheel build when the backend does not implement it),
  written to `dist/metadata_cache`, and the source is synced;
- second command: candidate probing and the sync both read
  `dist/metadata_cache` -> no rebuild;
- in total: one metadata build for both commands instead of three or
  more;
- deleting the file (or cleaning `dist/`) drops the cache, so the next
  `deps` run rebuilds it.

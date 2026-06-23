## Abstract
`deps add --sources LIST` adds a batch of explicitly named sources in
one `add` call, from a `;`-separated list of `<name> <type> [args ...]`
entries instead of a single positional `name type [args]` per source. With
`--reconfigure` and `--sync`, one call configures, syncs and verifies a
whole set of declared sources in a single process.

It is the additive sibling of `--candidates`: `--candidates` discovers
**one** source from an ordered list (first that collects wins);
`--sources` adds **all** of an explicit, pre-named list.

## Motivation
A caller may need to declare several dependency sources beyond the one
autodiscovery finds (a second PEP 735 group, a tox testenv) and
configure, sync and verify all of them. One source per `add` means one
call — one process spawn, ~150 ms — per source, carrying N command
strings instead of just the source list. One `add --sources` call
reduces this to a single process carrying just `<name> <type> args;...`,
mirroring `--candidates` for the additive case discovery does not cover.

## Specification

### `--sources LIST`
`LIST` is a `;`-separated string; each entry is `<name> <type>
[args ...]` (space-separated). Example:

```
'src_a pep735 group_a;src_b tox tox.ini env_b'
```

Parsing mirrors `--candidates`: entries are split on whitespace, blanks
dropped, and surrounding/repeated whitespace and a trailing `;` are
harmless. A malformed list is a usage error (`WRONG_USAGE`, 2), not a
skipped entry: an empty/whitespace/`;`-only value (no entries), an entry
with fewer than two tokens (name without a type), an unknown type, or a
name repeated within the list. A wrong argument count is *not* a
parse-time error: like `--candidates` and the single-source `add`, it is
checked against the collector when that entry is configured, raising
`DepsSourcesConfigError` (not `WRONG_USAGE`).

### Per-entry cycle
Entries are handled one at a time, in list order: each is configured,
and with `--sync` synced and verified, before the next — so `--sources`
equals running `add <entry> --reconfigure --sync --verify` once per
entry in one process (sharing `--verify-exclude` /
`--verify-ignore-version`). Configuring behaves exactly as a regular
`add <name> <type> [args]`: without `--reconfigure` an existing name
errors (`Source <name> already exists`); with it the source is kept when
its type and args match, or replaced (stored deps dropped) when they
differ.

Nothing is collected at add time — `--sources` is a declaration, not a
discovery; configuring only records `type`/`args`. With `--verify`, the
first source that is out of sync raises `DepsUnsyncedError` and exits
`SYNC_VERIFY_ERROR` (4); later entries are never reached — not synced,
not configured. (A freshly added or replaced source has no stored deps,
so its first `--verify` is always out of sync.) A source that cannot be
collected fails the same way at its sync step (the normal collect
failure), never a silent skip — so there is no `--sources` analog of the
no-candidate exit (5). A failed run leaves earlier entries configured
and synced and later ones untouched; running without `--verify`
configures and syncs the whole list in one pass (`--verify` is a check
and keeps stopping at the first out-of-sync entry).

Because there are no positionals, the `name`-before-`--verify-exclude`
ordering caveat does not arise. Programmatic API:
`DepsSourcesConfig.add(..., sources=(...))`, where `sources` is an
ordered tuple of `(srcname, srctype, *srcargs)`, mutually exclusive with
`srcname`/`srctype`/`candidates`; `add()` runs its single-source code
per entry, so the first `DepsUnsyncedError` stops the rest.

### Mutual exclusion
`--sources` carries its own names, takes **no positional arguments**,
and is mutually exclusive with the positional `name`/`type`/`args` and
with `--candidates`. The positional `name` becomes optional; exactly one
mode must be given (more than one, or `--sources` with a positional, is
`WRONG_USAGE`, 2):

- `add <name> <type> [args]` — one explicit source;
- `add <name> --candidates LIST` — one discovered source;
- `add --sources LIST` — a batch of explicit named sources.

## Example

```
python -m pyproject_installer deps add \
    --sources 'src_a pep735 group_a;src_b metadata_extra extra_b' \
    --reconfigure --sync --verify --verify-exclude 'excluded-dep'
```

- neither configured → first added and synced, out of sync on verify →
  exit 4; second never reached;
- both recorded with the same type/args → kept; `--verify` passes if
  neither's deps changed;
- one now differing (type or args) → replaced, deps dropped, out of sync
  → exit 4;
- one that cannot be collected → collect failure at sync, an error, not
  skipped.

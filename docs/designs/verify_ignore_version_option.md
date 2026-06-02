## Abstract
This RFE proposes a new opt-in `deps sync` option
`--verify-ignore-version` that excludes from the verify diff any
dependency whose only change is its version specifier. Intended for
downstream packagers - primarily RPM - who run `deps sync --verify`
as a drift gate and don't want it to fail (and force a re-sync
commit) every time an upstream project tightens a version bound,
such as `setuptools<81` -> `setuptools<82`.

## Motivation
`deps sync --verify` re-collects each source's requirements,
compares them with the stored set, and - if anything differs -
prints a `new_deps`/`extra_deps` diff and exits with
`SYNC_VERIFY_ERROR` (4). A pure version-bound change shows up as
the same distribution on both sides of that diff:

```
"setuptools<81,>=78.1.1"   stored    -> extra_deps
"setuptools<82,>=78.1.1"   collected -> new_deps
```

For RPM packaging those versioned upper bounds are usually
irrelevant - the distro ships its own setuptools - yet every such
bump fails the gate, forcing the maintainer to re-sync and commit a
`pyproject_deps.json` change that carries no packaging-relevant
information. Across many packages this is constant diff noise.

The existing `--verify-exclude <regex>` already drops chosen
distributions from the diff, but it requires enumerating names up
front and it hides a dependency entirely - including its genuine
addition or removal. Version bumps happen to *any* dependency and
can't be predicted, and the maintainer still wants to learn about
real add/remove events. A dedicated option that targets only the
"version moved, nothing else" case is the right tool.

The option is opt-in because the default behaviour (fail on any
difference) must stay unchanged for callers who rely on it.

## Specification

### User-facing contract
- `--verify-ignore-version` is declared on the `deps sync`
  subparser only, `action="store_true"`, default off.
- Requires `--verify`. Used without it, CLI validation fails with
  `--verify-ignore-version option must be used with --verify` and
  exit code `WRONG_USAGE` (2), mirroring `--verify-exclude`.
- Programmatic API: `DepsSourcesConfig.sync(...,
  verify_ignore_version=False)`. Passing it without `verify=True`
  raises `ValueError("verify_ignore_version must be used with
  verify")`.
- Composes with `--verify-exclude`: both filters apply to the diff.

### What counts as a version-only change
A dependency is version-only when the stored and collected
requirements are equal in every PEP 508 field except the version
specifier - i.e. same PEP 503-normalized name, extras, environment
marker and url. Such a dependency lands on *both* sides of the diff
(in `new_deps` from the collected side and `extra_deps` from the
stored side); the intersection of the two sides, compared without
specifiers, is exactly the set of version-only changes.

A dependency that is genuinely added or removed appears on only one
side and is kept. A change to extras, marker or url - even
alongside a version change - makes the two requirements differ in a
non-version field, so they no longer match and both are kept.
Gaining or losing a specifier where the rest is unchanged (e.g.
`foo` -> `foo>=1`) is version-only.

### Behaviour
With `--verify --verify-ignore-version`:

- version-only changes are removed from the printed
  `new_deps`/`extra_deps` diff;
- if, after that removal (and any `--verify-exclude` removal), no
  differences remain, the command succeeds (exit 0) instead of
  raising `SYNC_VERIFY_ERROR`;
- genuine additions/removals and extras/marker/url changes still
  appear in the diff and still fail.

Like `--verify` and `--verify-exclude`, the option does **not**
change the on-disk write: each out-of-sync source's stored `deps`
is still rewritten to the freshly collected set, including the new
version bounds. The option governs the diff and the pass/fail
decision only, not what is persisted.

## Example

```
# Drift gate that tolerates upstream version-bound bumps.
python -m pyproject_installer deps sync --verify \
    --verify-ignore-version build
```

Given a `build` source stored as `setuptools<81,>=78.1.1` whose
project now declares `setuptools<82,>=78.1.1`:

- `deps sync --verify build` prints

  ```json
  {
    "build": {
      "extra_deps": [
        "setuptools<81,>=78.1.1"
      ],
      "new_deps": [
        "setuptools<82,>=78.1.1"
      ]
    }
  }
  ```

  and exits 4;
- `deps sync --verify --verify-ignore-version build` prints nothing
  and exits 0.

If the project instead *added* `tomli>=2`, that dependency still
appears in `new_deps` and the command still exits 4, even with
`--verify-ignore-version`.

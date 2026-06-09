## Abstract
This RFE proposes an opt-in `deps add --candidates` option that
picks the source to add from an ordered candidate list — the first
candidate that exists in the project — instead of a fixed
`<type> <args>`. Together with `--reconfigure` and
`--sync` it lets one `add` call autodiscover a source (for example
a project's test dependencies), reconfigure it, and verify it in a
single process.

## Motivation
Downstream packaging discovers a project's test-dependency source
by trying a list of likely places — PEP 735 groups (`test`,
`tests`, ...), a tox testenv, poetry groups, common
test-named requirements files — and using the first that is
present. Implemented in shell, that walk is one `add` + `sync`
(+ `delete`) probe per candidate against a throwaway config — two
or three `python -m pyproject_installer` spawns each, so a
~20-candidate list is tens of spawns at ~150 ms apiece. Moving the walk into one `add
--candidates` call does the whole probe in a single process.

## Specification

### `--candidates LIST`
Declared on `deps add`. `LIST` is a `;`-separated string; each
entry is `<type> [args ...]` (space-separated) — the same shape as
`add`'s positional `type [args]`. Example:

```
'pep735 test;pep735 tests;tox tox.ini testenv;pip_reqfile test-requirements.txt'
```

### First existing wins
The candidate list is validated up front: an unknown type or the
wrong number of arguments means the list itself is malformed, which
is an error, not a skip. The validated entries are then walked left
to right, and the **first candidate that collects
successfully** is picked — its source is present and collectable — even if it
yields zero dependencies. A candidate is skipped when its collect
fails for any reason (a missing file or group, or data that cannot be
parsed): a source that cannot be collected is not a usable source, so
the walk moves on. If no candidate collects, none is picked,
which is an error (see below). There is no dependency-count or
dependency-content check (a future option could add "must contain a
distribution matching X").

### Mutual exclusion
`--candidates` is only the source of the picked candidate's `type`/`args` — a
discovered substitute for the positional `type [args]`. Every other
aspect of `add` (add-only by default, `--reconfigure`, `--sync` and
its verify options) behaves exactly as with explicit `type args`.

So `--candidates` and the positional `type [args]` are mutually
exclusive; giving both is a usage error (`WRONG_USAGE`, 2). With
`--candidates`, `name` is the only positional argument.

### Adding the picked candidate
The picked candidate only supplies `name`'s `type`/`args`; it is then
handled exactly as a regular `add <name> <type> <args>`,
`--reconfigure` included — `--candidates` special-cases nothing here.
So without `--reconfigure` an already configured `name` errors
(`Source <name> already exists`); with it the source is kept when the
picked candidate matches or replaced (dropping stored deps) when it
differs.

When **no candidate is picked** — none of them collects —
`add` reports it and exits with a dedicated exit code (5, distinct
from the verify code 4), in **every** case: whether or not `name` is already
configured, and whether or not `--reconfigure` is given. An existing
source under `name` is left untouched. Because the add part did not
succeed, `--sync` never runs on a no-candidate branch — and since
`--verify` depends on `--sync`, neither runs.

### Composition
Composes with `--reconfigure` and `--sync`. The full
discover → reconfigure → verify in one process is:

```
add <name> --candidates '<list>' --reconfigure --sync --verify
```

As with explicit `type args`, when `--verify-exclude` is used the
`name` positional must come **before** it (or use the
`--verify-exclude=PATTERN` form), since `--verify-exclude` is
`nargs="+"` and would otherwise fold `name` into the pattern list.
With `--candidates`, `name` is the only positional, so placing it
first is enough.

Programmatic API: `DepsSourcesConfig.add(..., candidates=(...))`.

## Example

```
# name first (before --verify-exclude, which is nargs="+")
python -m pyproject_installer deps add check_autodiscovery \
    --candidates 'pep735 test;pep735 tests;pip_reqfile test-requirements.txt' \
    --reconfigure --sync --verify --verify-exclude 'pytest-cov' 'flake8$'
```

- first of those that exists → recorded as `check_autodiscovery`,
  then synced and verified (a newly recorded source drifts → exit
  4);
- already recorded as the same candidate (same type and args) → kept;
  `--verify` passes if its deps are unchanged;
- already recorded but the candidate now differs (different type or
  args) → replaced, its stored deps dropped → drift → exit 4;
- none of them collect → reported, exit 5 (the dedicated no-candidate
  code); sync does not run and any existing `check_autodiscovery` is
  left untouched.

## Abstract
This RFE proposes two opt-in `deps add` options that let a single
`add` call replace the `show <name> || add <name> <type> <args>`
followed by `sync <name> ...` sequence a downstream packager runs
per source:

- `--reconfigure` makes `add` idempotent -- keep the
  source when its type and args are unchanged, replace it when they
  differ -- instead of erroring on an existing name.
- `--sync` runs a sync on the source in the same process after any
  successful `add` (newly added, kept unchanged, or replaced),
  reusing the existing `sync` verify options.

## Motivation
Downstream packaging (RPM) configures every dependency source in a
build's `%prep` with the same two steps:

```
show <name> 1>/dev/null 2>&1 || add <name> <type> <args>
sync <name> --verify [--verify-exclude ...]
```

For a typical project that is `pep518`, `pep517`, `metadata`, and
one or more check sources -- two to three `python -m
pyproject_installer` process spawns per source, where interpreter
startup dominates the cost. Two facts force the extra spawns:

- `add` raises when the source already exists, so the `show ||`
  guard is needed every build even though a committed
  `pyproject_deps.json` already lists the source;
- `add` cannot sync, so a separate `sync` invocation is needed.

Folding both into `add` cuts the per-source cost to one process and
removes the guard. The options are opt-in; default `add` behaviour
is unchanged.

## Specification

### `--reconfigure`
Declared on the `deps add` subparser, `action="store_true"`,
default off.

- source not configured -> add it (current behaviour);
- configured with the **same** `type` and `args` -> no-op, exit 0
  (this is the `show ||` case);
- configured with a **different** `type` or `args` -> remove the
  source together with its stored `deps`, then add the new one.

Without the flag, adding an already-configured name still fails
with `Source <name> already exists`, unchanged.

Programmatic API: `DepsSourcesConfig.add(..., reconfigure=False,
sync=False, verify=False, verify_excludes=(),
verify_ignore_version=False)`.

### `--sync`
Declared on `deps add`, `action="store_true"`, default off. When set,
`add()` syncs `name` itself after configuring it, in the same process --
the sync lives in the library method, not a separate CLI step.
Independent of `--reconfigure`: `add --sync name type args` (no
`--reconfigure`) adds a new source then syncs it; with `--reconfigure`
it also syncs after a kept or replaced source. Either way, sync runs
only when the add succeeded.

`--sync` and the sync options -- `--verify`, `--verify-exclude`,
`--verify-ignore-version` -- are `add()` parameters. They are declared
on the `add` subparser with the same `add_sync_options` helper (built
on `add_deps_argument`) that `sync` uses, so they are forwarded through
`main_args` to `add()`, which passes the verify options on to its own
`sync()` call. Because `--verify-exclude` takes one or more values
(`nargs="+"`), the source `name` and `type` must be given **before** the
verify options (or use the `--verify-exclude=PATTERN` form); otherwise
argparse greedily folds the positionals into the exclude list.

### Usage validation
Mirrors the existing checks, exit `WRONG_USAGE` (2):

- the sync/verify options require `--sync`;
- `--verify-exclude` and `--verify-ignore-version` require `--verify`.

### Behaviour
`add --sync --verify` performs add-or-reconfigure then sync in one
process. The sync step runs **only if the add/reconfigure part
succeeded**; a failed add does not proceed to sync. The verify
outcome is delegated to the existing sync, so a drift exits
`SYNC_VERIFY_ERROR` (4). A source freshly added (or
replaced, hence with no stored deps) drifts on its first
`--verify`. With neither option set, `add` is exactly as today.

## Example

```
# Configure-or-reconfigure a source and verify it, in one call.
# Note: name/type come before --verify-exclude (nargs="+").
python -m pyproject_installer deps add pep517 pep517 \
    --reconfigure --sync --verify --verify-exclude 'wheel$'
```

- pep517 not configured -> added, then synced; new source -> drift ->
  exit 4.
- pep517 already configured as `pep517 pep517` -> kept; sync
  re-collects and `--verify` passes if its deps are unchanged.
- pep517 configured with different args -> replaced, then synced ->
  drift -> exit 4.

## Abstract
This RFE splits the CLI's two output channels by purpose and makes the
commands report their progress:

- **Diagnostics go to stderr.** All `logging` records, every level,
  are emitted on stderr. `stdout` is reserved exclusively for the
  machine-readable *data* a command is asked to produce.
- **Levels reflect intent.** A source-registry mutation or a
  command's start/finish status is `INFO` (shown by default); plumbing,
  no-ops, and internal walk detail are `DEBUG` (shown only under
  `-v`).
- **Commands report start and finish.** Each `deps` subcommand brackets
  its work with an `INFO` start line and an `INFO` finish line on
  stderr, as the top-level `build`/`install`/`run` commands already do.
  The display-only `show` is the exception: it writes its data to
  `stdout` and emits no diagnostics.

Only `deps eval`, `deps show`, and `deps sync --verify` write data to
`stdout` (via `sys.stdout.write`); `build` reports its result through
the `.wheeltracker` file, not `stdout`. So no command outside `deps`
has a `stdout` data contract, and moving all logging to stderr breaks
none of them.

## Motivation
`setup_logging` currently routes `INFO` and `DEBUG` to `stdout` and
`WARNING`+ to `stderr`. But three `deps` commands also write data to
`stdout`:

- `eval` -- the formatted dependency list;
- `show` -- the config as JSON;
- `sync --verify` -- the unsynced diff as JSON.

Any log record on `stdout` interleaves with that data and corrupts it
for the tool consuming it. Sending all diagnostics to `stderr` is the
conventional Unix split (data on `stdout`, diagnostics on `stderr`):
it keeps the data commands pristine at *any* verbosity and lets each
message use the level it deserves, instead of being forced to `DEBUG`
just to keep `stdout` clean.

## Specification

### Stream split
`setup_logging` emits all records on a single
`StreamHandler(sys.stderr)`. The separate `stdout` handler and the
`emit_less_than_warning` filter are removed. The level is `DEBUG`
when `-v/--verbose` is given, `INFO` otherwise; the existing formats
are unchanged. After this, `stdout` carries only the explicit
`sys.stdout.write` data of `deps eval`/`show`/`sync --verify`.

### Level policy
- `INFO` -- a change to the source registry the user asked for, or a
  command's start/finish status. Visible by default.
- `DEBUG` -- plumbing (config load/save, default-config init),
  no-ops, and candidate-walk detail. Visible only under `-v`.

The categories above cover the records the `deps` commands emit; the
exact wording and level of each record live in the code and its tests,
not here.

### Per-command status (`deps`)
Each subcommand maps to a `DepsSourcesConfig` method (`deps_command`
dispatches via `getattr(config, action)`). Each brackets its work with
two `INFO` lines on `stderr` -- a start (configuring, deleting, syncing,
evaluating) and a finish reporting the outcome (configured, deleted,
synced, evaluated) -- so neither touches the data the command writes to
`stdout`. `show` is the exception: it only displays the stored config to
`stdout` and emits no diagnostics. `sync --verify` keeps its existing
contract: the diff is written to `stdout` and `DepsUnsyncedError` is
raised (the dispatcher exits `SYNC_VERIFY_ERROR`).

### Per-command status (top-level)
`build`/`install`/`run` already end with an `INFO` result line; the
audit confirmed each does, so none required a change and no unrelated
logging is touched.

### Compatibility and behaviour changes
- `build`/`install`/`run` progress moves from `stdout` to `stderr`.
  The documented filename-capture path is `{OUTDIR}/.wheeltracker`
  (read back by `install`), which is unaffected, so no data contract
  changes.
- `run` streams the child's `stdout` through `logger.info`; that
  child `stdout` now lands on the process `stderr` (child `stderr`,
  via `logger.error`, was already there).
- `deps eval`/`show`/`sync --verify` produce clean `stdout` at any
  verbosity, including `-v`.

## Example

```console
# The verify diff on stdout stays clean even with -v; all progress
# and status go to stderr (here discarded), so the data on stdout can
# be captured or piped without interleaved log lines.
$ python -m pyproject_installer -v deps sync --verify check 2>/dev/null
{
  "check": {
    "new_deps": [
      "pytest"
    ]
  }
}
```

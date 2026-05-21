## Abstract
This RFE proposes a `completion` subcommand that emits a small bash
wrapper. The wrapper sets `COMP_WORDS`, `COMP_CWORD`, and a sentinel
env var, then re-invokes the binary at TAB time; the binary detects
the sentinel and routes to an in-Python autocomplete handler that
walks the argparse tree, computes candidates from the current cursor
context, prints them one per line, and exits. Bash captures stdout
into `COMPREPLY`. Inspired by pip's design.

As prerequisites the project also gains a `pyproject-installer`
console-script entry (so bash has a binary name to bind completion
to) and the self-hosted backend learns to emit
`dist-info/entry_points.txt` from PEP 621 `[project.scripts]`.

No completion artefact is checked into the repository, no completion
file is shipped inside the wheel, no `tools/`-side generator or CI
drift gate is required, and the wrapper has no per-CLI knowledge so
it cannot drift even in principle: the wrapper is invariant in
`parser.prog` only, and the binary's live argparse tree is the
single source of truth for every TAB press.

## Motivation
Interactive users of `pyproject-installer` benefit from tab completion
of subcommands, option names, finite-choice option values (e.g.
`deps add ... <srctype>`) and path arguments. The dominant deployment target -
RPM packaging - already has an idiomatic place for completion files
(`%{_datadir}/bash-completion/completions/<name>`); a `completion`
subcommand lets the spec generate that file at package build time
without forcing the upstream wheel to ship a static artefact.

A static checked-in completion file would have required:

- a `tools/`-side generator and a CI drift gate (regenerate, diff,
  fail-on-diff) - because the file and the parser would be in two
  places that must be kept synchronised;
- a decision about whether to ship the file inside the wheel, which
  in turn would require the self-hosted backend to learn `.data/data/`
  routing.

Routing TAB presses back through the binary removes both problems by
construction. The wrapper has no per-CLI specifics (only `parser.prog`
appears in it), and every TAB press reads the live argparse tree, so
the script and the CLI it completes are always the same object walked
the same way.

The runtime cost is one Python interpreter spawn per TAB press,
typically 50-100 ms on a warm system. This is on the upper end of
what feels instantaneous, but bash users are familiar with similar
latency from other completion implementations (pip, gh, kubectl).

## Specification

### User-facing contract
- Syntax: `pyproject-installer completion bash`. Equivalent to
  `python -m pyproject_installer completion bash`.
- The subcommand takes exactly one positional, the shell name. Only
  `bash` is recognised today; other values produce the standard
  argparse error path (usage line on stderr, exit code
  `ExitCodes.WRONG_USAGE`). The positional is declared with
  `choices=SUPPORTED_SHELLS` to make the supported set discoverable
  via `--help` and trivially extensible later (`zsh`, `fish`, ...).
- Output is written to stdout: the bash wrapper, ~7 lines. No other
  side effects: nothing is read from disk, no environment variables
  are consulted, the working directory is not changed.
- Exit code: `ExitCodes.OK` on success.
- Output is deterministic for a fixed `parser.prog`: byte-identical
  across runs.

### Generated wrapper

The complete output for `parser.prog = "pyproject-installer"`:

```bash
_pyproject_installer()
{
    local IFS=$' \t\n'
    COMPREPLY=( $( COMP_WORDS="${COMP_WORDS[*]}" \
                   COMP_CWORD=$COMP_CWORD \
                   _PYPROJECT_INSTALLER_COMPLETE=1 "$1" 2>/dev/null ) )
}
complete -o nosort -F _pyproject_installer pyproject-installer
```

- `$1` is bash's standard convention for the command name passed to
  the completion function. The wrapper re-executes that binary.
- `_PYPROJECT_INSTALLER_COMPLETE=1` is the sentinel that switches
  `cli_entry` into autocomplete mode (see below). The leading
  underscore signals "internal protocol; do not set manually."
- `stderr` is suppressed so partial errors from the autocomplete
  handler never leak into the user's terminal mid-TAB.
- `-o nosort` preserves the order in which the handler emits
  candidates, so subcommands display before option names rather than
  getting interleaved by bash's default lexicographic sort.
- The wrapper is invariant in the argparse tree's shape; only
  `parser.prog` is consulted (to name the bash function and the
  `complete -o nosort -F` target).

### Runtime dispatch

`cli_entry` (the console-script entry) checks for the sentinel before
normal argparse processing:

```python
def cli_entry() -> None:
    if os.environ.get("_PYPROJECT_INSTALLER_COMPLETE") == "1":
        from .completion_cmd._autocomplete import run_autocomplete
        run_autocomplete(main_parser("pyproject-installer"))
    main(sys.argv[1:], prog="pyproject-installer")
```

When the sentinel is set, `run_autocomplete` reads `COMP_WORDS` and
`COMP_CWORD` from the environment, calls `compute_candidates`, prints
the candidates one per line to stdout, and exits with code 0
(or 1 if the env vars are missing/malformed).

`compute_candidates(parser, words, cword) -> list[str]` is a pure
function: given the words list and cursor index, it returns the
filtered candidates. The dispatch tree:

1. **Value-option context** - `prev` (word right before the cursor) is
   a value-taking option on the active parser: offer that option's
   value candidates. `--outdir <TAB>` (metavar=DIR) lists directories;
   `--srctype <TAB>` (choices=) lists the choices; `--installer <TAB>`
   (no path metavar, no choices) offers nothing.
2. **Option-name context** - `cur` (word under the cursor) starts with
   `-`: offer option names from the active parser, with
   mutually-exclusive group siblings suppressed.
3. **Subcommand context** - the active parser has subparsers: offer
   subcommand names + the parser's own option names (so
   `pyproject-installer <TAB>` shows `build install run deps
   completion --help -v ...`).
4. **Positional context** - the active parser has no subparsers:
   count which positional slot the cursor is on (skipping option tokens
   and values consumed by value-taking options) and offer that slot's
   completion. A slot with `choices=` offers those choices; a slot
   with a path-flavored `metavar` (`DIR`/`FILE`/`PATH`) offers paths.
   Variadic positionals (`nargs in ("*", "+")`) absorb every slot from
   their declaration onward. When no positional has anything to offer
   (no positionals at all, a positional with neither `choices=` nor a
   path metavar, or a slot past the fixed ones with no variadic), fall
   back to the parser's own option names so the user sees something
   actionable instead of an empty completion.

The "active parser" is reached by walking the subparser tree from
the top, consuming any token that names a subparser registered on the
current parser. So `deps add NAME <TAB>` walks to the `add` parser
(via `deps`), sees `["NAME"]` as its `parser_argv`, and
recognises that the cursor is at positional slot 1 (`srctype`).

### Value candidates

`_value_candidates(action, current_word)` picks the candidates for an
argument's value with a small priority chain:

1. `action.choices` set -> offer the choices (sorted).
2. Else look at `action.metavar`, case-insensitively:
   - `DIR` -> directories only;
   - `FILE` / `PATH` -> directories AND regular files;
   - anything else (or no metavar) -> no candidates. Opaque strings
     (`--installer NAME`, `--backend-config-settings JSON`, regex
     lists, ...) deliberately offer nothing rather than a misleading
     filename fallback.

Path completion is therefore driven entirely by `metavar`. To enable
directory or file completion for a new option, declare
`metavar="DIR"` or `metavar="FILE"` on its `add_argument` call. The
test `tests/unit/test_completion/test_path_metavars.py` walks the
live parser and fails CI if a `type=Path` action is added without a
path-flavored metavar, so the contract between the CLI shape and the
completion engine cannot silently drift.

Actions with no value to complete (`store_true/false/const`, `count`,
`--help`, `--version`) never reach this function: they're filtered out
of the value-taking option set by `_value_taking_options` via
`action.nargs != 0`.

### Terminating options (``--help`` / ``--version``)

Before the four-way dispatch fires, `compute_candidates` checks
whether any `_HelpAction` or `_VersionAction` option string already
appears in *parser_argv*. If so it returns `[]` immediately:
those actions call `parser.exit()` as soon as argparse parses them,
so the binary will print help (or the version) and exit before the
shell ever runs whatever the cursor word becomes. Matches git's and
pip's behaviour: `pyproject-installer --help <TAB>` offers nothing.

### Option-name filtering

`_option_name_candidates` applies two suppression rules whenever
option names are offered (branches 2, 3, and the branch-4 fallback
all funnel through it):

1. **Mutually-exclusive groups.** Argparse exposes group membership
   via `parser._mutually_exclusive_groups`, each group carrying its
   own `_group_actions`. If any member is already on the command
   line, every member is dropped - siblings because argparse would
   reject them, and the typed member itself because re-offering it
   is misleading. So typing `install --platlib --<TAB>` offers
   neither `--purelib` nor `--platlib`.
2. **Non-repeatable options already typed.** Any option whose action
   is *not* one of `append` / `append_const` / `count` / `extend` is
   dropped from the candidate list once it (or any of its aliases)
   appears on the line. So once `--help` is typed, neither `--help`
   nor `-h` is offered again; a value option like `--depsconfig`
   stops being suggested after its value is given; but a `count`
   option like `-v` stays available so the user can stack `-v -v`.

Both rules are generic: future mutually-exclusive groups and any
new options anywhere in the CLI receive the same treatment with no
code changes.

### End-of-options sentinel (``--``)

A bare `--` on the command line ends option parsing in argparse:
every word after it is treated as a positional even if it looks
option-shaped (e.g. `install -- --weird-filename.whl` fills the
`wheel` positional with `--weird-filename.whl`). The dispatcher
matches that semantic:

- `_positional_candidates` flips an "after `--`" flag in its slot
  counter, so words past the sentinel count as positionals regardless
  of leading `-`.
- Branches 1 and 2 (value-option context, option-name context) and
  the branch-4 option-name fallback all suppress themselves when
  `--` has already been committed on the line, because argparse
  would reject further options. So `install -- foo.whl <TAB>`
  returns no candidates: the wheel positional is filled, no more
  positionals exist, and options are no longer accepted.

A `--` typed as the cursor word itself (e.g. `install --<TAB>`) is
not counted as committed - branch 2 still fires and offers option
names. Only a `--` already in the COMP_WORDS prefix activates the
suppression.

### Path candidates

`_path_candidates(current_word, *, dirs_only)` lists filesystem
entries matching the cursor word as prefix via `pathlib.Path.glob`.
Directories carry a trailing `/` so bash treats them as continuation
points (cursor stays on the same word). When `dirs_only=True`
(metavar=DIR) regular files are filtered out so the user only sees
directories; when `dirs_only=False` (metavar=FILE/PATH) both are
offered. An unreadable parent directory returns an empty list rather
than crashing the TAB press.

### Console-script entry
A `[project.scripts]` table in `pyproject.toml`:

```toml
[project.scripts]
pyproject-installer = "pyproject_installer.__main__:cli_entry"
```

`cli_entry()` is a wrapper added to `__main__.py` that either routes
to `run_autocomplete` (when the sentinel env var is set) or falls
through to the normal `main()` flow.

The existing `python -m pyproject_installer` entry continues to work
unchanged; both entries call `main()` with the same `cli_args` and
differ only in the `prog` string surfaced in help output and in the
generated completion wrapper's `complete -F ... <prog>` registration.

### Backend prerequisite: `entry_points.txt`
The self-hosted backend in `backend/` currently emits only the wheel
members listed in `WheelBuilder.package_*` (modules, WHEEL, METADATA,
license files, RECORD). It does not emit `dist-info/entry_points.txt`.
Without that file the install pipeline's existing console-script
generator (`src/pyproject_installer/install_cmd/_install.py:237`) has
nothing to act on, so the `pyproject-installer` binary would not be
created at install time.

The backend's PEP 621 metadata parser already has access to
`[project.scripts]` (it round-trips through core metadata as part of
PEP 621 ingestion). The backend gains a single new method,
`WheelBuilder.package_entry_points(scripts: Mapping[str, str])`, that
emits the canonical `entry_points.txt` (INI-style `[console_scripts]`
section) via `configparser` with `optionxform = str` to preserve
entry-point name case.

### Install variants
Two documented ways to use the wrapper. Both feed from the same
`pyproject-installer completion bash` output; they differ only in
where that output lands.

```bash
# 1. End-user one-shot install. The bash-completion package picks it
#    up lazily on the next new shell.
mkdir -p ~/.local/share/bash-completion/completions
pyproject-installer completion bash \
    > ~/.local/share/bash-completion/completions/pyproject-installer

# 2. End-user eval-on-startup.
eval "$(pyproject-installer completion bash)"
```

The wrapper requires only the `complete` builtin and stderr
redirection; no `bash-completion` package helpers are referenced.
The actual TAB-time logic runs in Python and requires
`pyproject-installer` to be reachable on the user's `PATH` - which
it has to be for the user to invoke the tool anyway.

### Module layout
A package `src/pyproject_installer/completion_cmd/` mirrors the
existing `build_cmd` / `install_cmd` / `run_cmd` / `deps_cmd` layout:

```
src/pyproject_installer/completion_cmd/
    __init__.py        # SUPPORTED_SHELLS dispatch dict + completion_command
    _bash.py           # wrapper template + emit()
    _autocomplete.py   # runtime: introspection + compute_candidates + run_autocomplete
```

`SUPPORTED_SHELLS` in `__init__.py` is the single source of truth for
which shells are supported (used both by argparse `choices=` and by
the dispatcher).

### Out of scope
- Other shells (`zsh`, `fish`, `powershell`). The `choices=SUPPORTED_SHELLS`
  positional reserves the dispatch surface; adding a shell is a
  matter of writing a sibling `_zsh.py` and adding an entry to
  `SUPPORTED_SHELLS`. The autocomplete runtime is shell-agnostic.
- Dynamic completion that consults disk state beyond filesystem
  paths (e.g. completing wheel filenames against
  `dist/.wheeltracker`). The architecture supports this trivially
  - it'd just be additional `_value_candidates` logic - but it's not
  in scope for this RFE.
- Shipping the wrapper inside the wheel. Wheel-side `.data/data/`
  packaging is a separate concern, not required by this RFE.

## Example

```bash
# Generate and install for the current user.
mkdir -p ~/.local/share/bash-completion/completions
pyproject-installer completion bash \
    > ~/.local/share/bash-completion/completions/pyproject-installer

# In a new shell:
pyproject-installer <TAB><TAB>
build  completion  deps  install  run

pyproject-installer deps <TAB><TAB>
add  delete  eval  show  sync

pyproject-installer deps add mysrc <TAB><TAB>
hatch  metadata  pdm  pep517  pep518  pep735  pip_reqfile  pipenv  poetry  tox

pyproject-installer install --<TAB><TAB>
--destdir              --installer            --no-strip-dist-info
--exclude-paths        --platlib              --purelib
--help                 --rpm-filelist

pyproject-installer install --platlib --<TAB><TAB>
--destdir              --installer            --no-strip-dist-info
--exclude-paths        --platlib              --rpm-filelist
                                              # --purelib suppressed
```

For RPM packaging:

```rpm-spec
%install
...
mkdir -p %{buildroot}%{_datadir}/bash-completion/completions
%{python3} -m pyproject_installer completion bash \
    > %{buildroot}%{_datadir}/bash-completion/completions/pyproject-installer

%files
...
%{_datadir}/bash-completion/completions/pyproject-installer
```

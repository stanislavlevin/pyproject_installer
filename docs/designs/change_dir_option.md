## Abstract
This RFE proposes a global `-C <dir>` option that changes the working
directory before dispatching any subcommand. It matches the semantics of
`make -C`, `git -C`, and `tar -C`: a true `chdir` performed once, early in
`main()`.

## Motivation
Every existing subcommand derives at least one default path from
`Path.cwd()`:
- `build` takes `srcdir` from cwd.
- `install` / `run` look up the wheel via `{cwd}/dist/<WHEEL_TRACKER>`.
- `deps` reads `{cwd}/<DEFAULT_CONFIG_NAME>` and each collector calls
  `Path.cwd()` at runtime.

Today, operating on a project that isn't the shell's current directory
requires wrapping every invocation with `cd <dir> && python -m
pyproject_installer ...` (and restoring cwd afterwards). RPM specs and
other packaging macros frequently know the source tree absolute path up
front; passing it as a flag is more ergonomic than composing a shell
sequence, and it removes the need for callers to manage cwd state.

A single top-level option keeps the surface small: one flag replaces
four per-subcommand variants, and every future subcommand inherits the
behaviour for free.

## Specification

### User-facing contract
- Syntax: `python -m pyproject_installer -C <dir> <subcommand> [args...]`.
- `-C` is declared on the top-level `MainArgumentParser`, so it must
  appear **before** the subcommand token. There is no long alias and no
  per-subcommand variant.
- `<dir>` must be a directory that exists and is accessible. Failures
  produce the standard argparse error path (usage line on stderr, exit
  code 2). If `<dir>` is present but empty (e.g. `-C ""`), the current
  working directory is left unchanged.
- The flag is a true `chdir`: after the option is applied, the process
  cwd is `<dir>`. Relative paths passed elsewhere on the same command
  line (for example, `-C ../pkg install dist/foo.whl`) resolve against
  the new cwd (`../pkg/dist/foo.whl`). Relative paths passed as the
  `-C` value itself resolve against the original cwd (standard argparse
  behaviour: the tool only sees the string the shell produced).
- When `-C` is absent, behaviour is byte-identical to the current
  release.

### Implementation
Edits are confined to `src/pyproject_installer/__main__.py`.

1. Add the option on the top-level parser near the existing
   `-v` / `--version` block:
   ```python
   parser.add_argument(
       "-C",
       dest="cwd",
       type=Path,
       default=None,
       metavar="dir",
       help="change to dir before running subcommand (default: cwd)",
   )
   ```
   The `dest` is `cwd` so reading code (`if args.cwd is not None`) is
   self-documenting.

2. Defer the two argparse defaults that currently freeze cwd at
   parser-construction time:
   - `parser_build.add_argument("srcdir", ..., default=Path.cwd())` →
     `default=None`; compute `args.srcdir = args.srcdir or Path.cwd()`
     inside the `build` entry function.
   - `parser_deps.add_argument("--depsconfig", ...,
     default=Path.cwd() / DEFAULT_CONFIG_NAME)` → `default=None`;
     compute the fallback inside the `deps` dispatch before it is used.

   This change has a small independent benefit: the `--help` output
   no longer embeds the cwd as observed at import time.

3. Perform the `chdir` in `main()` between logging setup and
   subcommand dispatch:
   ```python
   setup_logging(verbose=args.verbose)
   if args.cwd is not None:
       try:
           os.chdir(args.cwd)
       except OSError as exc:
           parser.error(f"-C: {exc}")
       logger.debug("Changed working directory to %s", Path.cwd())
   args.main(args)
   ```
   The single `except OSError` covers `FileNotFoundError`,
   `NotADirectoryError`, `PermissionError`, and their siblings.
   `parser.error()` produces the conventional argparse failure output
   (usage line + exit 2). The debug log is gated by `-v` and serves as
   an operational breadcrumb; it is not considered part of the stable
   contract.

No changes are needed in `lib/backend_helper/backend_caller.py` (the
stdlib-only subprocess inherits cwd from its parent), in the deps
collectors (all `Path.cwd()` calls there are runtime), or in the
`build_cmd` / `install_cmd` / `run_cmd` internals.

### Data flow
1. Python starts with the shell's cwd.
2. `main_parser()` builds the argparse tree (no cwd-frozen defaults).
3. `parser.parse_args()` yields a namespace; `args.cwd` is either
   `None` or a `Path`.
4. `setup_logging(...)` is configured on stdout / stderr streams only.
5. If `args.cwd` is set, `os.chdir` is attempted; failures bail via
   `parser.error`. On success, a debug log is emitted.
6. `args.main(args)` dispatches. Any runtime `Path.cwd()` call and the
   deferred argparse fallbacks all resolve against the new cwd.
7. Subprocesses spawned by the tool inherit the new cwd automatically.

The original cwd is intentionally not preserved: nothing in the tool
needs it, and storing it would invite downstream callers to reinvent
`git -C`'s hybrid semantics, which this design rejects.

### Error handling
Failure modes are handled at the single `except OSError` site:
- Missing path → `FileNotFoundError`: `-C: [Errno 2] No such file or
  directory: '<path>'`.
- Path is a file → `NotADirectoryError`.
- Path is unreadable → `PermissionError`.
- Any other `OSError` (symlink loop, ENAMETOOLONG, etc.).

All produce the same argparse-style error output and exit code 2.
There is no pre-flight `Path.is_dir()` check (TOCTOU) and no custom
error message rewriting (`OSError.__str__` already includes errno and
path).

### Testing
Unit tests are added to `tests/unit/test_main.py`, which already
houses argparse-level tests for the top-level parser:

1. `-C` absent → cwd unchanged.
2. `-C <existing-dir>` → cwd equals that directory at subcommand
   dispatch.
3. `-C <missing-dir>` → `SystemExit` with exit code 2; stderr contains
   the errno message.
4. `-C <relative-path>` → resolved against the original cwd.
5. Deferred defaults → `args.srcdir` and `args.depsconfig` fall back
   to `Path.cwd()` post-chdir. Both the user-supplied and the fallback
   branches are covered.

No new integration tests. The chdir happens in `main()` before any
subcommand runs, and subprocess cwd inheritance is a stdlib guarantee;
existing integration tests implicitly exercise the same code path once
they use `-C`.

### Acceptance criteria
1. No coverage regression, measured per-file and overall, against the
   pre-change baseline (`pytest --cov --cov-config=pyproject.toml
   tests/unit` with `COVERAGE_PROCESS_START` set per project
   conventions). Both the new `except OSError` branch and both
   branches of each deferred-default fallback must be covered. If an
   existing test does not exercise the fallback branch of `srcdir` or
   `depsconfig`, a targeted test is added to keep that branch covered.
2. All existing tests pass without modification.
3. `ruff check .`, `pylint --rcfile=pyproject.toml .`,
   `black --check --diff .`, and `validate_pyproject -vv pyproject.toml`
   all pass.
4. The self-run dogfood flow
   (`python3 -m pyproject_installer -v build &&
     python3 -m pyproject_installer -v run -- pytest -vra tests/unit`)
   completes successfully.
5. `README.md` is updated with an entry for `-C` containing `name`,
   `description`, and `example`, per the project's CLI documentation
   rule.

## Example
```
# Build a project without cd'ing into its tree.
python -m pyproject_installer -C /path/to/project build

# Combined with a subcommand positional: dist/foo.whl is resolved
# relative to /path/to/project.
python -m pyproject_installer -C /path/to/project install dist/foo.whl

# Run the project's test suite from anywhere.
python -m pyproject_installer -C /path/to/project run -- pytest -vra
```

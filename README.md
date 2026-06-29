# pyproject-installer

[![CI](https://github.com/stanislavlevin/pyproject_installer/actions/workflows/pipelines.yml/badge.svg)](https://github.com/stanislavlevin/pyproject_installer/actions/workflows/pipelines.yml)
[![PyPI version](https://img.shields.io/pypi/v/pyproject-installer.svg)](https://pypi.org/project/pyproject-installer/)
[![Python versions](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://github.com/stanislavlevin/pyproject_installer/blob/main/.github/workflows/pipelines.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linted with Ruff](https://img.shields.io/badge/linted-Ruff-261230.svg)](https://github.com/astral-sh/ruff)

`pyproject-installer` builds and installs PEP 517/518 Python projects inside network-isolated environments, with the deliberate constraints needed by downstream system packagers. It is the build/install backbone used to package Python projects for RPM-based distributions.

## Contents

- [Description](#description)
  - [Scope](#scope)
  - [Standards compliance](#standards-compliance)
  - [What it deliberately doesn't do](#what-it-deliberately-doesnt-do)
- [Usage](#usage)
  - [Build](#build)
  - [Install](#install)
  - [Run](#run)
  - [Management of dependencies sources](#management-of-dependencies-sources)
    - [show](#show)
    - [add](#add)
    - [sync](#sync)
    - [eval](#eval)
    - [delete](#delete)
  - [Bash completion](#bash-completion)
- [Comparison with other tools](#comparison-with-other-tools)
- [Bootstrap](#bootstrap)
- [Tests](#tests)
- [Changelog](#changelog)
- [License](#license)

## Description

### Scope

- Supported platform: Unix.
  Currently, platform-specific parts:
  - pipe is used for calling build backend hooks in subprocess
  - script wrappers are generated only for Unix systems

- Source tree can be either checkout of VCS or unpacked source distribution.

- An installation result will be consumed by external tool like RPM.
  The main usage of `pyproject-installer` looks like:
  ```
  external tool => (pyproject-installer: build => install to destdir) => external tool packages destdir
  ```

  Therefore, there is no need to build intermediate source distribution for
  build wheel, only `build_wheel` backend's hook is actually called.

  Note: an installation into Python virtual environment is also supported, but
  only the manual uninstallation of such packages is possible (tools should
  refuse an uninstallation of distribution with missing `RECORD` file).

### Standards compliance

- Only stdlib or vendored dependencies can be used in runtime for bootstrapping
  any Python project.
  Current vendored packages:
  - `tomli` (used for parsing `pyproject.toml` configuration file).
     Note: `tomli` is the part of stdlib since Python 3.11.
  - `packaging` (used for parsing PEP508 dependencies)

- Installation of build dependencies is up to the caller.
  These dependencies of Python projects are managed externally with system
  package managers like `apt` or `dnf`. [External source](#management-of-dependencies-sources) of upstream's
  dependencies may be used for provision of formatted list of dependencies to external tools.

- INSTALLER file is not installed by default(optional).
  https://peps.python.org/pep-0627/#optional-installer-file:
  > The INSTALLER file is also made optional, and specified to be used for
    informational purposes only. It is still a single-line text file containing
    the name of the installer.

  https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-installer-file:
  > This value should be used for informational purposes only. For example, if a
    tool is asked to uninstall a project but finds no RECORD file, it may
    suggest that the tool named in INSTALLER may be able to do the
    uninstallation.

### What it deliberately doesn't do

- OS environment of this project is a `network-isolated` environment, which
  implies that a local loopback interface is the only available network
  interface. Thus, `pyproject-installer` doesn't perform any network activity
  (e.g. it doesn't install build dependencies specified via PEP518 configuration
  or PEP517's `get_requires_for_*` hooks). This also makes it difficult or
  impossible to create an isolated Python environment for calling build backend
  hooks specified in PEP517, therefore, current Python environment is the only
  available environment.

- There is no post-installation bytecompilation.
  PEP427 says that wheel installers should compile any installed .py to .pyc.
  External tools like RPM already provide Python bytecompilation means, which
  compile for multiple optimization levels at a time. No point to compile
  modules twice.

- RECORD file is not installed.
  https://peps.python.org/pep-0627/#optional-record-file:
  > Specifically, the RECORD file is unnecessary when projects are installed by
    a Linux system packaging system, which has its own ways to keep track of
    files, uninstall them or check their integrity. Having to keep a RECORD file
    in sync with the disk and the system package database would be unreasonably
    fragile, and no RECORD file is better than one that does not correspond to
    reality.

- Built distribution can be checked within Python virtual environment with the
  help of `run` command.

- Project's dependencies sources can be managed (i.e. stored, synced, verified
  or evaluated) with the help of `deps` command.

## Usage

### Global options

These options are accepted by the top-level command and must appear
**before** the subcommand token.

> **`-C DIR`**
>
> Change to `DIR` before running the subcommand. Matches the semantics
> of `make -C`, `git -C`, and `tar -C`: after the flag takes effect,
> defaults such as `{cwd}/dist` and `{cwd}/pyproject_deps.json`
> resolve against the new directory.
>
> *Default:* current working directory (no change). Empty `DIR`
> (e.g. `-C ""`) is treated the same as omitting the flag.
>
> *Example:* `python -m pyproject_installer -C /path/to/project build`

> **`-v, --verbose`**
>
> Raise diagnostic output from the default `INFO` level to `DEBUG`.
>
> *Default:* `INFO`
>
> *Example:* `python -m pyproject_installer -v build`

Diagnostics (progress and logging) are written to `stderr`, while
`stdout` carries only a command's machine-readable data: the
dependency list from `deps eval`, the JSON from `deps show`, and the
diff from `deps sync --verify`. The separation holds at any verbosity,
so the data on `stdout` can be captured or piped without interleaved
log lines.

### Build

Build project from source tree in current Python environment according to
PEP 517. This doesn't trigger installation of project's build dependencies.

```console
python -m pyproject_installer build
```

**Positional arguments:**

> **`srcdir`** (positional)
>
> Source directory.
>
> *Default:* current working directory
>
> *Example:* `python -m pyproject_installer build .`

**Options:**

> **`--outdir OUTDIR, -o OUTDIR`**
>
> Output directory for built wheel.
>
> *Default:* `{srcdir}/dist`
>
> *Example:* `python -m pyproject_installer build --outdir ~/outdir`

Upon successful build `pyproject_installer` dumps wheel filename into
`{OUTDIR}/.wheeltracker`.

> **`--sdist`**
>
> Build source distribution (sdist) instead of binary one (wheel).
>
> *Note:* installer supports only wheel format.
>
> *Default:* build wheel
>
> *Example:* `python -m pyproject_installer build --sdist`

> **`--backend-config-settings BACKEND_CONFIG_SETTINGS`**
>
> Ad-hoc configuration for build backend as dumped JSON dictionary.
>
> *Default:* `None`

Examples of passing `config_settings`:

```console
# setuptools >= 64.0.0
python -m pyproject_installer build --backend-config-settings='{"--build-option": ["--python-tag=sometag", "--build-number=123"]}'

# setuptools < 64.0.0
python -m pyproject_installer build --backend-config-settings='{"--global-option": ["--python-tag=sometag", "--build-number=123"]}'

# pdm backend
python -m pyproject_installer build --backend-config-settings='{"--python-tag": "sometag"}'
```

### Install

Install project built in wheel format. This doesn't trigger installation of
project's runtime dependencies.

```console
python -m pyproject_installer install
```

**Positional arguments:**

> **`wheel`** (positional)
>
> Wheel file to install.
>
> *Default:* constructed as directory `{cwd}/dist` and wheel filename read from `{cwd}/dist/.wheeltracker`
>
> *Example:* `python -m pyproject_installer install wheel.whl`

**Options:**

> **`--destdir DESTDIR, -d DESTDIR`**
>
> Wheel installation root will be prepended with destdir.
>
> *Default:* `/`
>
> *Example:* `python -m pyproject_installer install --destdir ~/destdir`

> **`--installer INSTALLER`**
>
> Name of installer to be recorded in `dist-info/INSTALLER`.
>
> *Default:* `None`, `INSTALLER` will be omitted
>
> *Example:* `python -m pyproject_installer install --installer custom_installer`

> **`--no-strip-dist-info`**
>
> Don't strip dist-info. By default only `METADATA` and `entry_points.txt` files are allowed in `dist-info` directory.
>
> *Note:* `RECORD` is unconditionally filtered out.
>
> *Default:* `False`
>
> *Example:* `python -m pyproject_installer install --no-strip-dist-info`

> **`--rpm-filelist PATH`**
>
> Write an RPM `%files`-compatible filelist of every installed file, plus the computed `.pyc` paths for every installed `.py` under `purelib`/`platlib` (PEP 3147 / PEP 488). The file is consumable by `%files -f <PATH>` without post-processing, letting a spec declare package contents as `%files -f dist/foo.files` rather than enumerating them by hand. Paths in the output are system-absolute (`--destdir` is stripped). Parent directory of `PATH` must exist.
>
> *What is emitted:*
>
> - *File lines* - every file the installer writes to `--destdir`: `.py` sources, compiled extensions, entry-point scripts, dist-info files (`METADATA`, and with `--no-strip-dist-info` every file that survives filtering), the `INSTALLER` file (when `--installer` is used), and the relocated contents of `{dist}-{ver}.data/<scheme>/`.
> - *`.pyc` expansion* - for every `.py` file whose deepest owning scheme is `purelib` or `platlib`, three bytecode paths are computed (`importlib.util.cache_from_source` at optimisation levels 0, 1, 2) and emitted. `.py` files outside `purelib`/`platlib` (scripts, data, headers, dist-info) are **not** expanded: RPM's bytecompile step does not compile them, so predicting `.pyc` there would yield phantom paths that fail `%files` parsing.
> - *Man page globbing* - files under `scheme["data"]/share/man/` get a trailing `*` so the filelist still matches after RPM's `brp-compress` compresses them post-`%install` (uncompressed pages gain a compression extension). Suffixes brp decompresses (`.gz`, `.bz2`, `.Z`) are stripped first - brp will recompress them, so the on-disk extension may differ from the wheel's. Others (`.xz`, `.zst`, ...) are kept literal - brp leaves them alone.
> - *`%dir` entries* - directories the package claims ownership of:
>   - `{dist}-{ver}.dist-info` is **always** owned (installer creates it even when stripped down to `METADATA`); its subdirectories (e.g. PEP 639 `licenses/` under `--no-strip-dist-info`) are owned too.
>   - `scheme["headers"]` (typically `/usr/include/pythonX.Y/<dist>`, per-distribution namespaced) is owned only when at least one installed file lives under it; its intermediate subdirectories are owned too.
>   - Every intermediate directory between an installed file and its owning scheme root - i.e. package and sub-package dirs under `purelib`/`platlib` - is owned. For `.py` files in sub-packages, the sibling `__pycache__` directory is owned.
>
> *What is deliberately **not** emitted:*
>
> - The site roots themselves (`scheme["purelib"]`, `scheme["platlib"]` - e.g. `/usr/lib/pythonX.Y/site-packages`, `/usr/lib64/pythonX.Y/site-packages`) - owned by the Python runtime package.
> - The shared site-level `__pycache__` (`/usr/lib{,64}/pythonX.Y/site-packages/__pycache__`) - every top-level single-file module would fight for ownership; no `%dir` is emitted even though `.pyc` file lines for top-level modules land inside it.
> - `%dir` for FHS-standard roots (`/usr/bin`, `/usr/share`, etc.) or any intermediate directory under them. Files installed to `scheme["scripts"]` or `scheme["data"]` are emitted *file-only*; if your package ships app-specific data directories that no other package owns, add `%dir` lines for them manually in the spec.
>
> *Note:* `sys.pycache_prefix` must be at its default (`None`). `importlib.util.cache_from_source` respects it, so any non-default value (`PYTHONPYCACHEPREFIX`, `-X pycache_prefix=...`) would redirect every computed `.pyc` path under that prefix and desync the filelist from the buildroot; the installer refuses to run with `--rpm-filelist` in that case.
>
> *Default:* `None`, filelist is not written
>
> *Example:* `python -m pyproject_installer install --destdir /tmp/buildroot --rpm-filelist dist/foo.files`
>
> *Example output* - `dist/foo.files` after installing a pure-Python `foo-1.0-py3-none-any.whl` containing the `foo` package, a `foo_cli` console script, and a `.data/data/share/foo/asset.dat` asset on Python 3.13 with purelib = `/usr/lib/python3/site-packages`:
>
> ```
> %dir /usr/lib/python3/site-packages/foo
> %dir /usr/lib/python3/site-packages/foo-1.0.dist-info
> %dir /usr/lib/python3/site-packages/foo/__pycache__
> /usr/bin/foo_cli
> /usr/lib/python3/site-packages/foo-1.0.dist-info/METADATA
> /usr/lib/python3/site-packages/foo-1.0.dist-info/entry_points.txt
> /usr/lib/python3/site-packages/foo/__init__.py
> /usr/lib/python3/site-packages/foo/__pycache__/__init__.cpython-313.opt-1.pyc
> /usr/lib/python3/site-packages/foo/__pycache__/__init__.cpython-313.opt-2.pyc
> /usr/lib/python3/site-packages/foo/__pycache__/__init__.cpython-313.pyc
> /usr/share/foo/asset.dat
> ```
>
> Emitted paths follow `sysconfig.get_paths()` of the running interpreter. For a platform-specific wheel (e.g. `foo-1.0-cp313-cp313-linux_x86_64.whl`) on a split `lib`/`lib64` layout where platlib = `/usr/lib64/python3/site-packages`, the same contents plus a compiled extension land under the platlib root:
>
> ```
> %dir /usr/lib64/python3/site-packages/foo
> %dir /usr/lib64/python3/site-packages/foo-1.0.dist-info
> %dir /usr/lib64/python3/site-packages/foo/__pycache__
> /usr/bin/foo_cli
> /usr/lib64/python3/site-packages/foo-1.0.dist-info/METADATA
> /usr/lib64/python3/site-packages/foo-1.0.dist-info/entry_points.txt
> /usr/lib64/python3/site-packages/foo/__init__.py
> /usr/lib64/python3/site-packages/foo/__pycache__/__init__.cpython-313.opt-1.pyc
> /usr/lib64/python3/site-packages/foo/__pycache__/__init__.cpython-313.opt-2.pyc
> /usr/lib64/python3/site-packages/foo/__pycache__/__init__.cpython-313.pyc
> /usr/lib64/python3/site-packages/foo/_ext.cpython-313-x86_64-linux-gnu.so
> /usr/share/foo/asset.dat
> ```

> **`--exclude-paths PATTERN [PATTERN ...]`**
>
> One or more `fnmatch` glob patterns. Files whose wheel-relative POSIX path matches any pattern are excluded from installation. Pattern syntax follows Python's [`fnmatch`](https://docs.python.org/3/library/fnmatch.html) module: `*` matches any run of characters including `/`; `?` matches one character; `[seq]` / `[!seq]` are character classes. Identical patterns are collapsed (first occurrence kept).
>
> *Path format:* patterns are matched against the wheel's ZIP `namelist()` entries verbatim. Those entries are always forward-slash separated POSIX paths with no leading `/` and no `./` prefix, regardless of host operating system. Examples of what a pattern matches against: `pkg/__init__.py`, `pkg/sub/foo.py`, `pkg-1.0.dist-info/METADATA`, `pkg-1.0.data/scripts/cli`.
>
> Intended for RPM packaging: strip test files (`tests/`, `test_*.py`, `*_test.py`) and other artifacts the upstream project shipped inside the wheel but that aren't useful in installed form.
>
> Because `*` is slash-blind in `fnmatch`, every pattern should include literal `/` anchors to avoid leaking across directory boundaries. Typical default list (root-anchored + nested forms, suitable for an RPM macro):
>
> ```
> tests/*       */tests/*
> test_*.py     */test_*.py
> *_test.py     */*_test.py
> ```
>
> No hard-coded exceptions: a pattern matching `*.dist-info/METADATA` does strip it. System-level filtering of `dist-info` content remains controlled by `--no-strip-dist-info`.
>
> *Scope -- wheel members only.* Patterns are matched against the wheel's ZIP namelist before extraction. Content synthesised by the installer downstream is **not** subject to these patterns: console-script wrappers generated from `entry_points.txt`, the `INSTALLER` file written by `--installer`, and `.pyc` files produced post-install by external bytecompile steps (e.g. RPM's `brp-python-bytecompile`). To suppress generated console scripts, exclude `*.dist-info/entry_points.txt` -- the script-generation step is skipped when the file is absent from the install tree.
>
> *Default:* `[]`, no paths excluded.
>
> *Example:* `python -m pyproject_installer install --destdir /tmp/buildroot --exclude-paths 'tests/*' '*/tests/*' 'test_*.py' '*/test_*.py' '*_test.py' '*/*_test.py'`
>
> *Note:* `--exclude-paths` uses `nargs="+"` and greedily consumes positional-looking arguments. Place the wheel positional before `--exclude-paths`, terminate the option with `--`, or follow it with another flag -- otherwise the wheel argument is consumed as another pattern.

> **`--platlib`**
>
> Force the install to land in the `platlib` site-packages directory regardless of the wheel's `Root-Is-Purelib` flag. Both the unprefixed wheel root and any `.data/purelib/` content are redirected to `platlib`. Mutually exclusive with `--purelib`.
>
> *Default:* unset, the wheel's `Root-Is-Purelib` flag is honoured
>
> *Example:* `python -m pyproject_installer install --destdir /tmp/buildroot --platlib`

> **`--purelib`**
>
> Force the install to land in the `purelib` site-packages directory regardless of the wheel's `Root-Is-Purelib` flag. Both the unprefixed wheel root and any `.data/platlib/` content are redirected to `purelib`. Mutually exclusive with `--platlib`. The symmetric inverse of `--platlib`.
>
> *Default:* unset, the wheel's `Root-Is-Purelib` flag is honoured
>
> *Example:* `python -m pyproject_installer install --destdir /tmp/buildroot --purelib`

### Run

Run command within Python virtual environment that has access to system and user
site packages, their console scripts and installed built package.

```console
python -m pyproject_installer run
```

**Positional arguments:**

> **`command`** (positional, variadic)
>
> Command to run within virtual environment.
>
> *Example:* `python -m pyproject_installer run pytest`

**Dash note:**

> https://docs.python.org/3/library/argparse.html#arguments-containing
> If you have positional arguments that must begin with `-` and don't look like
> negative numbers, you can insert the pseudo-argument `--` which tells
> `parse_args()` that everything after that is a positional argument:

```console
python -m pyproject_installer run -- pytest -vra
```

**Options:**

> **`--wheel WHEEL`**
>
> Wheel file to install into virtual environment.
>
> *Default:* constructed as directory `{cwd}/dist` and wheel filename read from `{cwd}/dist/.wheeltracker`
>
> *Example:* `python -m pyproject_installer run --wheel wheel.whl pytest`

Note: venv's directory name is `.run_venv`.


### Management of dependencies sources

Collect PEP 508 requirements from different sources, store and evaluate
them in Python environment.

```console
python -m pyproject_installer deps --help
```

**Common deps options:**

> **`--depsconfig`**
>
> Configuration file to use.
>
> *Default:* `{cwd}/pyproject_deps.json`
>
> *Example:* `python -m pyproject_installer deps --depsconfig foo.json`

#### show

Show configuration and data of dependencies' sources.

> **`<source names>`** (positional)
>
> Source names to show. Repeated names are collapsed (first occurrence kept).
>
> *Default:* all
>
> *Example:* `python -m pyproject_installer deps show build`

See `python -m pyproject_installer deps show --help` for full options.

#### add

Configure source of Python dependencies. Supported sources: standardized formats like PEP 517, PEP 518, PEP 735 or core metadata are fully supported, while tool-specific formats like pip, tox, poetry, hatch, pdm or pipenv have limited support.

The `metadata` and `metadata_extra` sources build the project's core metadata and cache it in `dist/metadata_cache` under the working directory, so repeated metadata builds for the same source tree (for example several `add ... --sync` calls, or `--candidates` probing followed by a sync) happen only once. Delete that file (or clean `dist/`) to force a rebuild.

There are three ways to add sources, exactly one per call:

- `add <name> <type> [args]` -- one source of an explicit type;
- `add <name> --candidates LIST` -- one source discovered from an ordered list (the first that collects wins);
- `add --sources LIST` -- a batch of explicitly named sources, each `<name> <type> [args ...]`.

> **`<source name>`** (positional, optional)
>
> Source name. Omit when using `--sources`.

> **`<source type>`** (positional, optional)
>
> Omit when using `--candidates` or `--sources`.
>
> *Choices:* `pep517`, `pep518`, `pep735`, `metadata`, `metadata_extra`, `pip_reqfile`, `poetry`, `tox`, `hatch`, `pdm`, `pipenv`

> **`<source-specific options>`** (positional, variadic)
>
> Omit when using `--candidates` or `--sources`.
>
> Specific configuration options for source.
>
> *Default:* `[]`

> **`--candidates LIST`**
>
> Discover the source from an ordered list instead of a fixed type. `LIST` is a `;`-separated string whose entries are each `<type> [args ...]` (the same shape as the positional type/args). The walk goes left to right and the first candidate that *collects successfully* (its source is present and collectable) wins, even if it has zero dependencies; its type and args are recorded under the source name. A candidate is skipped when its source cannot be collected (for example a missing file or group); a malformed candidate list (an unknown type or the wrong number of arguments) is an error, not a silent skip. Identical entries (same type and args) are collapsed (first occurrence kept). It is mutually exclusive with the positional type/args (giving both is a usage error), so the source name is the only positional; every other aspect of `add` (add-only by default, `--reconfigure`, `--sync` and its verify options) behaves exactly as with an explicit type. Because `--verify-exclude` takes one or more values, keep the source name *before* it.
>
> When no candidate is picked, `add` reports it and exits with code 5 in every case, whether or not `name` is already configured and whether or not `--reconfigure` is given; any existing source under `name` is left untouched. `--sync` (and the `--verify` that depends on it) never runs on a no-candidate branch.
>
> *Default:* disabled
>
> *Example:* `python -m pyproject_installer deps add check --candidates 'pep735 test;pep735 tests;pip_reqfile test-requirements.txt' --reconfigure --sync --verify`

> **`--sources LIST`**
>
> Add a batch of explicitly named sources in one call (the additive counterpart of `--candidates`). `LIST` is a `;`-separated string whose entries are each `<name> <type> [args ...]` (a positional `name type [args]` per entry). The entries are handled one at a time, in order: each is configured exactly as a regular `add <name> <type> [args]` (`--reconfigure` applies per entry), and with `--sync` it is synced and verified before the next, so one call equals running `add <name> <type> [args] --reconfigure --sync --verify` once per entry in a single process. A malformed list is a usage error, not a silent skip: an empty list, an entry without a type, an unknown type, or a name repeated with a different type/args; a wrong argument count for a type is reported when that entry is configured (the same error as an explicit `add`). Identical entries (same name, type and args) are collapsed (first occurrence kept).
>
> With `--verify`, the run stops at the first source that is out of sync and exits with code 4; the entries after it are not reached, so a failed run leaves the earlier entries configured and synced and the later ones untouched. Run without `--verify` to configure and sync the whole list in one pass; `--verify` is a check and keeps stopping at the first out-of-sync source. `--sources` takes no positional name/type/args and is mutually exclusive with `--candidates`; because there are no positionals, `--sources` and the verify options may be given in any order.
>
> *Default:* disabled
>
> *Example:* `python -m pyproject_installer deps add --sources 'check_pep735 pep735 test;check_meta metadata_extra tests' --reconfigure --sync --verify`

> **`--reconfigure`**
>
> Reconfigure an already-configured source instead of failing on a duplicate name: keep it when the source type and args are unchanged (exit 0), or replace it (dropping its stored deps) when they differ. Without this flag, adding an already-configured name is an error.
>
> *Default:* disabled
>
> *Example:* `python -m pyproject_installer deps add --reconfigure runtime metadata`

> **`--sync`**
>
> After a successful add (newly added, kept, or replaced), sync the source in the same process. Accepts the same verify options as [`deps sync`](#sync) (`--verify`, `--verify-exclude`, `--verify-ignore-version`), each of which requires `--sync`. This lets a single `add` call replace the downstream `show || add` followed by `sync` sequence. Because `--verify-exclude` takes one or more values, give the source name and type *before* the verify options (or use the `--verify-exclude=PATTERN` form); otherwise they are folded into the exclude list.
>
> *Default:* disabled
>
> *Example:* `python -m pyproject_installer deps add build_pep517 pep517 --sync --verify --verify-exclude 'wheel$'`

Examples:

```console
# PEP 518 dependencies
python -m pyproject_installer deps add build_pep518 pep518

# PEP 517 dependencies
python -m pyproject_installer deps add build_pep517 pep517

# core metadata dependencies
python -m pyproject_installer deps add runtime metadata

# core metadata extra
# (its deps are the project's full core dependency list, not just the
# extra's delta; the extra is stored in the source and applied
# automatically at eval, so no eval --extra is needed)
python -m pyproject_installer deps add check metadata_extra tests

# PEP 735 dependency group
python -m pyproject_installer deps add check pep735 test

# pip requirements file
python -m pyproject_installer deps add check pip_reqfile requirements.txt

# tox testenv
python -m pyproject_installer deps add check tox tox.ini testenv

# poetry dev group
python -m pyproject_installer deps add check poetry dev

# hatch environment
python -m pyproject_installer deps add check hatch hatch.toml test

# pdm group
python -m pyproject_installer deps add check pdm test

# pipenv packages
python -m pyproject_installer deps add check pipenv Pipfile packages

# autodiscover a test-dependency source (first existing wins), then
# reconcile and verify it in one process
python -m pyproject_installer deps add check \
    --candidates 'pep735 test;pep735 tests;pip_reqfile test-requirements.txt;metadata_extra tests' \
    --reconfigure --sync --verify

# add a declared set of named sources in one process, reconciling and
# verifying each in turn (stops at the first that is out of sync)
python -m pyproject_installer deps add \
    --sources 'check_pep735 pep735 test;check_meta metadata_extra tests' \
    --reconfigure --sync --verify
```

See `python -m pyproject_installer deps add --help` for full options.

#### sync

Sync stored requirements to configured sources.

> **`<source names>`** (positional)
>
> Source names to sync. Repeated names are collapsed (first occurrence kept).
>
> *Default:* all
>
> *Example:* `python -m pyproject_installer deps sync build`

> **`--verify`**
>
> Sync sources, but print diff and exit with code 4 if the sources were unsynced.
>
> *Default:* only sync
>
> *Example:* `python -m pyproject_installer deps sync --verify build`

> **`--verify-exclude`**
>
> Regex patterns; exclude from diff requirements whose PEP 503-normalized names match one of the patterns. Requires `--verify`. Repeated patterns are collapsed (first occurrence kept).
>
> *Default:* `[]`
>
> *Example:* `python -m pyproject_installer deps sync --verify build --verify-exclude 'foo.*'`

> **`--verify-ignore-version`**
>
> Exclude from diff requirements that differ only in their version specifier, i.e. a requirement with the same PEP 503-normalized name, extras, marker and url is present on both sides of the diff. A requirement that was genuinely added or removed (or whose extras/marker/url changed) still appears in the diff and fails verification. Useful in downstream packaging to avoid failing on upstream upper-bound bumps such as `setuptools<81` -> `setuptools<82`. Requires `--verify`.
>
> *Default:* disabled
>
> *Example:* `python -m pyproject_installer deps sync --verify build --verify-ignore-version`

See `python -m pyproject_installer deps sync --help` for full options.

#### eval

Evaluate stored requirements according to PEP 508 in current Python environment and print them to stdout in PEP 508 format (by default) or specified one.

> **`<source names>`** (positional)
>
> Source names to evaluate. Repeated names are collapsed (first occurrence kept).
>
> *Default:* all
>
> *Example:* `python -m pyproject_installer deps eval build`

> **`--depformat`**
>
> Format of dependency to print. Supported substitutions: `$name` - project's name; `$nname` - PEP 503 normalized project's name; `$fextra` - project's extras (expanded first with `--depformatextra`).
>
> *Default:* PEP 508 format
>
> *Example:* `python -m pyproject_installer deps eval build --depformat='python3-$nn'`

> **`--depformatextra`**
>
> Format of extras to print (one extra of dependencies per line). Result is expanded in the format specified by `--depformat` as `$fextra`. Supported substitutions: `$extra`.
>
> *Default:* `''`
>
> *Example:* `python -m pyproject_installer deps eval build --depformat='python3-$nn$fextra' --depformatextra='+$extra'`

> **`--extra`**
>
> PEP 508 `extra` marker to evaluate with. Before evaluation the supplied name and each dependency's `extra == ...` marker value are both PEP 503/685-normalized, then compared in that normalized form, so `Foo.Bar`, `foo_bar` and `foo-bar` are equivalent.
>
> *Default:* `None`
>
> *Example:* `python -m pyproject_installer deps eval build --extra tests`
>
> A `metadata_extra` source carries its own recorded extra: that extra is always applied to its stored dependencies, and `--extra` is ignored for that source (it still applies to other sources).

> **`--exclude`**
>
> Regex patterns; exclude requirements whose PEP 503-normalized names match one of these patterns. Repeated patterns are collapsed (first occurrence kept).
>
> *Default:* `[]`
>
> *Example:* `python -m pyproject_installer deps eval build --exclude types- pytest-cov`

See `python -m pyproject_installer deps eval --help` for full options.

#### delete

Deconfigure source of Python dependencies.

> **`<source name>`** (positional)
>
> Source name to delete.
>
> *Example:* `python -m pyproject_installer deps delete build`

See `python -m pyproject_installer deps delete --help` for full options.


### Bash completion

`pyproject-installer completion bash` writes a bash completion script to
stdout. The script is generated from the live argparse tree and binds
to the `pyproject-installer` console script.

#### End-user one-shot install (no per-shell cost)

```bash
mkdir -p ~/.local/share/bash-completion/completions
pyproject-installer completion bash \
    > ~/.local/share/bash-completion/completions/pyproject-installer
```

The file is picked up lazily by `bash-completion` when the user first
types `pyproject-installer<TAB>` in a new shell.

#### End-user eval-on-startup (opt-in interpreter spawn per shell)

```bash
# in ~/.bashrc
eval "$(pyproject-installer completion bash)"
```


## Comparison with other tools

`pyproject-installer` consists of builder and installer, both of which provide
*only necessary* and *sufficient* functionality.

### builder

Functionally, today's builder is similar to [build](https://pypi.org/project/build).
The key differences are:
- highly specialized defaults (see [description](#description))
- highly specialized features to drop extra runtime dependencies like
  `pep517`. No point to vendor `pep517` to call only `build_wheel` backend hook
  in subprocess.

### installer

Functionally, today's installer is similar to [installer](https://pypi.org/project/installer).
The key differences are:
- highly specialized defaults and features (see [description](#description))

Both can be replaced with [pip](https://pypi.org/project/pip). But again, no
point to use full-featured complex `pip` to highly specialized task.


## Bootstrap
There is a self-hosted build backend to avoid dependency on any other backend.

For example, bootstrap can be done as:
```console
export PYTHONPATH=$(pwd)/src
python -m pyproject_installer build
python -m pyproject_installer install --destdir=/rootdir
```

## Tests
Tests are run from an installed venv, matching CI:
- create a venv and install the project with its test dependencies
  (requires `pip 25.1+`):
  ```console
  python -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install --group test
  .venv/bin/python -m pip install .
  ```
- unit tests can be run as:
  ```console
  .venv/bin/pytest tests/unit
  ```
- integration tests (require internet connection and `git` tool) can be run as:
  ```console
  .venv/bin/pytest tests/integration
  ```

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Distributed under the terms of the **MIT** license, `pyproject-installer` is
free and open source software.

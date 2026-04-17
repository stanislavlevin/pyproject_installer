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
> Source names to show.
>
> *Default:* all
>
> *Example:* `python -m pyproject_installer deps show build`

See `python -m pyproject_installer deps show --help` for full options.

#### add

Configure source of Python dependencies. Supported sources: standardized formats like PEP 517, PEP 518, PEP 735 or core metadata are fully supported, while tool-specific formats like pip, tox, poetry, hatch, pdm or pipenv have limited support.

> **`<source name>`** (positional)
>
> Source name.

> **`<source type>`** (positional)
>
> *Choices:* `pep517`, `pep518`, `pep735`, `metadata`, `pip_reqfile`, `poetry`, `tox`, `hatch`, `pdm`, `pipenv`

> **`<source-specific options>`** (positional, variadic)
>
> Specific configuration options for source.
>
> *Default:* `[]`

Examples:

```console
# PEP 518 dependencies
python -m pyproject_installer deps add build_pep518 pep518

# PEP 517 dependencies
python -m pyproject_installer deps add build_pep517 pep517

# core metadata dependencies
python -m pyproject_installer deps add runtime metadata

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
```

See `python -m pyproject_installer deps add --help` for full options.

#### sync

Sync stored requirements to configured sources.

> **`<source names>`** (positional)
>
> Source names to sync.
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
> Regex patterns; exclude from diff requirements whose PEP 503-normalized names match one of the patterns. Requires `--verify`.
>
> *Default:* `[]`
>
> *Example:* `python -m pyproject_installer deps sync --verify build --verify-exclude 'foo.*'`

See `python -m pyproject_installer deps sync --help` for full options.

#### eval

Evaluate stored requirements according to PEP 508 in current Python environment and print them to stdout in PEP 508 format (by default) or specified one.

> **`<source names>`** (positional)
>
> Source names to evaluate.
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
> PEP 508 `extra` marker to evaluate with.
>
> *Default:* `None`
>
> *Example:* `python -m pyproject_installer deps eval build --extra tests`

> **`--exclude`**
>
> Regex patterns; exclude requirement having PEP 503-normalized name that matches one of these patterns.
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

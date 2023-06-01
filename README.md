# pyproject-installer

This tool is intended for build, install, run or management of dependencies
sources of Python project in source tree within network-isolated environments.


## Description

- Supported platform: Unix.<br>
  Currently, platform-specific parts:
  - pipe is used for calling build backend hooks in subprocess
  - script wrappers are generated only for Unix systems

- OS environment of this project is a `network-isolated` environment, which
  implies that a local loopback interface is the only available network
  interface. Thus, `pyproject-installer` doesn't perform any network activity
  (e.g. it doesn't install build dependencies specified via PEP518 configuration
  or PEP517's `get_requires_for_*` hooks). This also makes it difficult or
  impossible to create an isolated Python environment for calling build backend
  hooks specified in PEP517, therefore, current Python environment is the only
  available environment.

- Source tree can be either checkout of VCS or unpacked source distribution.

- An installation result will be consumed by external tool like RPM.<br>
  The main usage of `pyproject-installer` looks like:
  ```
  external tool => (pyproject-installer: build => install to destdir) => external tool packages destdir
  ```

  Therefore, there is no need to build intermediate source distribution for
  build wheel, only `build_wheel` backend's hook is actually called.

  Note: an installation into Python virtual environment is also supported, but
  only the manual uninstallation of such packages is possible (tools should
  refuse an uninstallation of distribution with missing `RECORD` file).

- Only stdlib or vendored dependencies can be used in runtime for bootstrapping
  any Python project.<br>
  Current vendored packages:
  - `tomli` (used for parsing `pyproject.toml` configuration file).
     Note: `tomli` is the part of stdlib since Python 3.11.
  - `packaging` (used for parsing PEP508 dependencies)

- Installation of build dependencies is up to the caller.<br>
  These dependencies of Python projects are managed externally with system
  package managers like `apt` or `dnf`. [External source](#management-of-dependencies-sources) of upstream's
  dependencies may be used for provision of formatted list of dependencies to external tools.

- There is no post-installation bytecompilation.<br>
  PEP427 says that wheel installers should compile any installed .py to .pyc.
  External tools like RPM already provide Python bytecompilation means, which
  compile for multiple optimization levels at a time. No point to compile
  modules twice.

- RECORD file is not installed.<br>
  https://peps.python.org/pep-0627/#optional-record-file:
  > Specifically, the RECORD file is unnecessary when projects are installed by
    a Linux system packaging system, which has its own ways to keep track of
    files, uninstall them or check their integrity. Having to keep a RECORD file
    in sync with the disk and the system package database would be unreasonably
    fragile, and no RECORD file is better than one that does not correspond to
    reality.

- INSTALLER file is not installed by default(optional).<br>
  https://peps.python.org/pep-0627/#optional-installer-file:
  > The INSTALLER file is also made optional, and specified to be used for
    informational purposes only. It is still a single-line text file containing
    the name of the installer.

  https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-installer-file:
  > This value should be used for informational purposes only. For example, if a
    tool is asked to uninstall a project but finds no RECORD file, it may
    suggest that the tool named in INSTALLER may be able to do the
    uninstallation.

- Built distribution can be checked within Python virtual environment with the
  help of `run` command.

- Project's dependencies sources can be managed (i.e. stored, synced, verified
  or evaluated) with the help of `deps` command.

## Usage

### Build
Build project from source tree in current Python environment according to
PEP517. This doesn't trigger installation of project's build dependencies.
```
python -m pyproject_installer build
```

Build positional arguments:
<pre>
<em><strong>description</strong></em>: source directory
<em><strong>default</strong></em>: current working directory
<em><strong>example</strong></em>: python -m pyproject_installer build .
</pre>

Build options:
<pre>
<em><strong>name</strong></em>: --outdir OUTDIR, -o OUTDIR
<em><strong>description</strong></em>: output directory for built wheel
<em><strong>default</strong></em>: {srcdir}/dist
<em><strong>example</strong></em>: python -m pyproject_installer build --outdir ~/outdir
</pre>
Upon successful build `pyproject_installer` dumps wheel filename into
`{OUTDIR}/.wheeltracker`.

<pre>
<em><strong>name</strong></em>: --sdist
<em><strong>description</strong></em>: build source distribution(sdist) instead of binary
one(wheel).
<em><strong>note</strong></em>: installer supports only wheel format.
<em><strong>default</strong></em>: build wheel
<em><strong>example</strong></em>: python -m pyproject_installer build --sdist
</pre>

<pre>
<em><strong>name</strong></em>: --backend-config-settings BACKEND_CONFIG_SETTINGS
<em><strong>description</strong></em>: ad-hoc configuration for build backend as dumped JSON dictionary
<em><strong>default</strong></em>: None

Example of passing <em><strong>config_settings</strong></em> for setuptools>=64.0.0:
python -m pyproject_installer build --backend-config-settings='{"--build-option": ["--python-tag=sometag", "--build-number=123"]}'

Example of passing <em><strong>config_settings</strong></em> for setuptools<64.0.0:
python -m pyproject_installer build --backend-config-settings='{"--global-option": ["--python-tag=sometag", "--build-number=123"]}'

Example of passing <em><strong>config_settings</strong></em> for pdm backend:
python -m pyproject_installer build --backend-config-settings='{"--python-tag": "sometag"}'
</pre>

### Install
Install project built in wheel format. This doesn't trigger installation of
project's runtime dependencies.
```
python -m pyproject_installer install
```

Install positional arguments:
<pre>
<em><strong>description</strong></em>: wheel file to install
<em><strong>default</strong></em>: contructed as directory {cwd}/dist and wheel filename read from
{cwd}/dist/.wheeltracker
<em><strong>example</strong></em>: python -m pyproject_installer install wheel.whl
</pre>

Install options:
<pre>
<em><strong>name</strong></em>: --destdir DESTDIR, -d DESTDIR
<em><strong>description</strong></em>: Wheel installation root will be prepended with destdir
<em><strong>default</strong></em>: /
<em><strong>example</strong></em>: python -m pyproject_installer install --destdir ~/destdir
</pre>

<pre>
<em><strong>name</strong></em>: --installer INSTALLER
<em><strong>description</strong></em>: Name of installer to be recorded in dist-info/INSTALLER
<em><strong>default</strong></em>: None, INSTALLER will be omitted
<em><strong>example</strong></em>: python -m pyproject_installer install --installer custom_installer
</pre>

<pre>
<em><strong>name</strong></em>: --no-strip-dist-info
<em><strong>description</strong></em>: Don't strip dist-info. By default only <em><strong>METADATA</strong></em>
and <em><strong>entry_points.txt</strong></em> files are allowed in <em>dist-info</em> directory.
<em><strong>note</strong></em>: <em><strong>RECORD</strong></em> is unconditionally filtered out.
<em><strong>default</strong></em>: False
<em><strong>example</strong></em>: python -m pyproject_installer install --no-strip-dist-info
</pre>

### Run
Run command within Python virtual environment that has access to system and user
site packages, their console scripts and installed built package.
```
python -m pyproject_installer run
```

Run positional arguments:
<pre>
<em><strong>description</strong></em>: command to run within virtual environment
<em><strong>example</strong></em>: python -m pyproject_installer run pytest
</pre>

Dash note:
> https://docs.python.org/3/library/argparse.html#arguments-containing
If you have positional arguments that must begin with - and don't look like
negative numbers, you can insert the pseudo-argument '--' which tells
`parse_args()` that everything after that is a positional argument:
```
python -m pyproject_installer run -- pytest -vra
```

Run options:
<pre>
<em><strong>name</strong></em>: --wheel WHEEL
<em><strong>description</strong></em>: wheel file to install into virtual environment
<em><strong>default</strong></em>: contructed as directory {cwd}/dist and wheel filename read from
{cwd}/dist/.wheeltracker
<em><strong>example</strong></em>: python -m pyproject_installer run --wheel wheel.whl pytest
</pre>

Note: venv's directory name is `.run_venv`.


### Management of dependencies sources

Collect PEP508 requirements from different sources, store and evaluate
them in Python environment.

```
python -m pyproject_installer deps --help
```

Common deps options:
<pre>
<em><strong>name</strong></em>: --depsconfig
<em><strong>description</strong></em>: configuration file to use
<em><strong>default</strong></em>: {cwd}/pyproject_deps.json
<em><strong>example</strong></em>: python -m pyproject_installer deps --depsconfig foo.json
</pre>

#### deps subcommands

<pre>
<em><strong>name</strong></em>: show
<em><strong>description</strong></em>: show configuration and data of dependencies's sources
<em><strong>example</strong></em>: python -m pyproject_installer deps show --help
</pre>

Positional arguments:
<pre>
<em><strong>description</strong></em>: source names
<em><strong>default</strong></em>: all
<em><strong>example</strong></em>: python -m pyproject_installer deps show build
</pre>

---

<pre>
<em><strong>name</strong></em>: add
<em><strong>description</strong></em>: configure source of Python dependencies. Supported sources: standardized formats like PEP517, PEP518 or core metadata are fully supported, while tool-specific formats like pip, tox, poetry, hatch or pdm have limited support.
<em><strong>example</strong></em>: python -m pyproject_installer deps add --help
</pre>

Positional arguments:
<pre>
<em><strong>description</strong></em>: source name
</pre>

<pre>
<em><strong>description</strong></em>: source type
<em><strong>choice</strong></em>: pep517, pep518, metadata, pip_reqfile, poetry, tox, hatch, pdm
</pre>

<pre>
<em><strong>description</strong></em>: specific configuration options for source
<em><strong>default</strong></em>: []
</pre>

<pre>
<em><strong>examples</strong></em>:
Configuration of source of <strong>PEP518</strong> dependencies:
python -m pyproject_installer deps add build_pep518 pep518

Configuration of source of <strong>PEP517</strong> dependencies:
python -m pyproject_installer deps add build_pep517 pep517

Configuration of source of <strong>metadata</strong> dependencies:
python -m pyproject_installer deps add runtime metadata

Configuration of source of <strong>pip</strong> requirements:
python -m pyproject_installer deps add check pip_reqfile requirements.txt

Configuration of source of <strong>tox</strong> requirements:
python -m pyproject_installer deps add check tox tox.ini testenv

Configuration of source of <strong>poetry</strong> requirements:
python -m pyproject_installer deps add check poetry dev

Configuration of source of <strong>hatch</strong> requirements:
python -m pyproject_installer deps add check hatch hatch.toml test

Configuration of source of <strong>pdm</strong> requirements:
python -m pyproject_installer deps add check pdm test
</pre>

---

<pre>
<em><strong>name</strong></em>: sync
<em><strong>description</strong></em>: sync stored requirements to configured sources
<em><strong>example</strong></em>: python -m pyproject_installer deps sync --help
</pre>

Positional arguments:
<pre>
<em><strong>description</strong></em>: source names
<em><strong>default</strong></em>: all
<em><strong>example</strong></em>: python -m pyproject_installer deps sync build
</pre>

Options:
<pre>
<em><strong>name</strong></em>: --verify
<em><strong>description</strong></em>: Sync sources, but print diff and exits with code 4 if the sources were unsynced
<em><strong>default</strong></em>: only sync
<em><strong>example</strong></em>: python -m pyproject_installer deps sync --verify build
</pre>

---

<pre>
<em><strong>name</strong></em>: eval
<em><strong>description</strong></em>: evaluate stored requirements according to PEP508 in current Python environment and print them to stdout in PEP508 format (by default) or specified one
<em><strong>example</strong></em>: python -m pyproject_installer deps eval --help
</pre>

Positional arguments:
<pre>
<em><strong>description</strong></em>: source names
<em><strong>default</strong></em>: all
<em><strong>example</strong></em>: python -m pyproject_installer deps eval build
</pre>

Options:
<pre>
<em><strong>name</strong></em>: --depformat
<em><strong>description</strong></em>: format of dependency to print. Supported substitutions: $name - project's name, $nname - PEP503 normalized project's name, $fextra - project's extras (expanded first with --depformatextra)
<em><strong>default</strong></em>: PEP508 format
<em><strong>example</strong></em>: python -m pyproject_installer deps eval build --depformat='python3-$nn'
</pre>

<pre>
<em><strong>name</strong></em>: --depformatextra
<em><strong>description</strong></em>: format of extras to print (one extra of dependencies per line). Result is expanded in format specified by --depformat as $fextra. Supported substitutions: $extra
<em><strong>default</strong></em>: ''
<em><strong>example</strong></em>: python -m pyproject_installer deps eval build --depformat='python3-$nn$fextra' --depformatextra='+$extra'
</pre>

<pre>
<em><strong>name</strong></em>: --extra
<em><strong>description</strong></em>: PEP508 'extra' marker to evaluate with
<em><strong>default</strong></em>: None
<em><strong>example</strong></em>: python -m pyproject_installer deps eval build --extra tests
</pre>

<pre>
<em><strong>name</strong></em>: --exclude
<em><strong>description</strong></em>: regexes patterns, exclude requirement having PEP503-normalized name that matches one of these patterns
<em><strong>default</strong></em>: []
<em><strong>example</strong></em>: python -m pyproject_installer deps eval build --exclude types- pytest-cov
</pre>

---

<pre>
<em><strong>name</strong></em>: delete
<em><strong>description</strong></em>: deconfigure source of Python dependencies
<em><strong>example</strong></em>: python -m pyproject_installer deps delete --help
</pre>

Positional arguments:
<pre>
<em><strong>description</strong></em>: source name
<em><strong>example</strong></em>: python -m pyproject_installer deps delete build
</pre>


## Comparison with other tools

`pyproject-installer` consists of builder and installer, both provide
*only necessary* and *sufficient* functionality.

### builder

Functionally, today's builder is similar to [build](https://pypi.org/project/build).<br>
The key differences are:
- highly specialized defaults (see [description](#Description))
- highly specialized features to drop extra runtime dependencies like
  `pep517`. No point to vendor `pep517` to call only `build_wheel` backend hook
  in subprocess.

### installer

Functionally, today's installer is similar to [installer](https://pypi.org/project/installer).<br>
The key differences are:
- highly specialized defaults and features (see [description](#Description))

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
- unit tests can be run as:
  ```
  pytest tests/unit
  ```
- integration tests (require internet connection and `git` tool) can be run as:
  ```
  pytest tests/integration
  ```

## License

Distributed under the terms of the **MIT** license, `pyproject-installer` is
free and open source software.

# pyproject-installer

This tool is intended to build wheel from Python source tree and install it.


## Description

- Supported platform: Unix.<br>
  Currently, the only platform-specific part is the pipe.

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
  Currently, only `tomli` (used for parsing `pyproject.toml` configuration file)
  is vendored by `pyproject_installer`.

  Note: `tomli` is the part of stdlib since Python 3.11.

- Installation of build dependencies is up to the caller.<br>
  Moreover, parsing of build requirements requires two additional external
  packages: `packaging` and its dependency `pyparsing`. But since the validation
  of build dependencies is optional (disabled by default) there is no point to
  vendor them.

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

- INSTALLER is populated with `pyproject_installer` as installer by default.<br>
  https://peps.python.org/pep-0627/#optional-installer-file:
  > The INSTALLER file is also made optional, and specified to be used for
    informational purposes only. It is still a single-line text file containing
    the name of the installer.


## Usage

### Build
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

Example of passing <em><strong>config_settings</strong></em> for setuptools backend:
python -m pyproject_installer build --backend-config-settings='{"--global-option": ["--python-tag=sometag", "--build-number=123"]}'

Example of passing <em><strong>config_settings</strong></em> for pdm backend:
python -m pyproject_installer build --backend-config-settings='{"--python-tag": "sometag"}'
</pre>

### Install
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
<em><strong>default</strong></em>: pyproject_installer
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

## Comparison with other tools

`pyproject-installer` consists of builder and installer, both provide
*only necessary* and *sufficient* functionality.

### builder

Functionally, today's builder is similar to [build](https://pypi.org/project/build).<br>
The key differences are:
- highly specialized defaults (see [description](#Description))
- highly specialized features to drop extra runtime dependencies like
  `pep517` or `packaging`. No point to vendor `pep517` to call only
  `build_wheel` backend hook in subprocess.

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


## License

Distributed under the terms of the **MIT** license, `pyproject-installer` is
free and open source software.

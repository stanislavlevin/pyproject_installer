## Abstract
This RFE proposes to add `run` command to execute an arbitrary command within
non-isolated `venv`-based Python virtual environment.

## Motivation
It's often required to run a project's tests during downstream packaging in the
global isolated environment. For example, the user of such environment is
unprivileged (can't install distributions into global sitepackages) and has no
access to Internet (can't install distributions from package indexes). On the
other hand built Python distributions should not be unintentionally installed
into user sitepackages to avoid their interference with any further
distributions being tested. Though some of tests can be run in current Python
environment without any change (e.g. `flat` layout and pure Python package),
some may require setting of `PYTHONPATH` environment variable (e.g. `src` layout
and pure Python package). But things may be more complex in case of
arch-dependent Python packages, `.pth` hooks or `entry_points` plugins where
`PYTHONPATH` way can't help. This is one of the reasons why
`venv`(stdlib)/`virtualenv`(third-party) exists. There is really nice tool `tox`
for automation of testing process. But it's overkill to use it for the
aforementioned task, for example:
- tox always wants to download and install dependencies of test env and
  dependencies of package (though this can be overcome with options and external
  plugins)
- tox has many runtime dependencies

## Specification
`run` command do the following:
- create minimal virtual environment with the help of stdlib's `venv`.
  The generated environment:
  - has no installed pip, setuptools
  - has access to system and user site packages
- generate console scripts of system and user site packages to access them
  within venv
- install built distribution into venv without any dependencies
- spawn a command in subprocess

### Example
```
python -m pyproject_installer run -- pytest -vra
```

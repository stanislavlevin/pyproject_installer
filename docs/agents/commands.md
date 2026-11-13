# Development commands

Run commands from the repository root. Use `.venv` for development commands.
Self-run tests have the environment requirements described below.

## Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --group lint --group coverage --group test
.venv/bin/python -m pip install 'validate-pyproject[all]'
.venv/bin/python -m pip install .
```

Install the current project before unit and integration tests. Reinstall
after code changes so tests use the updated installed package.

## Validation

Validate `pyproject.toml` and run lint before tests, following the CI order:

```sh
.venv/bin/python -m validate_pyproject -vv pyproject.toml
.venv/bin/python -m ruff check .
.venv/bin/python -m pylint --rcfile=pyproject.toml .
.venv/bin/python -m black --check --diff .
.venv/bin/python -m mypy
```

Black uses a line length of 80. Mypy uses strict checking and is a CI gate.

## Unit tests and coverage

```sh
.venv/bin/python -m pytest -vra --cov --cov-config=pyproject.toml tests/unit
```

## Integration tests

```sh
.venv/bin/python -m pytest -vra tests/integration
```

## Self-run tests

`run` creates its own virtual environment with access to system and user
site-packages. It does not use the existing `.venv`. Install
`pyproject-installer` and the required test dependencies into user
site-packages, as shown below.

Run these commands with the system Python, outside any virtual environment.
If `.venv` is activated, run `deactivate` first.

```sh
python3 -m pip install --user --group test
python3 -m pip install --user .
python3 -m pyproject_installer -v build
python3 -m pyproject_installer -v run -- pytest -vra tests/unit
```

## Vendored dependencies

Edit `src/pyproject_installer/vendored.txt`, then regenerate:

```sh
.venv/bin/python tools/vendored.py
```

Review the generated diff for unrelated changes.

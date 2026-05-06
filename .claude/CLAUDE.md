# pyproject-installer

Builds/installs PEP 517/518 projects in network-isolated envs (RPM packaging). Runtime = stdlib + vendored `tomli`/`packaging`, no network I/O. Self-hosting: `backend/` builds this project.

## Commands
- Run everything in `.venv` (`python -m venv .venv && .venv/bin/pip install --upgrade pip`) **except self-run** — nested venvs are unsupported there.
- Deps: `.venv/bin/pip install --group {lint,coverage,test}`; then `.venv/bin/pip install .` (required before unit/integration).
- Validate manifest (CI gate): `.venv/bin/python -m validate_pyproject -vv pyproject.toml`.
- Lint (run before tests): `ruff check .`; `pylint --rcfile=pyproject.toml .`; `black --check --diff .` (line-length 80); `mypy` (strict, gated in CI).
- Unit + coverage: `COVERAGE_PROCESS_START="$(pwd)/pyproject.toml" pytest -vra --cov --cov-config=pyproject.toml tests/unit` (env var required for subprocess coverage).
- Self-run tests (system interpreter, NOT inside `.venv`): `pip install --group test && pip install . && python3 -m pyproject_installer -v build && python3 -m pyproject_installer -v run -- pytest -vra tests/unit`.
- Integration: `pytest -vra tests/integration`.
- CI matrix: Python 3.10–3.14 (min version floor).
- Vendored bump: edit `backend/vendored.txt` + `src/pyproject_installer/vendored.txt`, run `python3 tools/vendored.py`.

## Constraints
- `lib/backend_helper/backend_caller.py` runs in subprocess — **stdlib-only**, no main-package imports.
- Non-isolated build; no build-dep checking (caller's job).
- Install drops `RECORD` (PEP 627), no bytecompilation — by design.
- pytest `filterwarnings = ["error"]` — warnings are errors.
- New features need tests + docs; new CLI opts → `README.md` with `name`/`description`/`example`.

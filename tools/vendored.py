"""
Vendor required packages

Updating vendored packages:
- bump required package in `backend/vendored.txt`
- bump required package in `src/pyproject_installer/vendored.txt`
- run `python3 tools/vendored.py`

Currently there are no changes made on vendored packages.

To verify changes if any:
- tomli: https://github.com/hukkin/tomli.git
git diff 2.3.0:src/tomli @:backend/_vendor/tomli
git diff 2.3.0:src/tomli @:src/pyproject_installer/_vendor/tomli
- packaging: https://github.com/pypa/packaging
git diff 25.0:src/packaging @:src/pyproject_installer/_vendor/packaging
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

VENDORED_PATH = "src/pyproject_installer/_vendor"
BACKEND_VENDORED_PATH = "backend/_vendor"


def install(vendored_path):
    env = os.environ.copy()
    # don't build binary extensions with mypyc
    env["TOMLI_USE_MYPYC"] = "0"
    install_args = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--no-compile",
        "--no-binary",
        ":all:",
        "-r",
        vendored_path.parent / "vendored.txt",
        "-t",
        vendored_path,
    ]
    subprocess.check_call(install_args, env=env)
    (vendored_path / "__init__.py").touch()


def update_main():
    vendored_path = Path(VENDORED_PATH)
    if vendored_path.exists():
        shutil.rmtree(vendored_path)
    vendored_path.mkdir()
    install(vendored_path)


def update_backend():
    vendored_path = Path(BACKEND_VENDORED_PATH)
    if vendored_path.exists():
        shutil.rmtree(vendored_path)
    vendored_path.mkdir()
    install(vendored_path)


if __name__ == "__main__":
    update_main()
    update_backend()

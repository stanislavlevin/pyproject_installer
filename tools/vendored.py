#!/usr/bin/python3

"""
Vendor required packages

Updating vendored packages:
- bump required package in `src/pyproject_installer/vendored.txt`
- run `python3 tools/vendored.py`

Currently there are no changes made on vendored packages.

To verify changes if any:
- packaging: https://github.com/pypa/packaging
git diff 26.3:src/packaging @:src/pyproject_installer/_vendor/packaging
"""

import shutil
import subprocess
import sys
from pathlib import Path

VENDORED_PATH = "src/pyproject_installer/_vendor"


def install(vendored_path):
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
    subprocess.check_call(install_args)
    (vendored_path / "__init__.py").touch()


def update_main():
    vendored_path = Path(VENDORED_PATH)
    if vendored_path.exists():
        shutil.rmtree(vendored_path)
    vendored_path.mkdir()
    install(vendored_path)


if __name__ == "__main__":
    update_main()

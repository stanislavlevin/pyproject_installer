"""
Vendor required packages

Updating vendored packages:
- bump required package in `src/pyproject_installer/vendored.txt`
- run `python3 tools/vendored.py`

Currently there are no changes made on vendored packages.

To verify changes if any:
- tomli: https://github.com/hukkin/tomli.git
git diff 2.0.1:src/tomli @:src/pyproject_installer/_vendor/tomli
- packaging: https://github.com/pypa/packaging
git diff 23.1:src/packaging @:src/pyproject_installer/_vendor/packaging
"""

from pathlib import Path
import sys
import subprocess
import shutil

VENDORED_PATH = "src/pyproject_installer/_vendor"
BACKEND_VENDORED_PATH = "backend/_vendor"


def install(vendored_path):
    install_args = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--no-compile",
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


def update_backend():
    vendored_path = Path(BACKEND_VENDORED_PATH)
    if vendored_path.exists():
        shutil.rmtree(vendored_path)
    vendored_path.mkdir()
    install(vendored_path)


if __name__ == "__main__":
    update_main()
    update_backend()

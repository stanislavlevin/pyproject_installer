"""
Check if pyproject_installer is buildable by other tools like `build` or `pip`
"""
from pathlib import Path
import subprocess


from pyproject_installer import __version__ as installer_version


def install_pkg(creator, pkg):
    install_args = [
        str(creator.exe),
        "-Im",
        "pip",
        "install",
        "--ignore-installed",
        pkg,
    ]
    subprocess.check_call(install_args, cwd=creator.dest)


def test_build_with_build(virt_env, wheeldir):
    install_pkg(virt_env, "build")
    cwd = Path.cwd()
    assert cwd.name == "pyproject_installer"

    build_args = [
        str(virt_env.exe),
        "-Im",
        "build",
        ".",
        "--outdir",
        str(wheeldir),
    ]
    subprocess.check_call(build_args, cwd=cwd)
    built_files = {f.name for f in wheeldir.iterdir()}
    expected_files = {
        f"pyproject_installer-{installer_version}-py3-none-any.whl",
        f"pyproject_installer-{installer_version}.tar.gz",
    }
    assert built_files == expected_files


def test_build_with_pip(virt_env, wheeldir):
    install_pkg(virt_env, "pip")
    cwd = Path.cwd()
    assert cwd.name == "pyproject_installer"

    build_args = [
        str(virt_env.exe),
        "-Im",
        "pip",
        "wheel",
        ".",
        "-w",
        str(wheeldir),
    ]
    subprocess.check_call(build_args, cwd=cwd)
    built_files = {f.name for f in wheeldir.iterdir()}
    expected_files = {
        f"pyproject_installer-{installer_version}-py3-none-any.whl",
    }
    assert built_files == expected_files

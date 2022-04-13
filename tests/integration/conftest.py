from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    import pyproject_installer.build_cmd._vendor.tomli as tomllib

import pytest
import virtualenv

from pyproject_installer.build_cmd._build import call_hook


@pytest.fixture(scope="session")
def pyproject_installer_whl():
    """Build pyproject_installer as wheel"""
    assert Path.cwd().name == "pyproject_installer"
    with tempfile.TemporaryDirectory() as d:
        wheels = Path(d) / "wheels"
        wheels.mkdir()
        build_args = [
            sys.executable,
            "-m",
            "pyproject_installer",
            "build",
            "--outdir",
            wheels,
        ]
        subprocess.check_call(build_args)
        yield wheels / (wheels / ".wheeltracker").read_text().rstrip()


@pytest.fixture
def virt_env(tmpdir):
    """Create virtualenv"""
    venv = tmpdir / "venv"
    cmd = [str(venv), "--no-setuptools", "--no-wheel", "--activators", ""]
    result = virtualenv.cli_run(cmd, setup_logging=False)
    return result.creator


@pytest.fixture
def virt_env_installer(virt_env, pyproject_installer_whl):
    """Install pyproject_installer with pip into virtual env"""
    virtualenv_python = str(virt_env.exe)

    install_args = [
        virtualenv_python,
        "-Im",
        "pip",
        "install",
        str(pyproject_installer_whl),
    ]
    subprocess.check_call(install_args, cwd=virt_env.dest)
    return virt_env


@pytest.fixture
def install_build_deps():
    """Calc and install build deps of srcdir with pip"""

    def _install_build_deps(python, srcdir):
        # get common build requirements(PEP518)
        with (srcdir / "pyproject.toml").open("rb") as f:
            pyproject_data = tomllib.load(f)

        build_requires = pyproject_data["build-system"]["requires"]

        if build_requires:
            with tempfile.NamedTemporaryFile() as f:
                f.write("\n".join(build_requires).encode("utf-8"))
                f.flush()
                install_args = [
                    python,
                    "-Im",
                    "pip",
                    "install",
                    "-r",
                    f.name,
                ]
                subprocess.check_call(install_args)

        # get wheel build requirements(PEP517)
        wheel_build_requires = call_hook(
            python=python,
            srcdir=srcdir,
            verbose=False,
            hook="get_requires_for_build_wheel",
        )["result"]

        if wheel_build_requires:
            with tempfile.NamedTemporaryFile() as f:
                f.write("\n".join(wheel_build_requires).encode("utf-8"))
                f.flush()
                install_args = [
                    python,
                    "-Im",
                    "pip",
                    "install",
                    "-r",
                    f.name,
                ]
                subprocess.check_call(install_args)

    return _install_build_deps


@pytest.fixture
def setuptools_project(pyproject):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["setuptools"]
            build-backend = "setuptools.build_meta"
            """
        )
    )
    (pyproject_path / "setup.cfg").write_text(
        textwrap.dedent(
            """\
            [metadata]
            name = my_package
            version = 1.0
            description = My package description
            license = Some license
            """
        )
    )

    return pyproject_path


@pytest.fixture
def pdm_project(pyproject):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires = ["pdm-pep517"]
            build-backend = "pdm.pep517.api"

            [project]
            name = "my_package"
            version = "1.0"
            description = "My package description"
            license = {text = "Some license"}

            dependencies = []
            """
        )
    )

    return pyproject_path

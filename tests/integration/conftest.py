from pathlib import Path
from venv import EnvBuilder
import subprocess
import sys
import tempfile
import textwrap

import pytest

from pyproject_installer import __version__ as installer_version
from pyproject_installer.build_cmd import WHEEL_TRACKER
from pyproject_installer.lib import tomllib
from pyproject_installer.lib.build_backend import backend_hook


class ContextVenv(EnvBuilder):
    def __init__(self, *args, **kwargs):
        self.context = None
        super().__init__(*args, **kwargs)

    def ensure_directories(self, *args, **kwargs):
        # save context for reusage
        self.context = super().ensure_directories(*args, **kwargs)
        # env_exec_cmd requires Python3.9+ (https://bugs.python.org/issue45337),
        # for non-windows systems: context.env_exec_cmd = context.env_exe
        if not hasattr(self.context, "env_exec_cmd"):
            self.context.env_exec_cmd = self.context.env_exe
        return self.context


@pytest.fixture(scope="session")
def pyproject_installer_whl():
    """Build pyproject_installer as wheel"""
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
        built_files = {f.name for f in wheels.iterdir()}
        # make sure that pyproject_installer was built
        expected_files = {
            WHEEL_TRACKER,
            f"pyproject_installer-{installer_version}-py3-none-any.whl",
        }
        assert built_files == expected_files
        yield wheels / (wheels / WHEEL_TRACKER).read_text().rstrip()


@pytest.fixture
def virt_env(tmpdir):
    """Create virtual environment and returns its context

    https://docs.python.org/3/library/venv.html#venv.EnvBuilder.ensure_directories
    """
    venv_path = tmpdir / "venv"
    venv = ContextVenv(with_pip=True)
    venv.create(venv_path)
    return venv.context


@pytest.fixture
def virt_env_installer(virt_env, pyproject_installer_whl):
    """Install pyproject_installer with pip into virtual env"""
    python = virt_env.env_exec_cmd

    install_args = [
        python,
        "-Im",
        "pip",
        "install",
        str(pyproject_installer_whl),
    ]
    subprocess.check_call(install_args, cwd=virt_env.env_dir)
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
        wheel_build_requires = backend_hook(
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

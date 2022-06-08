from pathlib import Path
import subprocess

import pytest
import re


@pytest.fixture
def git_tree(tmpdir, request, monkeypatch):
    """Clone project and chdir into it"""
    name, url, subdir = request.param
    subprocess.check_call(
        ["git", "clone", "--depth", "1", url, name],
        cwd=tmpdir,
    )
    if subdir is None:
        project = tmpdir / name
    else:
        project = tmpdir / name / subdir
    monkeypatch.chdir(project)
    return project


@pytest.fixture
def normalized_name(request):
    """
    Normalized name according to
    https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode
    """
    name = request.param
    return re.sub(r"[-_.]+", "_", name).lower()


@pytest.mark.parametrize(
    "git_tree,normalized_name",
    (
        pytest.param(
            (
                "setuptools",
                "https://github.com/pypa/setuptools",
                None,
            ),
            "setuptools",
            id="setuptools.build_meta",
        ),
        pytest.param(
            (
                "poetry-core",
                "https://github.com/python-poetry/poetry-core",
                None,
            ),
            "poetry-core",
            id="poetry.core.masonry.api",
        ),
        pytest.param(
            (
                "flit",
                "https://github.com/pypa/flit",
                "flit_core",
            ),
            "flit_core",
            id="flit_core.buildapi",
        ),
        pytest.param(
            (
                "hatchling",
                "https://github.com/pypa/hatch",
                "backend",
            ),
            "hatchling",
            id="hatchling.ouroboros",
        ),
        pytest.param(
            (
                "trampolim",
                "https://github.com/FFY00/trampolim",
                None,
            ),
            "trampolim",
            id="trampolim",
        ),
        pytest.param(
            (
                "pdm-pep517",
                "https://github.com/pdm-project/pdm-pep517",
                None,
            ),
            "pdm-pep517",
            id="pdm-pep517",
        ),
        pytest.param(
            (
                "enscons",
                "https://github.com/dholth/enscons",
                None,
            ),
            "enscons",
            marks=pytest.mark.xfail(
                reason="https://github.com/dholth/enscons/issues/25",
                strict=True,
            ),
            id="enscons",
        ),
    ),
    indirect=True,
)
def test_build_and_install_in_tree_backends(
    virt_env_installer, git_tree, install_build_deps, destdir, normalized_name
):
    python = str(virt_env_installer.exe)
    install_build_deps(python, srcdir=git_tree)
    build_args = [python, "-m", "pyproject_installer", "build"]
    subprocess.check_call(build_args, cwd=git_tree)

    # base check for build result
    build_files = {f.name for f in (git_tree / "dist").iterdir()}
    # wheel and tracker
    assert len(build_files) == 2
    assert ".wheeltracker" in build_files

    wheels = [f for f in build_files if f.endswith(".whl")]
    assert len(wheels) == 1
    assert wheels[0].startswith(f"{normalized_name}-")

    install_args = [
        python,
        "-m",
        "pyproject_installer",
        "install",
        "--destdir",
        destdir,
    ]
    subprocess.check_call(install_args, cwd=git_tree)

    # base check for installation result
    # assume the backends are pure Python packages for simplification
    purelib = subprocess.check_output(
        [
            python,
            "-c",
            "import sysconfig; print(sysconfig.get_path('purelib'))",
        ],
        cwd=git_tree,
        encoding="utf-8",
    ).rstrip()

    assert purelib

    installed_purelib = Path(str(destdir) + purelib)
    installed_files = {f.name for f in installed_purelib.iterdir()}
    # dist-info
    dist_infos = [f for f in installed_files if f.endswith(".dist-info")]
    assert len(dist_infos) == 1
    assert dist_infos[0].startswith(f"{normalized_name}-")

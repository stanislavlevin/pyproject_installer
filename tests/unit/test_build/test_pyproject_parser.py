"""Tests for parser of pyproject.toml"""
import json
import textwrap
import sys

import pytest

from pyproject_installer.build_cmd import build_wheel
from pyproject_installer.build_cmd._build import BACKEND_CALLER


def test_pyproject_invalid_toml(pyproject, wheeldir):
    pyproject_path = pyproject("content\n")

    with pytest.raises(ValueError, match="Invalid pyproject.toml"):
        build_wheel(pyproject_path, outdir=wheeldir)


def test_pyproject_missing_requires(pyproject, wheeldir):
    pyproject_path = pyproject("[build-system]\n")

    with pytest.raises(
        KeyError, match="Missing mandatory build-system.requires"
    ):
        build_wheel(pyproject_path, outdir=wheeldir)


@pytest.mark.parametrize(
    "requires",
    ('"foo"', '{key = "value"}', "[1, 2]"),
    ids=["string", "inline_table", "array_of_int"],
)
def test_pyproject_invalid_requires(requires, pyproject, wheeldir):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires={}
            build-backend="be"
            """
        ).format(requires),
    )
    with pytest.raises(TypeError, match="requires should be a list of strings"):
        build_wheel(pyproject_path, outdir=wheeldir)


@pytest.mark.parametrize(
    "build_backend",
    ('["foo"]', '{key = "value"}', "1"),
    ids=["array_of_strings", "inline_table", "int"],
)
def test_pyproject_invalid_build_backend(build_backend, pyproject, wheeldir):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires=[]
            build-backend={}
            """
        ).format(build_backend),
    )
    with pytest.raises(TypeError, match="build-backend should be a string"):
        build_wheel(pyproject_path, outdir=wheeldir)


@pytest.mark.parametrize(
    "backend_path",
    ('"foo"', '{key = "value"}', "[1]"),
    ids=["string", "inline_table", "array_of_int"],
)
def test_pyproject_invalid_backend_path(backend_path, pyproject, wheeldir):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires=[]
            build-backend="be"
            backend-path={}
            """
        ).format(backend_path),
    )
    with pytest.raises(
        TypeError, match="backend-path should be a list of strings"
    ):
        build_wheel(pyproject_path, outdir=wheeldir)


@pytest.mark.parametrize(
    "backend_paths",
    ("'/foo'", "'/foo', '.'", "'.', '/foo'"),
    ids=["abs", "abs_rel", "rel_abs"],
)
def test_pyproject_absolute_backend_path(backend_paths, pyproject, wheeldir):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires=[]
            build-backend="foo.bar"
            backend-path=[{backend_paths}]
            """
        ).format(backend_paths=backend_paths),
    )
    with pytest.raises(
        ValueError, match="Invalid absolute backend-path: /foo,"
    ):
        build_wheel(pyproject_path, outdir=wheeldir)


@pytest.mark.parametrize(
    "backend_paths",
    ("'./foo'", "'./foo', '.'", "'.', './foo'"),
    ids=["nonexistent", "nonexistent_existent", "existent_nonexistent"],
)
def test_pyproject_nonexistent_backend_path(backend_paths, pyproject, wheeldir):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires=[]
            build-backend="foo.bar"
            backend-path=[{backend_paths}]
            """
        ).format(backend_paths=backend_paths),
    )
    with pytest.raises(
        ValueError, match="Unable to resolve backend-path: ./foo"
    ):
        build_wheel(pyproject_path, outdir=wheeldir)


@pytest.mark.parametrize(
    "backend_paths",
    ("'../foo'", "'../foo', '.'", "'.', '../foo'"),
    ids=["out", "out_in", "in_out"],
)
def test_pyproject_outside_backend_path(backend_paths, pyproject, wheeldir):
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires=[]
            build-backend="foo.bar"
            backend-path=[{backend_paths}]
            """
        ).format(backend_paths=backend_paths),
    )

    foodir = pyproject_path.parent / "foo"
    foodir.mkdir()

    with pytest.raises(
        ValueError,
        match=(
            "Invalid backend-path, path should refer to location within "
            f"source tree, given ../foo is resolved to {foodir}"
        ),
    ):
        build_wheel(pyproject_path, outdir=wheeldir)


def test_pyproject_missing_build_system(mock_build, pyproject):
    """If build-system is missing then the default backend should be used"""
    pyproject_path = pyproject("[sometable]\n")
    outdir = pyproject_path / "dist"

    build_wheel(pyproject_path, outdir=outdir)

    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "setuptools.build_meta:__legacy__",
            "build_wheel",
            "--hook-args",
            json.dumps([[str(outdir)], {"config_settings": None}]),
        ],
        "stdin": None,
        "capture_output": True,
        "cwd": pyproject_path,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)


def test_pyproject_missing_build_backend(mock_build, pyproject):
    """If build-backend is missing then the default backend should be used"""
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires=[]
            """
        ),
    )
    outdir = pyproject_path / "dist"

    build_wheel(pyproject_path, outdir=outdir)
    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "setuptools.build_meta:__legacy__",
            "build_wheel",
            "--hook-args",
            json.dumps([[str(outdir)], {"config_settings": None}]),
        ],
        "stdin": None,
        "capture_output": True,
        "cwd": pyproject_path,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)


def test_pyproject_build_backend(mock_build, pyproject):
    """Check build-backend"""
    pyproject_path = pyproject()
    outdir = pyproject_path / "dist"

    build_wheel(pyproject_path, outdir=outdir)
    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "be",
            "build_wheel",
            "--hook-args",
            json.dumps([[str(outdir)], {"config_settings": None}]),
        ],
        "stdin": None,
        "capture_output": True,
        "cwd": pyproject_path,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)


@pytest.mark.parametrize(
    "backend_paths,expected_beps",
    (("'.'", ["."]), ("'.', 'src'", [".", "src"])),
    ids=["one_path", "multiple_paths"],
)
def test_pyproject_build_backend_path(
    backend_paths, expected_beps, mock_build, pyproject
):
    """Check in-tree backend paths"""
    pyproject_path = pyproject(
        textwrap.dedent(
            """\
            [build-system]
            requires=[]
            build-backend="be"
            backend-path=[{backend_paths}]
            """
        ).format(backend_paths=backend_paths),
    )
    outdir = pyproject_path / "dist"
    (pyproject_path / "src").mkdir()

    build_wheel(pyproject_path, outdir=outdir)

    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "be",
        ]
        + [x for bep in expected_beps for x in ("--backend-path", bep)]
        + [
            "build_wheel",
            "--hook-args",
            json.dumps([[str(outdir)], {"config_settings": None}]),
        ],
        "stdin": None,
        "capture_output": True,
        "cwd": pyproject_path,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)

from pathlib import Path
from subprocess import CalledProcessError
import json
import os
import sys

import pytest

from pyproject_installer.build_cmd import (
    build_wheel,
    build_sdist,
    build_metadata,
    WHEEL_TRACKER,
)
from pyproject_installer.build_cmd._build import (
    SUPPORTED_BUILD_HOOKS,
    build,
)
from pyproject_installer.lib.build_backend import BACKEND_CALLER


def test_srcdir_nonexistent(wheeldir):
    with pytest.raises(
        ValueError,
        match="Unable to resolve path for source directory",
    ):
        build_wheel(Path("/nonexistent/path"), outdir=wheeldir)


def test_srcdir_nondir(tmpdir, wheeldir):
    file_src = tmpdir / "file_src"
    file_src.touch()
    with pytest.raises(ValueError, match="Source path should be a directory"):
        build_wheel(file_src, outdir=wheeldir)


def test_srcdir_nonpython_project(tmpdir, wheeldir):
    with pytest.raises(
        ValueError, match="Required either pyproject.toml or setup.py"
    ):
        build_wheel(tmpdir, outdir=wheeldir)


def test_missing_pyproject_config(mock_build, tmpdir):
    """If pyproject.toml is missing then the default backend should be used"""
    wheeldir = tmpdir / "dist"
    setuppy = tmpdir / "setup.py"
    setuppy.touch()

    build_wheel(tmpdir, outdir=wheeldir)
    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "setuptools.build_meta:__legacy__",
            "build_wheel",
            "--hook-args",
            json.dumps([[str(wheeldir)], {"config_settings": None}]),
        ],
        "stdin": None,
        "capture_output": True,
        "cwd": tmpdir,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)


@pytest.mark.parametrize(
    "build_args",
    ({}, {"verbose": False}, {"verbose": True}),
    ids=["default", "quiet", "verbose"],
)
def test_verbosity(mock_build, pyproject, build_args):
    """Check verbosity"""
    pyproject_path = pyproject()
    wheeldir = pyproject_path / "dist"

    verbose = build_args.get("verbose", False)
    capture = not verbose

    # emulate build error to see captured out/err
    stdout, stderr = (b"stdout", b"stderr") if capture else (None, None)

    mock_build.side_effect = CalledProcessError(
        1, ["command args"], output=stdout, stderr=stderr
    )

    expected_err_msg = "build_wheel failed"
    if not verbose:
        expected_err_msg += (
            "\n\nCaptured stdout:\n\nstdout\n\nCaptured stderr:\n\nstderr"
        )
    with pytest.raises(RuntimeError) as e:
        build_wheel(pyproject_path, outdir=wheeldir, **build_args)

    assert str(e.value) == expected_err_msg

    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
        ]
        + [x for x in ("--verbose",) if verbose]
        + [
            "be",
            "build_wheel",
            "--hook-args",
            json.dumps([[str(wheeldir)], {"config_settings": None}]),
        ],
        "stdin": None,
        "capture_output": not verbose,
        "cwd": pyproject_path,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)


def test_paths_resolved(mock_build, pyproject, monkeypatch):
    """Check if srcdir and wheeldir are resolved for backend"""
    pyproject_path = pyproject()
    cwd = pyproject_path.parent
    monkeypatch.chdir(cwd)

    wheeldir = cwd / "dist"

    build_wheel(
        pyproject_path.relative_to(cwd), outdir=wheeldir.relative_to(cwd)
    )
    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "be",
            "build_wheel",
            "--hook-args",
            json.dumps([[str(wheeldir)], {"config_settings": None}]),
        ],
        "stdin": None,
        "capture_output": True,
        "cwd": pyproject_path,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)


def test_build_backend_config_settings(mock_build, pyproject):
    """Check build-backend"""
    pyproject_path = pyproject()
    wheeldir = pyproject_path / "dist"
    config = {"key": "value"}

    build_wheel(pyproject_path, outdir=wheeldir, config=config)
    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "be",
            "build_wheel",
            "--hook-args",
            json.dumps([[str(wheeldir)], {"config_settings": config}]),
        ],
        "stdin": None,
        "capture_output": True,
        "cwd": pyproject_path,
        "check": True,
        "pass_fds": (4,),
    }
    mock_build.assert_called_once_with(**b_kwargs)


def test_nonexistent_outdir(mock_build, pyproject):
    """Check if outdir is created when it's missing"""
    pyproject_path = pyproject()

    outdir = pyproject_path / "dist"
    assert not outdir.exists()

    build_wheel(pyproject_path, outdir=outdir)

    assert outdir.exists()


def test_existent_outdir(mock_build, pyproject):
    """Check if build_wheel doesn't fail on existent outdir"""
    pyproject_path = pyproject()

    outdir = pyproject_path / "dist"
    outdir.mkdir()

    build_wheel(pyproject_path, outdir=outdir)


@pytest.mark.skipif(os.geteuid() == 0, reason="Requires unprivileged user")
def test_uncreatable_outdir(mock_build, pyproject):
    """Check error if outdir is uncreatable(e.g. not enough permissions)"""
    pyproject_path = pyproject()

    outdir = Path("/uncreatable_dir")
    with pytest.raises(
        ValueError,
        match="Unable to create path for outdir: /uncreatable_dir",
    ):
        build_wheel(pyproject_path, outdir=outdir)


def test_wheeltracker(mock_build, pyproject):
    """Check if .wheeltracker is written on build"""
    pyproject_path = pyproject()
    outdir = pyproject_path / "dist"

    tracker = outdir / WHEEL_TRACKER
    assert not tracker.exists()

    build_wheel(pyproject_path, outdir=outdir)

    assert tracker.is_file()
    assert tracker.read_text().rstrip() == "foo.whl"


def test_sdist_no_wheeltracker(mock_build, pyproject):
    """Check if .wheeltracker is not created on sdist build"""
    pyproject_path = pyproject()
    outdir = pyproject_path / "dist"

    tracker = outdir / WHEEL_TRACKER
    assert not tracker.exists()

    build_sdist(pyproject_path, outdir=outdir)

    assert not tracker.exists()


def test_build_invalid_hook(pyproject):
    pyproject_path = pyproject()
    outdir = pyproject_path / "dist"
    invalid_hook = "invalid_hook"

    with pytest.raises(
        ValueError,
        match=(
            f"Unknown build hook: {invalid_hook}, "
            f"supported: {', '.join(SUPPORTED_BUILD_HOOKS)}"
        ),
    ):
        build(pyproject_path, outdir=outdir, hook=invalid_hook)


@pytest.mark.parametrize("hook", SUPPORTED_BUILD_HOOKS)
def test_supported_build_hooks(hook, mock_build, pyproject):
    """Check build hook"""
    pyproject_path = pyproject()
    outdir = pyproject_path / "dist"

    build(pyproject_path, outdir=outdir, hook=hook)
    b_kwargs = {
        "args": [
            sys.executable,
            BACKEND_CALLER,
            "--result-fd",
            "4",
            "be",
            hook,
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


def test_raisable_thread(mock_build, pyproject, mocker):
    """Check if build fails on raised thread"""
    pyproject_path = pyproject()
    outdir = pyproject_path / "dist"

    # override mock_build's mock for os.read
    mock_os_read = mocker.patch("pyproject_installer.lib.build_backend.os.read")

    # emulate os.read error to raise thread
    mock_os_read.side_effect = OSError("oops")

    with pytest.raises(RuntimeError, match="oops"):
        build_wheel(pyproject_path, outdir=outdir)


def test_received_invalid_data(mock_build, pyproject, mocker):
    """Check if build fails on invalid data"""
    pyproject_path = pyproject()
    outdir = pyproject_path / "dist"

    # override mock_build's mock for os.read
    mock_os_read = mocker.patch("pyproject_installer.lib.build_backend.os.read")
    mock_os_read.side_effect = [b"invalid_json", b""]

    with pytest.raises(
        RuntimeError,
        match="Received invalid JSON data from backend helper: 'invalid_json'",
    ):
        build_wheel(pyproject_path, outdir=outdir)


def test_metadata_no_wheeltracker_metadata(pyproject_metadata):
    """Check if .wheeltracker is not created on metadata build (metadata)"""
    pyproject_path = pyproject_metadata()
    outdir = pyproject_path / "dist"

    tracker = outdir / WHEEL_TRACKER
    assert not tracker.exists()

    build_metadata(pyproject_path, outdir=outdir)

    assert not tracker.exists()


def test_metadata_no_wheeltracker_wheel(pyproject_metadata_wheel):
    """Check if .wheeltracker is not created on metadata build (wheel)"""
    pyproject_path = pyproject_metadata_wheel()
    outdir = pyproject_path / "dist"

    tracker = outdir / WHEEL_TRACKER
    assert not tracker.exists()

    build_metadata(pyproject_path, outdir=outdir)

    assert not tracker.exists()


def test_metadata_nonexistent_outdir(pyproject_metadata):
    """Check if outdir is created when it's missing on metadata build"""
    pyproject_path = pyproject_metadata()

    outdir = pyproject_path / "dist"
    assert not outdir.exists()

    build_metadata(pyproject_path, outdir=outdir)

    assert outdir.exists()


def test_metadata_existent_outdir(pyproject_metadata):
    """Check if build_metadata doesn't fail on existent outdir"""
    pyproject_path = pyproject_metadata()

    outdir = pyproject_path / "dist"
    outdir.mkdir()

    build_metadata(pyproject_path, outdir=outdir)


def test_metadata_outdir_resolved(pyproject_metadata):
    """Check if outdir is resolved for build_metadata"""
    pyproject_path = pyproject_metadata()

    outdir = Path("dist")
    expected_outdir = pyproject_path / outdir
    assert not expected_outdir.exists()

    build_metadata(pyproject_path, outdir=outdir)

    assert expected_outdir.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="Requires unprivileged user")
def test_metadata_uncreatable_outdir(pyproject_metadata):
    """Check error if outdir is uncreatable(e.g. not enough permissions)"""
    pyproject_path = pyproject_metadata()

    outdir = Path("/uncreatable_dir")
    with pytest.raises(
        ValueError,
        match="Unable to create path for outdir: /uncreatable_dir",
    ):
        build_metadata(pyproject_path, outdir=outdir)


def test_metadata_content_metadata(pyproject_metadata):
    """Check content of metadata for build_metadata (metadata)"""
    expected_fields = [
        "Metadata-Version: 2.1",
        "Name: foo",
        "Version: 1.0",
    ]
    pyproject_path = pyproject_metadata(expected_fields)
    outdir = pyproject_path / "dist"

    metadata_filename = build_metadata(pyproject_path, outdir=outdir)
    assert metadata_filename == "METADATA"
    actual_contents = (outdir / metadata_filename).read_text(encoding="utf-8")
    expected_contents = "\n".join(expected_fields) + "\n"
    assert actual_contents == expected_contents


def test_metadata_content_wheel(pyproject_metadata_wheel):
    """Check content of metadata for build_metadata (wheel)"""
    expected_fields = [
        "Metadata-Version: 2.1",
        "Name: foo",
        "Version: 1.0",
    ]
    pyproject_path = pyproject_metadata_wheel(expected_fields)
    outdir = pyproject_path / "dist"

    metadata_filename = build_metadata(pyproject_path, outdir=outdir)
    assert metadata_filename == "METADATA"
    actual_contents = (outdir / metadata_filename).read_text(encoding="utf-8")
    expected_contents = "\n".join(expected_fields) + "\n"
    assert actual_contents == expected_contents

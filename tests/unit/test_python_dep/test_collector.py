"""Tests for collecting Python version constraints from metadata."""

import json

import pytest

from pyproject_installer.python_dep_cmd import python_dep_command
from tests.conftest import default_content_fields


@pytest.fixture(
    params=(
        "Requires-Python: invalid",
        "Requires-Python: >=3.12; os_name=='posix'",
        "Requires-Dist: invalid!",
        # Requires-Python may appear only once
        "Requires-Python: >=3.12\nRequires-Python: <4",
    ),
)
def invalid_header(request):
    """Return invalid core metadata headers."""
    return request.param


def test_metadata_python_collect(
    valid_requires_python_data,
    pyproject_metadata,
    depsconfig,
):
    """
    Collect Requires-Python from metadata built with
    prepare_metadata_for_build_wheel hook.
    """
    depsconfig_path = depsconfig("{}")
    python_req, expected_python = valid_requires_python_data

    pyproject_metadata(python_req=python_req)

    python_dep_command("sync", depsconfig_path)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_python


def test_metadata_python_collect_wheel(
    valid_requires_python_data,
    pyproject_metadata_wheel,
    depsconfig,
):
    """Collect Requires-Python from metadata built with build_wheel."""
    depsconfig_path = depsconfig("{}")
    python_req, expected_python = valid_requires_python_data

    pyproject_metadata_wheel(python_req=python_req)

    python_dep_command("sync", depsconfig_path)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_python


def test_metadata_python_collect_creates_cache(
    pyproject_metadata,
    depsconfig,
):
    """Save built metadata to the cache on the first collection."""
    project = pyproject_metadata(python_req=">=3.12")
    config_path = depsconfig("{}")
    cache_path = project / "dist" / "metadata_cache"
    assert not cache_path.exists()

    python_dep_command("sync", config_path)

    assert cache_path.is_file()
    actual_metadata = cache_path.read_text(encoding="utf-8")
    expected_header = "Requires-Python: >=3.12"
    assert expected_header in actual_metadata


@pytest.mark.parametrize("python_req", ("", "   "))
def test_metadata_python_collect_empty(
    python_req,
    pyproject_metadata,
    depsconfig,
):
    """Treat an empty built Requires-Python field as absent."""
    pyproject_metadata(python_req=python_req)
    config_path = depsconfig("{}")

    python_dep_command("sync", config_path)

    actual_config = json.loads(config_path.read_text())
    expected_config: dict[str, str] = {}
    assert actual_config == expected_config


@pytest.mark.parametrize("python_req", ("", "   "))
def test_metadata_python_collect_empty_wheel(
    python_req,
    pyproject_metadata_wheel,
    depsconfig,
):
    """Treat an empty Requires-Python field from a wheel as absent."""
    pyproject_metadata_wheel(python_req=python_req)
    config_path = depsconfig("{}")

    python_dep_command("sync", config_path)

    actual_config = json.loads(config_path.read_text())
    expected_config: dict[str, str] = {}
    assert actual_config == expected_config


@pytest.mark.parametrize("python_req", ("", "   "))
def test_metadata_python_collect_empty_cached(
    python_req,
    pyproject_metadata,
    depsconfig,
):
    """Treat an empty cached Requires-Python field as absent."""
    project = pyproject_metadata(python_req=">=3.12")
    config_path = depsconfig("{}")
    cache_path = project / "dist" / "metadata_cache"
    cache_path.parent.mkdir()
    headers = [*default_content_fields, f"Requires-Python: {python_req}"]
    cache_path.write_text("\n".join(headers) + "\n")

    python_dep_command("sync", config_path)

    actual_config = json.loads(config_path.read_text())
    expected_config: dict[str, str] = {}
    assert actual_config == expected_config


def test_metadata_python_collect_cached(
    valid_requires_python_data,
    pyproject_metadata,
    depsconfig,
):
    """Collect Requires-Python from cached metadata without rebuilding."""
    depsconfig_path = depsconfig("{}")
    python_req, expected_python = valid_requires_python_data

    # The backend would return a different constraint; the cache must win.
    project = pyproject_metadata(python_req=">=3.11")
    cache_path = project / "dist" / "metadata_cache"
    cache_path.parent.mkdir()
    cache_headers = [*default_content_fields, f"Requires-Python: {python_req}"]
    cache_path.write_text("\n".join(cache_headers) + "\n")

    python_dep_command("sync", depsconfig_path)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_python


def test_python_dep_invalid_metadata(
    invalid_header,
    pyproject_metadata,
    depsconfig,
):
    """Reject invalid built metadata."""
    headers = [*default_content_fields, *invalid_header.splitlines()]
    pyproject_metadata(headers=headers)
    config_path = depsconfig("{}")

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)


def test_python_dep_invalid_metadata_no_stdout(
    pyproject_metadata,
    depsconfig,
    capsys,
):
    """Write nothing to stdout when built metadata is invalid."""
    pyproject_metadata(python_req="invalid")
    config_path = depsconfig("{}")

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)

    actual_output = capsys.readouterr().out
    assert not actual_output


def test_python_dep_does_not_cache_invalid_metadata(
    pyproject_metadata,
    depsconfig,
):
    """Do not cache invalid built metadata."""
    project = pyproject_metadata(python_req="invalid")
    config_path = depsconfig("{}")
    cache_path = project / "dist" / "metadata_cache"

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)

    assert not cache_path.exists()


def test_python_dep_invalid_cached_metadata(
    invalid_header,
    pyproject_metadata,
    depsconfig,
):
    """Reject invalid cached metadata."""
    headers = [*default_content_fields, *invalid_header.splitlines()]
    project = pyproject_metadata()
    config_path = depsconfig("{}")
    cache_path = project / "dist" / "metadata_cache"
    cache_path.parent.mkdir()
    cache_path.write_text("\n".join(headers) + "\n")

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)


def test_python_dep_invalid_cached_metadata_no_stdout(
    pyproject_metadata,
    depsconfig,
    capsys,
):
    """Write nothing to stdout when cached metadata is invalid."""
    project = pyproject_metadata()
    config_path = depsconfig("{}")
    cache_path = project / "dist" / "metadata_cache"
    cache_path.parent.mkdir()
    headers = [*default_content_fields, "Requires-Python: invalid"]
    cache_path.write_text("\n".join(headers) + "\n")

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)

    actual_output = capsys.readouterr().out
    assert not actual_output


def test_python_dep_invalid_cached_metadata_preserves_cache(
    pyproject_metadata,
    depsconfig,
):
    """Preserve the cache when cached metadata is invalid."""
    project = pyproject_metadata()
    config_path = depsconfig("{}")
    cache_path = project / "dist" / "metadata_cache"
    cache_path.parent.mkdir()
    headers = [*default_content_fields, "Requires-Python: invalid"]
    expected_metadata = "\n".join(headers) + "\n"
    cache_path.write_text(expected_metadata)

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)

    actual_metadata = cache_path.read_text()
    assert actual_metadata == expected_metadata

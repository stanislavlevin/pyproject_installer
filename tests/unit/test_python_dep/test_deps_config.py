"""Tests for storing, verifying, and printing Python version constraints."""

import json

import pytest

from pyproject_installer.errors import DepsSourcesConfigError, DepsUnsyncedError
from pyproject_installer.python_dep_cmd import python_dep_command
from tests.conftest import default_content_fields


@pytest.fixture(
    params=(
        '{"requires_python": null}',
        '{"requires_python": 312}',
        '{"requires_python": []}',
        '{"requires_python": {}}',
        '{"requires_python": "3.12"}',
        '{"requires_python": ">=invalid"}',
        '{"requires_python": "invalid"}',
        '{"requires_python": ">=3.12; os_name==\'posix\'"}',
    ),
)
def invalid_python_config(request):
    """Return a config with an invalid Python constraint."""
    return request.param


def test_python_dep_first_sync(
    valid_requires_python_data,
    pyproject_metadata,
    depsconfig_path,
):
    """Create a missing config and store the collected Python constraint."""
    python_req, expected_python = valid_requires_python_data
    pyproject_metadata(python_req=python_req)

    python_dep_command("sync", depsconfig_path)

    actual_config = json.loads(depsconfig_path.read_text())
    expected_config = {
        "sources": {},
        **expected_python,
    }
    assert actual_config == expected_config


def test_python_dep_first_sync_verify(
    valid_requires_python_data,
    pyproject_metadata,
    depsconfig_path,
    capsys,
):
    """Save a newly declared constraint before reporting verification drift."""
    python_req, expected_python = valid_requires_python_data
    normalized = expected_python["requires_python"]
    pyproject_metadata(python_req=python_req)

    with pytest.raises(DepsUnsyncedError):
        python_dep_command("sync", depsconfig_path, verify=True)

    actual_diff = json.loads(capsys.readouterr().out)
    expected_diff = {
        "requires_python": {"new": normalized},
    }
    assert actual_diff == expected_diff
    actual_config = json.loads(depsconfig_path.read_text())
    expected_config = {
        "sources": {},
        "requires_python": normalized,
    }
    assert actual_config == expected_config


def test_python_dep_first_sync_verify_without_constraint(
    pyproject_metadata,
    depsconfig_path,
):
    """Create a config and pass verification when no constraint is declared."""
    pyproject_metadata()

    python_dep_command("sync", depsconfig_path, verify=True)

    actual_config = json.loads(depsconfig_path.read_text())
    expected_config: dict[str, object] = {
        "sources": {},
    }
    assert actual_config == expected_config


@pytest.mark.parametrize(
    "stored,python_req,expected_python",
    (
        ({}, ">=3.12", {"requires_python": ">=3.12"}),
        ({"requires_python": ">=3.11"}, None, {}),
        ({"requires_python": ">=3.11"}, "", {}),
        (
            {"requires_python": ">=3.11"},
            ">=3.12, <4",
            {"requires_python": "<4,>=3.12"},
        ),
    ),
)
def test_python_dep_sync_existing(
    stored,
    python_req,
    expected_python,
    pyproject_metadata,
    depsconfig,
):
    """Save added, removed, or changed constraints."""
    pyproject_metadata(python_req=python_req)
    config_path = depsconfig(json.dumps(stored))

    python_dep_command("sync", config_path)

    actual_config = json.loads(config_path.read_text())
    assert actual_config == expected_python


@pytest.mark.parametrize(
    "stored,python_req,expected_python,diff",
    (
        (
            {},
            ">=3.12",
            {"requires_python": ">=3.12"},
            {"new": ">=3.12"},
        ),
        ({"requires_python": ">=3.11"}, None, {}, {"old": ">=3.11"}),
        ({"requires_python": ">=3.11"}, "", {}, {"old": ">=3.11"}),
        (
            {"requires_python": ">=3.11"},
            ">=3.12, <4",
            {"requires_python": "<4,>=3.12"},
            {"old": ">=3.11", "new": "<4,>=3.12"},
        ),
    ),
)
def test_python_dep_sync_existing_verify(
    stored,
    python_req,
    expected_python,
    diff,
    pyproject_metadata,
    depsconfig,
    capsys,
):
    """Save changed constraints before reporting verification drift."""
    pyproject_metadata(python_req=python_req)
    config_path = depsconfig(json.dumps(stored))

    with pytest.raises(DepsUnsyncedError):
        python_dep_command("sync", config_path, verify=True)

    actual_diff = json.loads(capsys.readouterr().out)
    expected_diff = {"requires_python": diff}
    assert actual_diff == expected_diff
    actual_config = json.loads(config_path.read_text())
    assert actual_config == expected_python


def test_python_dep_sync_preserves_other_fields(pyproject_metadata, depsconfig):
    """Preserve unrelated config fields when saving a constraint."""
    pyproject_metadata(python_req=">=3.12")
    config_path = depsconfig('{"other": {"preserved": true}}')

    python_dep_command("sync", config_path)

    actual_config = json.loads(config_path.read_text())
    expected_config = {
        "other": {"preserved": True},
        "requires_python": ">=3.12",
    }
    assert actual_config == expected_config


def test_python_dep_sync_verify_preserves_other_fields(
    pyproject_metadata,
    depsconfig,
):
    """Preserve unrelated config fields when verification saves a change."""
    pyproject_metadata(python_req=">=3.12")
    config_path = depsconfig('{"other": {"preserved": true}}')

    with pytest.raises(DepsUnsyncedError):
        python_dep_command("sync", config_path, verify=True)

    actual_config = json.loads(config_path.read_text())
    expected_config = {
        "other": {"preserved": True},
        "requires_python": ">=3.12",
    }
    assert actual_config == expected_config


def test_python_dep_sync_uses_config_path(pyproject_metadata, depsconfig):
    """Save to the supplied config path without creating a default config."""
    project = pyproject_metadata(python_req=">=3.12")
    config_path = depsconfig("{}")

    python_dep_command("sync", config_path)

    actual_config = json.loads(config_path.read_text())
    expected_config = {"requires_python": ">=3.12"}
    assert actual_config == expected_config
    assert not (project / "pyproject_deps.json").exists()


@pytest.mark.parametrize(
    "stored,python_req",
    (
        (
            {"requires_python": " >=3.12.0, <4 "},
            "<4, >=3.12",
        ),
        ({}, None),
    ),
)
def test_python_dep_sync_in_sync(
    stored,
    python_req,
    pyproject_metadata,
    depsconfig,
):
    """Accept equivalent or absent constraints without reporting drift."""
    pyproject_metadata(python_req=python_req)
    expected_config = stored
    config_path = depsconfig(json.dumps(stored))

    python_dep_command("sync", config_path, verify=True)

    actual_config = json.loads(config_path.read_text())
    assert actual_config == expected_config


def test_python_dep_sync_no_stdout(pyproject_metadata, depsconfig, capsys):
    """Write nothing to stdout after syncing a constraint."""
    pyproject_metadata(python_req=">=3.12")
    config_path = depsconfig("{}")

    python_dep_command("sync", config_path)

    actual_output = capsys.readouterr().out
    assert not actual_output


@pytest.mark.parametrize("python_req", ("", "   "))
def test_python_dep_sync_verify_empty_metadata_constraint(
    python_req,
    pyproject_metadata,
    depsconfig,
    capsys,
):
    """Treat empty metadata constraints as absent during verification."""
    pyproject_metadata(python_req=python_req)
    config_path = depsconfig("{}")

    python_dep_command("sync", config_path, verify=True)

    actual_config = json.loads(config_path.read_text())
    expected_config: dict[str, str] = {}
    assert actual_config == expected_config
    actual_output = capsys.readouterr().out
    assert not actual_output


def test_python_dep_sync_verify_unchanged_no_stdout(
    pyproject_metadata,
    depsconfig,
    capsys,
):
    """Write nothing to stdout when verification finds no changes."""
    pyproject_metadata(python_req=">=3.12")
    config_path = depsconfig('{"requires_python": ">=3.12"}')

    python_dep_command("sync", config_path, verify=True)

    actual_output = capsys.readouterr().out
    assert not actual_output


@pytest.mark.parametrize(
    "stored,depformat,expected_output",
    (
        ({}, None, ""),
        ({"requires_python": ">=3.12, <4"}, None, "<4,>=3.12\n"),
        ({}, "python3$rpmlowver", "python3\n"),
        ({}, "$specifier", ""),
        (
            {"requires_python": ">=3.12, <4"},
            "python3 $specifier",
            "python3 <4,>=3.12\n",
        ),
        (
            {"requires_python": ">=3.12, <4"},
            "python3$rpmlowver",
            "python3 >= 3.12\n",
        ),
        ({"requires_python": ">=3.12"}, "python3", "python3\n"),
        ({"requires_python": ">=3.12"}, "", ""),
        ({}, "  ", "  \n"),
        ({"requires_python": "<4"}, "python3$rpmlowver", "python3\n"),
    ),
)
def test_python_dep_print(
    stored,
    depformat,
    expected_output,
    depsconfig,
    capsys,
):
    """Print normalized constraints and templates."""
    config_path = depsconfig(json.dumps(stored))

    python_dep_command("print", config_path, depformat=depformat)

    actual_output = capsys.readouterr().out
    assert actual_output == expected_output


def test_python_dep_sync_invalid_config(
    invalid_python_config,
    depsconfig,
):
    """Reject invalid stored constraints when syncing."""
    config_path = depsconfig(invalid_python_config)

    with pytest.raises(DepsSourcesConfigError):
        python_dep_command("sync", config_path)


def test_python_dep_print_invalid_config(
    invalid_python_config,
    depsconfig,
):
    """Reject invalid stored constraints when printing."""
    config_path = depsconfig(invalid_python_config)

    with pytest.raises(DepsSourcesConfigError):
        python_dep_command("print", config_path)


def test_python_dep_sync_invalid_config_no_stdout(depsconfig, capsys):
    """Write nothing to stdout when syncing rejects an invalid config."""
    config_path = depsconfig('{"requires_python": "invalid"}')

    with pytest.raises(DepsSourcesConfigError):
        python_dep_command("sync", config_path, verify=True)

    actual_output = capsys.readouterr().out
    assert not actual_output


def test_python_dep_print_invalid_config_no_stdout(depsconfig, capsys):
    """Write nothing to stdout when printing rejects an invalid config."""
    config_path = depsconfig('{"requires_python": "invalid"}')

    with pytest.raises(DepsSourcesConfigError):
        python_dep_command("print", config_path)

    actual_output = capsys.readouterr().out
    assert not actual_output


def test_python_dep_sync_invalid_config_preserves_config(depsconfig):
    """Leave an invalid config unchanged when syncing fails."""
    expected_config = '{"requires_python": "invalid"}'
    config_path = depsconfig(expected_config)

    with pytest.raises(DepsSourcesConfigError):
        python_dep_command("sync", config_path)

    actual_config = config_path.read_text()
    assert actual_config == expected_config


def test_python_dep_print_invalid_config_preserves_config(depsconfig):
    """Leave an invalid config unchanged when printing fails."""
    expected_config = '{"requires_python": "invalid"}'
    config_path = depsconfig(expected_config)

    with pytest.raises(DepsSourcesConfigError):
        python_dep_command("print", config_path)

    actual_config = config_path.read_text()
    assert actual_config == expected_config


def test_python_dep_sync_ignores_sources(
    pyproject_metadata,
    depsconfig,
):
    """Sync Python constraints without validating or changing source data."""
    pyproject_metadata(python_req=">=3.12")
    config = {
        "sources": "invalid",
        "requires_python": ">=3.11",
    }
    config_path = depsconfig(json.dumps(config))

    python_dep_command("sync", config_path)

    actual_config = json.loads(config_path.read_text())
    expected_config = {
        "sources": "invalid",
        "requires_python": ">=3.12",
    }
    assert actual_config == expected_config


def test_python_dep_print_ignores_sources(depsconfig, capsys):
    """Print Python constraints without validating or changing source data."""
    expected_config = {
        "sources": "invalid",
        "requires_python": ">=3.11",
    }
    config_path = depsconfig(json.dumps(expected_config))

    python_dep_command("print", config_path)

    actual_output = capsys.readouterr().out
    expected_output = ">=3.11\n"
    assert actual_output == expected_output
    actual_config = json.loads(config_path.read_text())
    assert actual_config == expected_config


def test_python_dep_invalid_metadata_preserves_config(
    pyproject_metadata,
    depsconfig,
):
    """Preserve the config when built metadata is invalid."""
    pyproject_metadata(python_req="invalid")
    expected_config = '{"requires_python": ">=3.11"}'
    config_path = depsconfig(expected_config)

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)

    actual_config = config_path.read_text()
    assert actual_config == expected_config


def test_python_dep_invalid_cached_metadata_preserves_config(
    pyproject_metadata,
    depsconfig,
):
    """Preserve the config when cached metadata is invalid."""
    project = pyproject_metadata()
    expected_config = '{"requires_python": ">=3.11"}'
    config_path = depsconfig(expected_config)
    cache_path = project / "dist" / "metadata_cache"
    cache_path.parent.mkdir()
    headers = [*default_content_fields, "Requires-Python: invalid"]
    cache_path.write_text("\n".join(headers) + "\n")

    with pytest.raises(
        ValueError,
        match=r"^python_dep: invalid core metadata:",
    ):
        python_dep_command("sync", config_path, verify=True)

    actual_config = config_path.read_text()
    assert actual_config == expected_config


def test_python_dep_print_missing_config(depsconfig_path):
    """Printing a missing config fails without creating it."""
    with pytest.raises(FileNotFoundError):
        python_dep_command("print", depsconfig_path)

    assert not depsconfig_path.exists()

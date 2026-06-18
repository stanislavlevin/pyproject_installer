import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from pyproject_installer.deps_cmd import deps_command
from pyproject_installer.deps_cmd.collectors import (
    metadata as metadata_collector,
)


def test_metadata_collector_metadata_valid_deps(
    valid_pep508_data,
    pyproject_metadata,
    depsconfig,
):
    """
    Collection of core metadata's valid PEP508 dependencies via
    prepare_metadata_for_build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, out_reqs = valid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata(reqs=in_reqs)

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_metadata_collector_metadata_invalid_deps(
    invalid_pep508_data,
    pyproject_metadata,
    depsconfig,
):
    """
    Collection of core metadata's invalid PEP508 dependencies via
    prepare_metadata_for_build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, _ = invalid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata(reqs=in_reqs)

    # depends on packaging error message
    expected_err = (
        f"^{collector}: invalid core metadata: .* "
        "is invalid for 'requires-dist'"
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_collector_writes_cache_on_miss(
    pyproject_metadata,
    depsconfig,
):
    """A first metadata build writes it to dist/metadata_cache."""
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata(reqs=("bar",))

    cache_path = Path.cwd() / "dist" / "metadata_cache"
    assert not cache_path.is_file()

    deps_command("sync", depsconfig_path, srcnames=[])

    assert cache_path.is_file()
    assert "Requires-Dist: bar" in cache_path.read_text(encoding="utf-8")


def test_metadata_collector_prefers_cache_over_build(
    pyproject_metadata,
    depsconfig,
):
    """A present dist/metadata_cache is used instead of building."""
    input_conf: dict[str, Any] = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    # the build would yield from-build; the cache must win
    pyproject_metadata(reqs=("from-build",))

    cache_path = Path.cwd() / "dist" / "metadata_cache"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        "Metadata-Version: 2.1\nName: foo\nVersion: 1.0\n"
        "Requires-Dist: from-cache\n",
        encoding="utf-8",
    )

    deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"]["foo"]["deps"] = ["from-cache"]
    assert actual_conf == expected_conf


def test_metadata_collector_does_not_cache_invalid_metadata(
    invalid_pep508_data,
    pyproject_metadata,
    depsconfig,
):
    """Metadata with an invalid PEP508 dep is not written to the cache."""
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, _ = invalid_pep508_data
    pyproject_metadata(reqs=in_reqs)

    with pytest.raises(ValueError, match="invalid core metadata"):
        deps_command("sync", depsconfig_path, srcnames=[])

    cache_path = Path.cwd() / "dist" / "metadata_cache"
    assert not cache_path.exists()

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_collector_rejects_invalid_metadata_fields(
    pyproject_metadata,
    depsconfig,
):
    """Core metadata invalid beyond Requires-Dist is rejected and not cached.

    Here the deps are valid but the metadata itself is invalid (no
    required Version), which only full validation catches.
    """
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata(
        headers=["Metadata-Version: 2.1", "Name: foo"],
        reqs=("bar",),
    )

    with pytest.raises(ValueError, match="invalid core metadata"):
        deps_command("sync", depsconfig_path, srcnames=[])

    cache_path = Path.cwd() / "dist" / "metadata_cache"
    assert not cache_path.exists()

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_collector_rejects_invalid_cached_metadata(
    pyproject_metadata,
    depsconfig,
):
    """A present but invalid dist/metadata_cache is rejected, not used."""
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    # a build would yield valid metadata, but the cache is consulted first
    pyproject_metadata(reqs=("bar",))

    cache_path = Path.cwd() / "dist" / "metadata_cache"
    cache_path.parent.mkdir(parents=True)
    # invalid: missing the required Version field
    cache_path.write_text(
        "Metadata-Version: 2.1\nName: foo\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid core metadata"):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_collector_builds_once_for_multiple_sources(
    pyproject_metadata,
    depsconfig,
    mocker,
):
    """One metadata build serves every metadata source synced together."""
    input_conf: dict[str, Any] = {
        "sources": {
            "a": {"srctype": "metadata"},
            "b": {"srctype": "metadata"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata(reqs=("bar",))

    spy = mocker.spy(metadata_collector, "build_metadata")

    deps_command("sync", depsconfig_path, srcnames=[])

    assert spy.call_count == 1
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"]["a"]["deps"] = ["bar"]
    expected_conf["sources"]["b"]["deps"] = ["bar"]
    assert actual_conf == expected_conf


def test_metadata_collector_reuses_cache_across_syncs(
    pyproject_metadata,
    depsconfig,
    mocker,
):
    """A later, separate sync reuses the cache the first build wrote."""
    input_conf: dict[str, Any] = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata(reqs=("bar",))

    spy = mocker.spy(metadata_collector, "build_metadata")

    # two independent deps_command invocations against the same tree
    deps_command("sync", depsconfig_path, srcnames=[])
    deps_command("sync", depsconfig_path, srcnames=[])

    assert spy.call_count == 1
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"]["foo"]["deps"] = ["bar"]
    assert actual_conf == expected_conf


def test_metadata_collector_wheel_valid_deps(
    valid_pep508_data,
    pyproject_metadata_wheel,
    depsconfig,
):
    """
    Collection of core metadata's valid PEP508 dependencies via
    build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, out_reqs = valid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata_wheel(reqs=in_reqs)

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_metadata_collector_wheel_invalid_deps(
    invalid_pep508_data,
    pyproject_metadata_wheel,
    depsconfig,
):
    """
    Collection of core metadata's invalid PEP508 dependencies via
    build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, _ = invalid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata_wheel(reqs=in_reqs)

    # depends on packaging error message
    expected_err = (
        f"^{collector}: invalid core metadata: .* "
        "is invalid for 'requires-dist'"
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

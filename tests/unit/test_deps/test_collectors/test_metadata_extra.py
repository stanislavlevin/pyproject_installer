import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from pyproject_installer.deps_cmd import deps_command
from pyproject_installer.deps_cmd.collectors import (
    metadata as metadata_collector,
)
from pyproject_installer.errors import DepsSourcesConfigError


def test_metadata_extra_collects_full_list(
    pyproject_metadata_extra,
    depsconfig,
):
    """metadata_extra stores the full Requires-Dist, markers intact."""
    srcname = "check"
    collector = "metadata_extra"
    extra = "bar"
    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [extra]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata_extra(extra, reqs=("qux", f"baz; extra == '{extra}'"))

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = [
        f'baz; extra == "{extra}"',
        "qux",
    ]
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize(
    "requested",
    ("foo-bar", "Foo.Bar", "foo_bar", "FOO-BAR"),
)
@pytest.mark.parametrize("header", ("foo-bar", "Foo.Bar", "foo_bar", "FOO_BAR"))
def test_metadata_extra_normalizes_extra(
    header,
    requested,
    pyproject_metadata_extra,
    depsconfig,
):
    """The extra is matched PEP 503/685-normalized on both the requested
    and the Provides-Extra (provided) side."""
    srcname = "check"
    collector = "metadata_extra"
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [requested],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata_extra(header, reqs=(f"baz; extra == '{header}'",))

    deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = deepcopy(input_conf)
    # sync() round-trips each dep through Requirement -> str, and packaging
    # normalizes the extra marker on the way, so the stored form is foo-bar
    # regardless of the header's spelling.
    expected_conf["sources"][srcname]["deps"] = ['baz; extra == "foo-bar"']
    assert actual_conf == expected_conf


def test_metadata_extra_unknown_extra_raises(
    pyproject_metadata_extra,
    depsconfig,
):
    """An extra not in Provides-Extra is a loud error (skips in candidates)."""
    srcname = "check"
    collector = "metadata_extra"
    extra = "bar"
    unknown = "nope"
    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [unknown]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata_extra(extra, reqs=(f"baz; extra == '{extra}'",))

    expected_err = "^" + re.escape(
        f"{collector}: extra '{unknown}' not provided by project "
        f"(available: {extra})",
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    # config unchanged on failure
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_extra_requires_exactly_one_arg(depsconfig):
    """Zero srcargs is a config error caught by validate_collector."""
    collector = "metadata_extra"
    input_conf = {"sources": {"check": {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(DepsSourcesConfigError):
        deps_command("sync", depsconfig_path, srcnames=[])

    # config unchanged on failure
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_extra_rejects_too_many_args(depsconfig):
    """More than one srcarg is a config error caught by validate_collector."""
    collector = "metadata_extra"
    input_conf = {
        "sources": {
            "check": {"srctype": collector, "srcargs": ["bar", "baz"]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(DepsSourcesConfigError):
        deps_command("sync", depsconfig_path, srcnames=[])

    # config unchanged on failure
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_extra_invalid_dep_raises(
    pyproject_metadata_extra,
    depsconfig,
):
    """A malformed Requires-Dist raises under the metadata_extra name."""
    srcname = "check"
    collector = "metadata_extra"
    extra = "bar"
    invalid_dep = "_foo"
    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [extra]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata_extra(extra, reqs=(invalid_dep,))

    # depends on packaging error message
    expected_err = (
        f"^{collector}: invalid core metadata: .* "
        "is invalid for 'requires-dist'"
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    # config unchanged on failure
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_extra_no_provided_extras(pyproject_metadata, depsconfig):
    """With no Provides-Extra the error's available list is empty."""
    srcname = "check"
    collector = "metadata_extra"
    extra = "bar"
    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [extra]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    # default headers carry no Provides-Extra
    pyproject_metadata(reqs=())

    expected_err = "^" + re.escape(
        f"{collector}: extra '{extra}' not provided by project "
        "(available: )",
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    # config unchanged on failure
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_extra_extra_with_no_deps(
    pyproject_metadata_extra,
    depsconfig,
):
    """A provided extra with no Requires-Dist stores no deps."""
    srcname = "check"
    collector = "metadata_extra"
    extra = "bar"
    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [extra]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata_extra(extra, reqs=())

    deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_extra_prefers_cache_over_build(
    pyproject_metadata_extra,
    depsconfig,
):
    """metadata_extra reads dist/metadata_cache instead of building."""
    srcname = "check"
    extra = "tests"
    input_conf = {
        "sources": {
            srcname: {"srctype": "metadata_extra", "srcargs": [extra]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    # the build would yield from-build; the cache must win
    pyproject_metadata_extra(extra, reqs=("from-build",))

    cache_path = Path.cwd() / "dist" / "metadata_cache"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        "Metadata-Version: 2.1\nName: foo\nVersion: 1.0\n"
        f"Provides-Extra: {extra}\nRequires-Dist: from-cache\n",
        encoding="utf-8",
    )

    deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = ["from-cache"]
    assert actual_conf == expected_conf


def test_metadata_extra_shares_cache_with_metadata(
    pyproject_metadata_extra,
    depsconfig,
    mocker,
):
    """A metadata and a metadata_extra source share one build."""
    extra = "tests"
    input_conf: dict[str, Any] = {
        "sources": {
            "runtime": {"srctype": "metadata"},
            "check": {"srctype": "metadata_extra", "srcargs": [extra]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata_extra(extra, reqs=("bar",))

    spy = mocker.spy(metadata_collector, "build_metadata")

    deps_command("sync", depsconfig_path, srcnames=[])

    assert spy.call_count == 1
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"]["runtime"]["deps"] = ["bar"]
    expected_conf["sources"]["check"]["deps"] = ["bar"]
    assert actual_conf == expected_conf

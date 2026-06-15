import json
import re
from copy import deepcopy

import pytest

from pyproject_installer.deps_cmd import deps_command
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


def test_metadata_extra_normalizes_extra(
    pyproject_metadata_extra,
    depsconfig,
):
    """The requested extra is matched PEP 503/685-normalized."""
    srcname = "check"
    collector = "metadata_extra"
    extra = "bar"
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [extra.capitalize()],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_metadata_extra(extra, reqs=(f"baz; extra == '{extra}'",))

    deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = [f'baz; extra == "{extra}"']
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

    expected_err = "^" + re.escape(
        f"{collector}: invalid PEP508 Dependency Specifier: {invalid_dep}",
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

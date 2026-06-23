import json
import re
from copy import deepcopy

import pytest

from pyproject_installer.deps_cmd import deps_command
from pyproject_installer.errors import (
    DepsNoCandidateError,
    DepsSourcesConfigError,
    DepsUnsyncedError,
)


def test_config_add_new_config(depsconfig_path):
    """Add new source to nonexistent config"""

    action = "add"
    srcname = "foo"
    srctype = "metadata"
    assert not depsconfig_path.exists()
    deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)
    config_data = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_data = {"sources": {"foo": {"srctype": srctype}}}
    assert config_data == expected_data


def test_config_add_new_source(depsconfig):
    """Add new source to existent config"""

    action = "add"
    srcname = "bar"
    srctype = "metadata"
    depsconfig_path = depsconfig()

    deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)

    config_data = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_data = {
        "sources": {"foo": {"srctype": srctype}, "bar": {"srctype": srctype}},
    }
    assert config_data == expected_data


def test_config_add_existent_source(depsconfig):
    """Add already existent source"""

    action = "add"
    srcname = "foo"
    srctype = "metadata"
    depsconfig_path = depsconfig()

    expected_err = re.escape(f"Source {srcname} already exists")
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)


def test_config_add_wrong_srctype(depsconfig_path):
    """Add new source with wrong srctype"""

    action = "add"
    srcname = "foo"
    srctype = "foo"

    expected_err = re.escape(f"Unsupported collector type: {srctype}")
    expected_err = f"^{expected_err}"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)


def test_config_add_missing_srcargs(depsconfig_path):
    """Add new source with missing required srcargs"""

    action = "add"
    srcname = "foo"
    srctype = "pip_reqfile"

    expected_err = re.escape(f"Unsupported arguments of collector {srctype}:")
    expected_err = f"^{expected_err}"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)


def test_config_add_extra_srcargs(depsconfig_path):
    """Add new source with extra srcargs"""

    action = "add"
    srcname = "foo"
    srctype = "metadata"

    expected_err = re.escape(f"Unsupported arguments of collector {srctype}:")
    expected_err = f"^{expected_err}"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            srctype=srctype,
            srcargs=["fooarg"],
        )


def test_config_add_srcargs(depsconfig_path):
    """Add new source with srcargs"""

    action = "add"
    srcname = "foo"
    srctype = "pip_reqfile"
    srcargs = ["requirements.txt"]

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        srctype=srctype,
        srcargs=srcargs,
    )
    config_data = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_data = {
        "sources": {"foo": {"srctype": srctype, "srcargs": srcargs}},
    }
    assert config_data == expected_data


def test_config_add_reconfigure_new(depsconfig_path):
    """reconfigure=True adds a not-yet-configured source (same as plain add)."""

    action = "add"
    srcname = "foo"
    srctype = "metadata"

    assert not depsconfig_path.exists()
    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        srctype=srctype,
        reconfigure=True,
    )
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {"sources": {srcname: {"srctype": srctype}}}
    assert actual_conf == expected_conf


def test_config_add_reconfigure_same_keeps_deps(depsconfig):
    """reconfigure with identical type+args is a no-op and keeps stored deps."""

    action = "add"
    srcname = "foo"
    srctype = "pip_reqfile"
    srcargs = ["r.txt"]

    input_conf = {
        "sources": {
            srcname: {"srctype": srctype, "srcargs": srcargs, "deps": ["bar"]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        srctype=srctype,
        srcargs=srcargs,
        reconfigure=True,
    )
    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_reconfigure_differ_args_drops_deps(depsconfig):
    """reconfigure with different args replaces the source, drops its deps."""

    action = "add"
    srcname = "foo"
    srctype = "pip_reqfile"
    srcargs = ["other.txt"]

    input_conf = {
        "sources": {
            srcname: {
                "srctype": srctype,
                "srcargs": ["r.txt"],
                "deps": ["bar"],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        srctype=srctype,
        srcargs=srcargs,
        reconfigure=True,
    )
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["srcargs"] = srcargs
    del expected_conf["sources"][srcname]["deps"]
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_reconfigure_differ_type_drops_deps(depsconfig):
    """reconfigure with different type replaces the source, drops its deps."""

    action = "add"
    srcname = "foo"
    srctype = "pip_reqfile"
    srcargs = ["other.txt"]

    input_conf = {
        "sources": {
            srcname: {
                "srctype": "tox",
                "srcargs": ["tox.ini", "testenv"],
                "deps": ["bar"],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        srctype=srctype,
        srcargs=srcargs,
        reconfigure=True,
    )
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["srctype"] = srctype
    expected_conf["sources"][srcname]["srcargs"] = srcargs
    del expected_conf["sources"][srcname]["deps"]
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_sync(depsconfig_path, mock_collector):
    """add(sync=True) configures the source then syncs it (collects deps)."""

    action = "add"
    srcname = "foo"
    srctype = "mock_collector"
    new_reqs = ["bar", "baz"]

    mock_collector(new_reqs)
    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        srctype=srctype,
        sync=True,
    )
    expected_conf = {
        "sources": {srcname: {"srctype": srctype, "deps": new_reqs}},
    }
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_reconfigure_keep_sync(depsconfig, mock_collector):
    """reconfigure-keep with sync=True still syncs (no early return)."""

    action = "add"
    srcname = "foo"
    srctype = "mock_collector"
    old_reqs = ["old"]
    new_reqs = ["new"]

    input_conf = {
        "sources": {srcname: {"srctype": srctype, "deps": old_reqs}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)
    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        srctype=srctype,
        reconfigure=True,
        sync=True,
    )
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = new_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_sync_skipped_when_add_fails(depsconfig):
    """add(sync=True) must not sync when the add itself fails."""

    action = "add"
    srcname = "foo"
    srctype = "metadata"
    old_reqs = ["bar"]

    input_conf = {
        "sources": {srcname: {"srctype": srctype, "deps": old_reqs}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError, match=rf"^Source {srcname} already exists"):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            srctype=srctype,
            sync=True,
        )

    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_sync_verify_drift(depsconfig_path, mock_collector):
    """add(sync=True, verify=True) raises DepsUnsyncedError on drift."""

    action = "add"
    srcname = "foo"
    srctype = "mock_collector"
    new_reqs = ["bar"]

    mock_collector(new_reqs)
    with pytest.raises(DepsUnsyncedError):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            srctype=srctype,
            sync=True,
            verify=True,
        )
    expected_conf = {
        "sources": {srcname: {"srctype": srctype, "deps": new_reqs}},
    }
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_candidates_first_existing_wins(
    depsconfig_path,
    pep735_deps,
):
    """First candidate whose collector resolves is recorded; missing skipped."""

    action = "add"
    srcname = "check"
    srctype = "pep735"
    srcargs = ["tests"]
    candidates = (
        (srctype, "test"),  # missing group -> skipped
        (srctype, "tests"),  # present -> picked
        ("pip_reqfile", "test-requirements.txt"),  # not reached
    )

    pep735_deps({"tests": ['"bar"']})

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        candidates=candidates,
    )
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {srcname: {"srctype": srctype, "srcargs": srcargs}},
    }
    assert actual_conf == expected_conf


def test_config_add_candidates_zero_deps_still_wins(
    depsconfig_path,
    pep735_deps,
):
    """A candidate that resolves to zero dependencies still wins."""

    action = "add"
    srcname = "check"
    srctype = "pep735"
    srcargs = ["test"]
    candidates = ((srctype, "test"), (srctype, "tests"))

    pep735_deps({"test": []})

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        candidates=candidates,
    )
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {srcname: {"srctype": srctype, "srcargs": srcargs}},
    }
    assert actual_conf == expected_conf


def test_config_add_candidates_unknown_type_errors(
    depsconfig_path,
    pip_reqfile,
):
    """An unknown candidate type is a malformed list -> error, not a skip."""

    action = "add"
    srcname = "check"
    srctype = "nonsense"

    # a later candidate would be picked, but the bad entry must error first
    reqfile_path = pip_reqfile("bar\n")
    candidates = ((srctype, "x"), ("pip_reqfile", str(reqfile_path)))

    expected_err = re.escape(f"Unsupported collector type: {srctype}")
    expected_err = f"^{expected_err}"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            candidates=candidates,
        )
    assert not depsconfig_path.exists()


def test_config_add_candidates_wrong_args_errors(
    depsconfig_path,
    pip_reqfile,
):
    """A candidate with the wrong number of args -> error, not a skip."""

    action = "add"
    srcname = "check"
    srctype = "pip_reqfile"

    # a later candidate would be picked, but the bad entry must error first
    reqfile_path = pip_reqfile("bar\n")
    candidates = ((srctype,), (srctype, str(reqfile_path)))

    expected_err = re.escape(f"Unsupported arguments of collector {srctype}:")
    expected_err = f"^{expected_err}"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            candidates=candidates,
        )
    assert not depsconfig_path.exists()


def test_config_add_candidates_validated_before_walk(
    depsconfig_path,
    pep735_deps,
):
    """A malformed entry after a would-be pick still errors (up-front)."""

    action = "add"
    srcname = "check"
    srctype = "nonsense"

    # the first candidate would be picked, but the whole list is validated
    # before the walk, so the malformed entry behind it must error
    pep735_deps({"test": ['"bar"']})
    candidates = (("pep735", "test"), (srctype, "x"))

    expected_err = re.escape(f"Unsupported collector type: {srctype}")
    expected_err = f"^{expected_err}"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            candidates=candidates,
        )
    assert not depsconfig_path.exists()


def test_config_add_candidates_uncollectable_is_skipped(
    depsconfig_path,
    pep735_deps,
):
    """A present but uncollectable source is skipped, like an absent one."""

    action = "add"
    srcname = "check"
    srctype = "pep735"
    srcargs = ["tests"]
    candidates = ((srctype, "test"), (srctype, "tests"))

    # the 'test' group exists but has an invalid PEP 508 requirement, so it
    # cannot be collected; the walk moves on to the collectable 'tests'.
    pep735_deps({"test": ['"foo !!> 1.0"'], "tests": ['"bar"']})

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        candidates=candidates,
    )
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {srcname: {"srctype": srctype, "srcargs": srcargs}},
    }
    assert actual_conf == expected_conf


def test_config_add_candidates_metadata_extra_unknown_skipped(
    depsconfig_path,
    pyproject_metadata_extra,
):
    """A metadata_extra whose extra is undeclared is skipped; next wins.

    Exercises the feature's headline discovery path: an unknown extra
    makes the collector raise, so the candidate walk moves on to the
    declared extra.
    """

    action = "add"
    srcname = "check"
    collector = "metadata_extra"
    extra = "bar"
    unknown = "nope"
    candidates = (
        (collector, unknown),  # extra not provided -> skipped
        (collector, extra),  # provided -> picked
    )

    pyproject_metadata_extra(extra, reqs=(f"baz; extra == '{extra}'",))

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        candidates=candidates,
    )
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [extra]},
        },
    }
    assert actual_conf == expected_conf


def test_config_add_candidates_no_candidate_unconfigured_errors(
    depsconfig_path,
):
    """No candidate matches and name not configured: error, no file written."""

    action = "add"
    srcname = "check"
    candidates = (("pep735", "test"), ("pip_reqfile", "r.txt"))

    # no pyproject.toml, no r.txt -> nothing collects
    assert not depsconfig_path.exists()
    expected_err = rf"^No candidate source matched for {srcname}"
    with pytest.raises(DepsNoCandidateError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            candidates=candidates,
        )
    assert not depsconfig_path.exists()


def test_config_add_candidates_existing_without_reconfigure_errors(
    depsconfig,
    pep735_deps,
):
    """A pick under an already-configured name without reconfigure errors."""

    action = "add"
    srcname = "check"
    candidates = (("pep735", "test"),)

    pep735_deps({"test": ['"bar"']})
    input_conf = {"sources": {srcname: {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError, match=rf"^Source {srcname} already exists"):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            candidates=candidates,
        )
    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_candidates_reconfigure_same_keeps_deps(
    depsconfig,
    pep735_deps,
):
    """reconfigure: a pick equal to the configured source keeps deps."""

    action = "add"
    srcname = "check"
    srctype = "pep735"
    srcargs = ["test"]
    candidates = ((srctype, "test"),)

    pep735_deps({"test": ['"bar"']})
    input_conf = {
        "sources": {
            srcname: {"srctype": srctype, "srcargs": srcargs, "deps": ["bar"]},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        candidates=candidates,
        reconfigure=True,
    )
    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_candidates_reconfigure_differ_replaces(
    depsconfig,
    pep735_deps,
):
    """reconfigure: a differing pick replaces the configured source."""

    action = "add"
    srcname = "check"
    srctype = "pep735"
    srcargs = ["tests"]
    candidates = ((srctype, "test"), (srctype, "tests"))

    pep735_deps({"tests": ['"bar"']})
    input_conf = {
        "sources": {
            srcname: {
                "srctype": srctype,
                "srcargs": ["test"],
                "deps": ["bar"],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        candidates=candidates,
        reconfigure=True,
    )
    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["srcargs"] = srcargs
    del expected_conf["sources"][srcname]["deps"]
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize("reconfigure", (False, True))
def test_config_add_candidates_no_candidate_configured_errors(
    depsconfig,
    reconfigure,
):
    """No candidate matches and name configured: error, source untouched
    (with or without reconfigure)."""

    action = "add"
    srcname = "check"
    candidates = (("pep735", "test"), ("pip_reqfile", "r.txt"))

    # no pyproject.toml / r.txt -> nothing collects
    input_conf = {
        "sources": {
            srcname: {
                "srctype": "pep735",
                "srcargs": ["test"],
                "deps": ["bar"],
            },
            "other": {"srctype": "metadata"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = rf"^No candidate source matched for {srcname}"
    with pytest.raises(DepsNoCandidateError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            candidates=candidates,
            reconfigure=reconfigure,
        )
    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_add_candidates_sync_collects_picked(
    depsconfig_path,
    pip_reqfile,
):
    """candidates with sync=True records and syncs the picked source's deps."""

    action = "add"
    srcname = "check"
    srctype = "pip_reqfile"
    new_reqs = ["bar", "baz"]

    reqfile_path = pip_reqfile("\n".join(new_reqs) + "\n")
    srcargs = [str(reqfile_path)]
    candidates = ((srctype, "missing.txt"), (srctype, str(reqfile_path)))

    deps_command(
        action,
        depsconfig_path,
        srcname=srcname,
        candidates=candidates,
        sync=True,
    )
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            srcname: {
                "srctype": srctype,
                "srcargs": srcargs,
                "deps": new_reqs,
            },
        },
    }
    assert actual_conf == expected_conf


def test_config_add_candidates_sync_verify_drift(
    depsconfig_path,
    pip_reqfile,
):
    """candidates with sync=True, verify=True raises on drift.

    A freshly discovered source has no stored deps, so its first
    verify drifts, exactly as with an explicit srctype.
    """

    action = "add"
    srcname = "check"
    srctype = "pip_reqfile"
    new_reqs = ["bar"]

    reqfile_path = pip_reqfile("\n".join(new_reqs) + "\n")
    srcargs = [str(reqfile_path)]
    candidates = ((srctype, "missing.txt"), (srctype, str(reqfile_path)))

    with pytest.raises(DepsUnsyncedError):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            candidates=candidates,
            sync=True,
            verify=True,
        )
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            srcname: {
                "srctype": srctype,
                "srcargs": srcargs,
                "deps": new_reqs,
            },
        },
    }
    assert actual_conf == expected_conf


def test_config_add_requires_srctype_or_candidates(depsconfig_path):
    """add() with neither a srctype nor candidates is an error."""

    action = "add"
    srcname = "foo"

    expected_err = r"^add requires either srctype or candidates"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(action, depsconfig_path, srcname=srcname)
    assert not depsconfig_path.exists()


def test_config_add_candidates_with_srctype_errors(
    depsconfig_path,
    pep735_deps,
):
    """add() with both a srctype and candidates is an error."""

    action = "add"
    srcname = "foo"
    srctype = "metadata"
    candidates = (("pep735", "test"),)

    pep735_deps({"test": ['"bar"']})

    expected_err = r"^srctype is mutually exclusive with candidates"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            srctype=srctype,
            candidates=candidates,
        )
    assert not depsconfig_path.exists()


def test_config_add_sources_batch(depsconfig_path):
    """add(sources=...) configures every entry, in list order."""

    action = "add"
    sources = (("foo", "metadata"), ("bar", "pip_reqfile", "r.txt"))

    deps_command(action, depsconfig_path, sources=sources)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            "foo": {"srctype": "metadata"},
            "bar": {"srctype": "pip_reqfile", "srcargs": ["r.txt"]},
        },
    }
    assert actual_conf == expected_conf


def test_config_add_sources_with_srcname_errors(depsconfig_path):
    """sources is mutually exclusive with a positional srcname."""

    expected_err = (
        r"^sources is mutually exclusive with single source configuration "
        r"or candidates$"
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command(
            "add",
            depsconfig_path,
            srcname="foo",
            sources=(("bar", "metadata"),),
        )
    assert not depsconfig_path.exists()


def test_config_add_sources_with_candidates_errors(depsconfig_path):
    """sources is mutually exclusive with candidates."""

    expected_err = (
        r"^sources is mutually exclusive with single source configuration "
        r"or candidates$"
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command(
            "add",
            depsconfig_path,
            candidates=(("pep735", "test"),),
            sources=(("bar", "metadata"),),
        )
    assert not depsconfig_path.exists()


def test_config_add_sources_sync(depsconfig_path, mock_collector):
    """sources with sync=True configures and syncs every entry."""

    new_reqs = ["bar"]
    sources = (("foo", "mock_collector"), ("baz", "mock_collector"))

    mock_collector(new_reqs)
    deps_command("add", depsconfig_path, sources=sources, sync=True)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            "foo": {"srctype": "mock_collector", "deps": new_reqs},
            "baz": {"srctype": "mock_collector", "deps": new_reqs},
        },
    }
    assert actual_conf == expected_conf


def test_config_add_sources_sync_verify_fail_fast(
    depsconfig_path,
    mock_collector,
):
    """verify stops at the first out-of-sync entry; later ones untouched.

    Both entries are freshly added (no stored deps), so the first verify
    is out of sync and raises -- the second entry is never configured.
    """

    new_reqs = ["bar"]
    sources = (("foo", "mock_collector"), ("baz", "mock_collector"))

    mock_collector(new_reqs)
    with pytest.raises(DepsUnsyncedError):
        deps_command(
            "add",
            depsconfig_path,
            sources=sources,
            sync=True,
            verify=True,
        )

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {"foo": {"srctype": "mock_collector", "deps": new_reqs}},
    }
    assert actual_conf == expected_conf


def test_config_add_sources_verify_keeps_earlier_skips_later(
    depsconfig,
    mock_collector,
):
    """A later out-of-sync entry stops the run: an earlier in-sync entry
    stays configured, the out-of-sync entry is configured and synced, and the
    entry after it is never reached.

    'a' is already configured with deps that match what the collector
    yields, so its verify passes; 'b' is fresh and is out of sync.
    """

    reqs = ["bar"]
    input_conf = {
        "sources": {"a": {"srctype": "mock_collector", "deps": reqs}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))
    sources = (
        ("a", "mock_collector"),
        ("b", "mock_collector"),
        ("c", "mock_collector"),
    )

    mock_collector(reqs)
    with pytest.raises(DepsUnsyncedError):
        deps_command(
            "add",
            depsconfig_path,
            sources=sources,
            reconfigure=True,
            sync=True,
            verify=True,
        )

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            "a": {"srctype": "mock_collector", "deps": reqs},
            "b": {"srctype": "mock_collector", "deps": reqs},
        },
    }
    assert actual_conf == expected_conf


def test_config_add_sources_existing_without_reconfigure_stops(depsconfig):
    """An existing name without reconfigure stops the run; earlier entries
    are already written (partial), exactly as a per-entry add would do."""

    input_conf = {
        "sources": {"foo": {"srctype": "metadata", "deps": ["old_req"]}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))
    sources = (("bar", "metadata"), ("foo", "metadata"))

    with pytest.raises(ValueError, match=r"^Source foo already exists"):
        deps_command("add", depsconfig_path, sources=sources)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            "foo": {"srctype": "metadata", "deps": ["old_req"]},
            "bar": {"srctype": "metadata"},
        },
    }
    assert actual_conf == expected_conf


def test_config_add_sources_reconfigure_replaces(depsconfig):
    """reconfigure applies per entry: a differing entry is replaced."""

    input_conf = {
        "sources": {"foo": {"srctype": "metadata", "deps": ["old"]}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))
    sources = (("foo", "pip_reqfile", "r.txt"),)

    deps_command("add", depsconfig_path, sources=sources, reconfigure=True)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {"foo": {"srctype": "pip_reqfile", "srcargs": ["r.txt"]}},
    }
    assert actual_conf == expected_conf


def test_config_add_sources_bad_args_stops(depsconfig_path):
    """A wrong argument count is checked per entry when it is configured;
    earlier entries are already written."""

    sources = (("foo", "metadata"), ("bar", "pip_reqfile"))

    expected_err = r"^Unsupported arguments of collector pip_reqfile"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command("add", depsconfig_path, sources=sources)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    assert actual_conf == expected_conf


def test_config_add_sources_sync_collect_failure_stops(
    depsconfig_path,
    pip_reqfile,
):
    """A source that cannot be collected fails at its sync step and stops the
    run: the earlier entry is synced, the failing entry stays configured with
    no deps, and the entry after it is never reached."""

    reqfile = pip_reqfile("bar\n")
    sources = (
        ("a", "pip_reqfile", str(reqfile)),
        ("b", "pip_reqfile", "missing.txt"),
        ("c", "metadata"),
    )

    with pytest.raises(FileNotFoundError):
        deps_command("add", depsconfig_path, sources=sources, sync=True)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_conf = {
        "sources": {
            "a": {
                "srctype": "pip_reqfile",
                "srcargs": [str(reqfile)],
                "deps": ["bar"],
            },
            "b": {"srctype": "pip_reqfile", "srcargs": ["missing.txt"]},
        },
    }
    assert actual_conf == expected_conf


@pytest.mark.parametrize(
    "extra_kwargs",
    ({"srctype": "metadata"}, {"srcargs": ("x",)}),
    ids=("srctype", "srcargs"),
)
def test_config_add_sources_with_single_source_args_errors(
    depsconfig_path,
    extra_kwargs,
):
    """sources cannot be combined with srctype or srcargs either."""

    expected_err = (
        r"^sources is mutually exclusive with single source configuration "
        r"or candidates$"
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command(
            "add",
            depsconfig_path,
            sources=(("bar", "metadata"),),
            **extra_kwargs,
        )
    assert not depsconfig_path.exists()


def test_config_add_requires_srcname_or_sources(depsconfig_path):
    """add() with neither a srcname nor sources is an error."""

    expected_err = (
        r"^source name is required with --candidates or single source "
        r"configuration"
    )
    with pytest.raises(ValueError, match=expected_err):
        deps_command("add", depsconfig_path)
    assert not depsconfig_path.exists()

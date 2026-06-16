import json
import re
from copy import deepcopy
from typing import Any

import pytest

from pyproject_installer.deps_cmd import deps_command
from pyproject_installer.errors import DepsSourcesConfigError, DepsUnsyncedError

NONEXISTENT_SOURCE_DATA = (
    (["bar"], "Nonexistent sources: bar"),
    (["foo", "bar"], "Nonexistent sources: bar"),
    (["bar", "foo"], "Nonexistent sources: bar"),
    (["foobar", "bar"], "Nonexistent sources: foobar, bar"),
    (["foo", "foobar", "bar"], "Nonexistent sources: foobar, bar"),
)


@pytest.mark.parametrize(
    "config_data",
    (
        ("", "Invalid config file: "),
        ("[]", "Config should be dict, given: []"),
        ("{}", "Missing 'sources' field in config"),
        ('{"foo": ""}', "Missing 'sources' field in config"),
        ('{"sources": ""}', "'sources' field should be dict, given: ''"),
        ('{"sources": []}', "'sources' field should be dict, given: []"),
        (
            '{"sources": {"foo": ""}}',
            "Source definition should be dict, given: ''",
        ),
        (
            '{"sources": {"foo": []}}',
            "Source definition should be dict, given: []",
        ),
        (
            '{"sources": {"foo": {}}}',
            "Missing 'srctype' field in source definition",
        ),
        (
            '{"sources": {"foo": {"bar": ""}}}',
            "Missing 'srctype' field in source definition",
        ),
        (
            '{"sources": {"foo": {"srctype": "bar"}}}',
            "Unsupported collector type: bar",
        ),
        (
            '{"sources": {"foo": {"srctype": "metadata", "srcargs": "bar"}}}',
            "Unsupported arguments of collector metadata: ",
        ),
        (
            '{"sources": {"foo": {"srctype": "metadata", "deps": ["foo!"]}}}',
            "Invalid stored PEP508 requirement: foo!",
        ),
        (
            (
                '{"sources": {"foo": {"srctype": "metadata", '
                '"deps": ["bar", "foo !!> 1.0"]'
                "}}}"
            ),
            "Invalid stored PEP508 requirement: foo !!> 1.0",
        ),
        (
            (
                '{"sources": {"foo": {"srctype": "metadata", '
                '"deps": ["foo", "foo;invalid_marker >= \'1.0\'"]'
                "}}}"
            ),
            "Invalid stored PEP508 requirement: foo;invalid_marker >= '1.0'",
        ),
        (
            (
                '{"sources": {"foo": {"srctype": "metadata", '
                '"deps": [""]'
                "}}}"
            ),
            "Invalid stored PEP508 requirement: ",
        ),
    ),
)
def test_config_read_invalid(config_data, depsconfig_path):
    """Read invalid config"""

    action = "show"
    data, expected_err = config_data

    depsconfig_path.write_text(data, encoding="utf-8")
    expected_err = f"^{re.escape(expected_err)}"
    with pytest.raises(DepsSourcesConfigError, match=expected_err):
        deps_command(action, depsconfig_path)


def test_config_delete(depsconfig):
    """Delete source"""

    action = "delete"
    srcname = "foo"
    depsconfig_path = depsconfig()

    deps_command(action, depsconfig_path, srcname=srcname)
    config_data = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_data: dict[str, Any] = {"sources": {}}
    assert config_data == expected_data


def test_config_delete_nonexistent_source(depsconfig):
    """Delete nonexistent source"""

    action = "delete"
    srcname = "bar"
    depsconfig_path = depsconfig()

    expected_err = re.escape(f"Source {srcname} doesn't exist")
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(action, depsconfig_path, srcname=srcname)


@pytest.mark.parametrize(
    "select_data",
    (
        ([], ["bar", "foo", "foobar"]),
        (["foo"], ["foo"]),
        (["bar", "foo"], ["bar", "foo"]),
        (["foo", "bar"], ["bar", "foo"]),
        (["foobar"], ["foobar"]),
    ),
)
def test_config_show(select_data, depsconfig, capsys):
    """Show selected source"""

    action = "show"
    select, selected = select_data

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {"srctype": "metadata"},
            "bar": {"srctype": "metadata"},
            "foobar": {"srctype": "metadata"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=select)

    out_conf: dict[str, Any] = {"sources": {}}
    for srcname in selected:
        out_conf["sources"][srcname] = input_conf["sources"][srcname]
    expected_out = json.dumps(out_conf, indent=2) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out

    # make sure the config was not modified
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize("select_data", NONEXISTENT_SOURCE_DATA)
def test_config_show_nonexistent_source(select_data, depsconfig, capsys):
    """Show nonexistent source"""

    action = "show"
    select, expected_err = select_data

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(action, depsconfig_path, srcnames=select)

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


def test_config_show_empty(depsconfig, capsys):
    """Show empty"""

    action = "show"

    # prepare source config
    input_conf: dict[str, Any] = {"sources": {}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[])

    output_conf: dict[str, Any] = {"sources": {}}
    expected_out = json.dumps(output_conf, indent=2) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


def test_config_sync_empty(depsconfig, capsys):
    """Sync empty"""

    action = "sync"

    # prepare source config
    input_conf: dict[str, Any] = {"sources": {}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[])

    output_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert output_conf == input_conf

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "select_data",
    (
        ([], ["bar", "foo", "foobar"]),
        (["foo"], ["foo"]),
        (["bar", "foo"], ["bar", "foo"]),
        (["foo", "bar"], ["foo", "bar"]),
        (["foobar"], ["foobar"]),
    ),
)
def test_config_sync_selected(select_data, depsconfig, mock_collector, capsys):
    """Sync changed selected source"""

    action = "sync"
    select, synced = select_data

    # prepare source config
    input_conf: dict[str, Any] = {
        "sources": {
            "foo": {"srctype": "mock_collector"},
            "bar": {"srctype": "mock_collector"},
            "foobar": {"srctype": "mock_collector"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    reqs = ["foo", "bar"]
    mock_collector(reqs)

    deps_command(action, depsconfig_path, srcnames=select)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))

    expected_conf = deepcopy(input_conf)
    for srcname in synced:
        expected_conf["sources"][srcname]["deps"] = sorted(reqs)
    assert actual_conf == expected_conf

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "data",
    (
        (["foo", "bar"], [], {"foo": {"extra_deps": ["bar", "foo"]}}),
        ([], ["foo", "bar"], {"foo": {"new_deps": ["bar", "foo"]}}),
        (
            ["foo"],
            ["bar", "foobar"],
            {"foo": {"extra_deps": ["foo"], "new_deps": ["bar", "foobar"]}},
        ),
        (
            ["foo", "foo1"],
            ["bar", "foobar", "foo1"],
            {"foo": {"extra_deps": ["foo"], "new_deps": ["bar", "foobar"]}},
        ),
    ),
)
def test_config_sync_verify_changed(data, depsconfig, mock_collector, capsys):
    """Sync changed source with verify"""

    action = "sync"
    old_reqs, new_reqs, diff = data

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {
                "srctype": "mock_collector",
                "deps": old_reqs,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)

    with pytest.raises(DepsUnsyncedError):
        deps_command(action, depsconfig_path, srcnames=[], verify=True)

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"]["foo"]["deps"] = sorted(new_reqs)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

    expected_out = json.dumps(diff, indent=2) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


@pytest.mark.parametrize(
    "select",
    ([], ["foo"], ["bar", "foo"], ["foo", "bar"], ["foobar"]),
)
def test_config_sync_verify_unchanged(
    select,
    depsconfig,
    mock_collector,
    capsys,
):
    """Sync unchanged selected source with verify"""

    action = "sync"

    # prepare source config
    reqs = ["foo", "bar"]
    input_conf = {
        "sources": {
            "foo": {"srctype": "mock_collector", "deps": sorted(reqs)},
            "bar": {"srctype": "mock_collector", "deps": sorted(reqs)},
            "foobar": {"srctype": "mock_collector", "deps": sorted(reqs)},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(reqs)

    deps_command(action, depsconfig_path, srcnames=select, verify=True)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == deepcopy(input_conf)

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "old_reqs,new_reqs",
    (
        (["foo"], ["foo "]),
        (["foo[a,b]"], ["foo [ a, b ]"]),
        (["foo>1"], ["foo > 1"]),
        (["foo;python_version=='3'"], ["foo ; python_version == '3'"]),
    ),
)
def test_config_sync_verify_normalized_dep(
    old_reqs,
    new_reqs,
    depsconfig,
    mock_collector,
    capsys,
):
    """Sync unchanged source with verify and dependency normalization"""

    action = "sync"

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {
                "srctype": "mock_collector",
                "deps": old_reqs,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)

    deps_command(action, depsconfig_path, srcnames=[], verify=True)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "data",
    # original reqs, updated reqs, filter, expected diff
    (
        (
            ["foo", "bar", "foobar"],
            [],
            ["foob.*"],
            {"extra_deps": ["bar", "foo"]},
        ),
        (
            ["foo", "bar", "foobar"],
            [],
            ["foofoo.*", "barbar.*"],
            {"extra_deps": ["bar", "foo", "foobar"]},
        ),
        (
            [],
            ["foo", "bar", "foobar"],
            ["foob.*"],
            {"new_deps": ["bar", "foo"]},
        ),
        (
            [],
            ["foo", "bar", "foobar"],
            ["foofoo.*", "barbar.*"],
            {"new_deps": ["bar", "foo", "foobar"]},
        ),
        (
            ["foo", "bar", "foobar"],
            ["foobar>=1"],
            ["foobar.*"],
            {"extra_deps": ["bar", "foo"]},
        ),
        (
            ["foo", "bar", "foobar >= 1"],
            ["foobar"],
            ["foobar.*"],
            {"extra_deps": ["bar", "foo"]},
        ),
        (
            ["foo", "ffoo"],
            ["bar", "bbar"],
            ["foo.*", "bar.*"],
            {"extra_deps": ["ffoo"], "new_deps": ["bbar"]},
        ),
        (
            ["fo_o", "BaR", "foobar"],
            ["bbarfoo"],
            ["fo-o.*", "bar.*"],
            {"extra_deps": ["foobar"], "new_deps": ["bbarfoo"]},
        ),
    ),
)
def test_config_sync_verify_exclude_changed(
    data,
    depsconfig,
    mock_collector,
    capsys,
):
    """Sync source with verify and exclude, check config and diff of changes"""

    action = "sync"
    old_reqs, new_reqs, excludes, diff = data

    srcname = "src_foo"

    # prepare source config
    input_conf = {
        "sources": {
            srcname: {
                "srctype": "mock_collector",
                "deps": old_reqs,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)

    with pytest.raises(DepsUnsyncedError):
        deps_command(
            action,
            depsconfig_path,
            srcnames=[],
            verify=True,
            verify_excludes=excludes,
        )

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = sorted(new_reqs)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

    expected_out = json.dumps({srcname: diff}, indent=2) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


@pytest.mark.parametrize(
    "data",
    # original reqs, updated reqs, filter
    (
        (["foo", "bar", "foobar"], [], ["foo.*", "bar.*"]),
        ([], ["bar", "foo", "foobar"], ["foo.*", "bar.*"]),
        ([], [], ["foofoo.*", "barbar.*"]),
        ([], [], []),
        (["foo"], ["bar"], ["foo.*", "bar.*"]),
        (["foo", "bar"], ["foo", "bar"], ["foobar.*"]),
        (["fo_o", "BaR"], [], ["fo-o.*", "bar.*"]),
        (["fo_o"], ["Bar"], ["fo-o.*", "bar.*"]),
    ),
)
def test_config_sync_verify_exclude_unchanged(
    data,
    depsconfig,
    mock_collector,
    capsys,
):
    """
    Sync source with verify and exclude, check config and nodiff of changes
    """

    action = "sync"
    old_reqs, new_reqs, excludes = data

    srcname = "src_foo"

    # prepare source config
    input_conf = {
        "sources": {
            srcname: {
                "srctype": "mock_collector",
                "deps": old_reqs,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)

    deps_command(
        action,
        depsconfig_path,
        srcnames=[],
        verify=True,
        verify_excludes=excludes,
    )

    expected_conf = deepcopy(input_conf)
    # same order as it was before
    expected_conf["sources"][srcname]["deps"] = new_reqs

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


def test_config_sync_verify_exclude_without_verify(depsconfig, capsys):
    """Sync with --verify-exclude and without --verify"""

    action = "sync"

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = re.escape("verify_excludes must be used with verify")
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcnames=[],
            verify_excludes=["foo.*"],
        )

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "old_reqs,new_reqs",
    (
        # only the version specifier differs
        (["foo>=1"], ["foo>=2"]),
        (["foo<81,>=78.1.1"], ["foo<82,>=78.1.1"]),
        # extras and markers preserved, only version changes
        (["foo[a,b]>=1"], ["foo[a,b]>=2"]),
        (
            ['foo>=1; python_version < "3.11"'],
            ['foo>=2; python_version < "3.11"'],
        ),
        # several deps, all version-only
        (["foo>=1", "bar==1"], ["foo>=2", "bar==2"]),
        # gaining a specifier where there was none is still version-only
        (["foo"], ["foo>=1"]),
    ),
)
def test_config_sync_verify_ignore_version_unchanged(
    old_reqs,
    new_reqs,
    depsconfig,
    mock_collector,
    capsys,
):
    """Sync version-only changed source with verify and ignore-version

    Version-only changes don't appear in the diff and don't fail, but the
    config is still rewritten to the synced deps.
    """

    action = "sync"
    srcname = "src_foo"

    input_conf = {
        "sources": {
            srcname: {
                "srctype": "mock_collector",
                "deps": old_reqs,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)

    deps_command(
        action,
        depsconfig_path,
        srcnames=[],
        verify=True,
        verify_ignore_version=True,
    )

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = sorted(new_reqs)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "data",
    # original reqs, updated reqs, expected diff
    (
        # version-only foo suppressed, genuinely added dep surfaces
        (
            ["foo>=1"],
            ["foo>=2", "newdep>=1"],
            {"new_deps": ["newdep>=1"]},
        ),
        # version-only foo suppressed, genuinely removed dep surfaces
        (
            ["foo>=1", "gone==1"],
            ["foo>=2"],
            {"extra_deps": ["gone==1"]},
        ),
        # a change of extras is a real change, not a version change
        (
            ["foo[a]>=1"],
            ["foo[a,b]>=2"],
            {"extra_deps": ["foo[a]>=1"], "new_deps": ["foo[a,b]>=2"]},
        ),
        # a change of marker is a real change, not a version change
        (
            ['foo>=1; python_version < "3.11"'],
            ['foo>=2; python_version < "3.12"'],
            {
                "extra_deps": ['foo>=1; python_version < "3.11"'],
                "new_deps": ['foo>=2; python_version < "3.12"'],
            },
        ),
    ),
)
def test_config_sync_verify_ignore_version_changed(
    data,
    depsconfig,
    mock_collector,
    capsys,
):
    """Sync source with verify and ignore-version, real changes still fail"""

    action = "sync"
    old_reqs, new_reqs, diff = data
    srcname = "src_foo"

    input_conf = {
        "sources": {
            srcname: {
                "srctype": "mock_collector",
                "deps": old_reqs,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)

    with pytest.raises(DepsUnsyncedError):
        deps_command(
            action,
            depsconfig_path,
            srcnames=[],
            verify=True,
            verify_ignore_version=True,
        )

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = sorted(new_reqs)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

    expected_out = json.dumps({srcname: diff}, indent=2) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


def test_config_sync_verify_ignore_version_with_exclude(
    depsconfig,
    mock_collector,
    capsys,
):
    """ignore-version and exclude filters compose"""

    action = "sync"
    srcname = "src_foo"

    # foo: version-only (ignored), bar: removed but excluded, baz: added
    old_reqs = ["foo>=1", "bar==1"]
    new_reqs = ["foo>=2", "baz>=1"]

    input_conf = {
        "sources": {
            srcname: {
                "srctype": "mock_collector",
                "deps": old_reqs,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    mock_collector(new_reqs)

    with pytest.raises(DepsUnsyncedError):
        deps_command(
            action,
            depsconfig_path,
            srcnames=[],
            verify=True,
            verify_ignore_version=True,
            verify_excludes=["bar.*"],
        )

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = sorted(new_reqs)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

    diff = {srcname: {"new_deps": ["baz>=1"]}}
    expected_out = json.dumps(diff, indent=2) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


def test_config_sync_verify_ignore_version_without_verify(depsconfig, capsys):
    """Sync with ignore-version and without verify"""

    action = "sync"

    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = re.escape("verify_ignore_version must be used with verify")
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(
            action,
            depsconfig_path,
            srcnames=[],
            verify_ignore_version=True,
        )

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize("select_data", NONEXISTENT_SOURCE_DATA)
def test_config_sync_nonexistent_source(select_data, depsconfig, capsys):
    """Sync nonexistent source"""

    action = "sync"
    select, expected_err = select_data

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {"srctype": "metadata"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(action, depsconfig_path, srcnames=select)

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out

    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_config_eval_empty(depsconfig, capsys):
    """Eval empty"""

    action = "eval"

    # prepare source config
    input_conf: dict[str, Any] = {"sources": {}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[])

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out

    output_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert output_conf == input_conf


@pytest.mark.parametrize(
    "select_data",
    (
        ([], ["bar1", "bar2", "foo1", "foo2", "foobar1"]),
        (["foo"], ["foo1", "foo2"]),
        (["bar", "foo"], ["bar1", "bar2", "foo1", "foo2"]),
        (["foo", "bar"], ["bar1", "bar2", "foo1", "foo2"]),
        (["foobar"], ["bar2", "foo1", "foobar1"]),
    ),
)
def test_config_eval_select(select_data, depsconfig, capsys):
    """Eval selected source"""

    action = "eval"
    select, deps = select_data

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {"srctype": "metadata", "deps": ["foo1", "foo2"]},
            "bar": {"srctype": "metadata", "deps": ["bar1", "bar2"]},
            "foobar": {
                "srctype": "metadata",
                "deps": ["foo1", "bar2", "foobar1"],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=select)

    expected_out = "\n".join(deps) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


@pytest.mark.parametrize("select_data", NONEXISTENT_SOURCE_DATA)
def test_config_eval_nonexistent_source(select_data, depsconfig, capsys):
    """Eval nonexistent source"""

    action = "eval"
    select, expected_err = select_data

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {"srctype": "metadata"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(action, depsconfig_path, srcnames=select)

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out

    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize(
    "data",
    (
        (["project-foo"], "$nname", None, ["project-foo"]),
        (["Project-Foo"], "$nname", None, ["project-foo"]),
        (["PROJECT_FOO"], "$nname", None, ["project-foo"]),
        (["project.foo"], "$nname", None, ["project-foo"]),
        (["project_foo"], "$nname", None, ["project-foo"]),
        (["project--foo"], "$nname", None, ["project-foo"]),
        (["projecT_-.-_fOo"], "$nname", None, ["project-foo"]),
        (["Project-Foo"], "$name", None, ["Project-Foo"]),
        (["Project-Foo"], "python3-$nname", None, ["python3-project-foo"]),
        (["Project-Foo"], "python3-$name", None, ["python3-Project-Foo"]),
        (["foo [bar,foobar] >= 2.8.1, == 2.8.*"], "$name", None, ["foo"]),
        (["foo [bar]"], "$name", None, ["foo"]),
        (["foo == 1.0.0"], "$name", None, ["foo"]),
        (["project-foo"], "$name-$foo", None, ["project-foo-$foo"]),
        (["project-foo"], "$foo$bar", None, ["$foo$bar"]),
        (["project-foo"], "$fextra", None, []),
        (["project-foo [foo]"], "$fextra", None, []),
        (["project-foo [foo]"], "$fextra", "+$extra", ["+foo"]),
        (["project-foo [foo,bar]"], "$fextra", "+$extra", ["+bar", "+foo"]),
        (
            ["project-foo [foo,bar]"],
            "$fextra",
            "+$extra-$foo",
            ["+bar-$foo", "+foo-$foo"],
        ),
        (
            ["project-foo [foo,bar]", "project_bar"],
            "$nname$fextra",
            "+$extra",
            ["project-bar", "project-foo+bar", "project-foo+foo"],
        ),
        (
            ["project-foo [foo,bar]", "project_bar"],
            "$nname$fextra",
            None,
            ["project-bar", "project-foo"],
        ),
    ),
)
def test_config_eval_formatting(data, depsconfig, capsys):
    """Eval source and format names"""

    action = "eval"
    deps, depformat, depformatextra, out = data

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata", "deps": deps}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action,
        depsconfig_path,
        srcnames=[],
        depformat=depformat,
        depformatextra=depformatextra,
    )

    expected_out = "\n".join(out) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


def test_config_eval_formatting_depformatextra_only(depsconfig, capsys):
    """Eval with depformatextra only formatting"""

    action = "eval"

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = re.escape("depformatextra must be used with depformat")
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command(action, depsconfig_path, srcnames=[], depformatextra="foo")

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


@pytest.mark.parametrize(
    "data",
    (
        (["foo"], ["foo"]),
        (["foo [bar]"], ["foo[bar]"]),
        (["foo == 1.0.0"], ["foo==1.0.0"]),
        (
            ["foo [bar,foobar] >= 2.8.1, == 2.8.*"],
            ["foo[bar,foobar]==2.8.*,>=2.8.1"],
        ),
        (
            ["foo [bar,foobar] >= 2.8.1, == 2.8.* ; python_version > '2.7'"],
            ['foo[bar,foobar]==2.8.*,>=2.8.1; python_version > "2.7"'],
        ),
    ),
)
def test_config_eval_default(data, depsconfig, capsys):
    """Eval source and print in normalized(packaging) PEP508 format"""

    action = "eval"
    deps, out = data

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata", "deps": deps}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[])

    expected_out = "\n".join(out) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


@pytest.mark.parametrize(
    "data",
    (
        (["foo ; python_version>'2.7'"], ['foo; python_version > "2.7"']),
        (["foo ; python_version<'2.7'"], ""),
        (
            ["foo ; python_version>'2.7'", "bar ; python_version<'2.7'"],
            ['foo; python_version > "2.7"'],
        ),
        (
            [
                "foo ; python_version>'2.7'",
                "bar ; python_version<'2.7'",
                "foo1 ; extra == 'test'",
            ],
            ['foo; python_version > "2.7"'],
        ),
        (
            ["foobar", "foo ; python_version>'2.7'"],
            ['foo; python_version > "2.7"', "foobar"],
        ),
        (
            [
                "foo ; python_version>'2.7'",
                "bar ; python_version<'2.7'",
                'foo1 ; extra == "test"',
                "foobar",
            ],
            ['foo; python_version > "2.7"', "foobar"],
        ),
    ),
)
def test_config_eval_markers(data, depsconfig, capsys):
    """Eval source with markers"""

    action = "eval"
    deps, out = data

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata", "deps": deps}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[])

    expected_out = out and "\n".join(out) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


@pytest.mark.parametrize(
    "data",
    (
        (["foo"], ["foo"]),
        (["foo", 'bar ; extra == "doc"'], ["foo"]),
        (
            ['foo ; extra == "test"', 'bar ; extra == "doc"'],
            ['foo; extra == "test"'],
        ),
        (
            ['foo ; extra == "test"', 'bar ; extra == "doc"', "foobar"],
            ['foo; extra == "test"', "foobar"],
        ),
        (
            [
                'foo ; extra == "test"',
                'bar ; extra == "doc"',
                "foobar",
                'foo1 ; extra == "test"',
                "foobar1",
            ],
            [
                'foo1; extra == "test"',
                'foo; extra == "test"',
                "foobar",
                "foobar1",
            ],
        ),
        (['foo ; extra == "doc"'], ""),
    ),
)
def test_config_eval_extra(data, depsconfig, capsys):
    """Eval source with extra"""

    action = "eval"
    deps, out = data
    extra = "test"

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata", "deps": deps}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[], extra=extra)

    expected_out = out and "\n".join(out) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


@pytest.mark.parametrize("marker_extra", ("te-st", "te_st", "Te.St", "TE-ST"))
@pytest.mark.parametrize("extra", ("Te-St", "te_st", "te.st"))
def test_config_eval_extra_normalized(extra, marker_extra, depsconfig, capsys):
    """Both the --extra arg and the marker's extra value are normalized
    before comparison (PEP 503/685), so any denormalized spelling of
    either side selects the dep."""

    action = "eval"
    deps = [f'foo ; extra == "{marker_extra}"', 'bar ; extra == "doc"']

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata", "deps": deps}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[], extra=extra)

    captured = capsys.readouterr()
    assert not captured.err
    # eval parses each dep through Requirement and prints str(parsed_req),
    # and packaging normalizes the extra marker on the way, so the printed
    # form is te-st regardless of the stored marker's spelling.
    assert captured.out == 'foo; extra == "te-st"\n'


@pytest.mark.parametrize("deps", (["foo", "foo_bar", "Bar", "foobar"],))
def test_config_eval_excludes(deps, depsconfig, capsys):
    """Eval source with excludes"""

    action = "eval"

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata", "deps": deps}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action,
        depsconfig_path,
        srcnames=[],
        excludes=["bar", "foo-", "foob.*"],
    )

    expected_out = "foo\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


def test_config_eval_metadata_extra_applies_stored_extra(depsconfig, capsys):
    """A metadata_extra source evaluates with its recorded extra."""
    action = "eval"
    collector = "metadata_extra"
    deps = ["qux", 'baz; extra == "bar"', 'corge; extra == "quux"']
    input_conf = {
        "sources": {
            "check": {
                "srctype": collector,
                "srcargs": ["bar"],
                "deps": deps,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    # No --extra on the command line: the stored extra drives evaluation.
    deps_command(action, depsconfig_path, srcnames=[])

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == 'baz; extra == "bar"\nqux\n'


def test_config_eval_metadata_extra_ignores_cli_extra(depsconfig, capsys):
    """For metadata_extra, the recorded extra wins over a CLI --extra."""
    action = "eval"
    collector = "metadata_extra"
    deps = ['baz; extra == "bar"', 'corge; extra == "quux"']
    input_conf = {
        "sources": {
            "check": {
                "srctype": collector,
                "srcargs": ["bar"],
                "deps": deps,
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    # CLI asks for "quux", but the source records "bar" and wins.
    deps_command(action, depsconfig_path, srcnames=[], extra="quux")

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == 'baz; extra == "bar"\n'

from copy import deepcopy
import json

import pytest

from pyproject_installer.errors import DepsSourcesConfigError, DepsUnsyncedError
from pyproject_installer.deps_cmd import deps_command
from pyproject_installer.deps_cmd.collectors.collector import Collector


@pytest.fixture
def mock_collector(mocker):
    """Mock collector"""

    def _collector(reqs):
        class MockCollector(Collector):
            name = "mock_collector"

            def collect(self):
                yield from reqs

        mocker.patch(
            "pyproject_installer.deps_cmd.collectors.SUPPORTED_COLLECTORS",
            {"mock_collector": MockCollector},
        )

    return _collector


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
    data, error = config_data

    depsconfig_path.write_text(data, encoding="utf-8")
    with pytest.raises(DepsSourcesConfigError) as exc:
        deps_command(action, depsconfig_path)
    assert error in str(exc.value)


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
        "sources": {"foo": {"srctype": srctype}, "bar": {"srctype": srctype}}
    }
    assert config_data == expected_data


def test_config_add_existent_source(depsconfig):
    """Add already existent source"""

    action = "add"
    srcname = "foo"
    srctype = "metadata"
    depsconfig_path = depsconfig()

    expected_err = f"Source {srcname} already exists"
    with pytest.raises(ValueError) as exc:
        deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)
    assert expected_err in str(exc.value)


def test_config_add_wrong_srctype(depsconfig_path):
    """Add new source with wrong srctype"""

    action = "add"
    srcname = "foo"
    srctype = "foo"

    expected_err = f"Unsupported collector type: {srctype}"
    with pytest.raises(DepsSourcesConfigError) as exc:
        deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)
    assert expected_err in str(exc.value)


def test_config_add_missing_srcargs(depsconfig_path):
    """Add new source with missing required srcargs"""

    action = "add"
    srcname = "foo"
    srctype = "pip_reqfile"

    expected_err = f"Unsupported arguments of collector {srctype}:"
    with pytest.raises(DepsSourcesConfigError) as exc:
        deps_command(action, depsconfig_path, srcname=srcname, srctype=srctype)
    assert expected_err in str(exc.value)


def test_config_add_extra_srcargs(depsconfig_path):
    """Add new source with extra srcargs"""

    action = "add"
    srcname = "foo"
    srctype = "metadata"

    expected_err = f"Unsupported arguments of collector {srctype}:"
    with pytest.raises(DepsSourcesConfigError) as exc:
        deps_command(
            action,
            depsconfig_path,
            srcname=srcname,
            srctype=srctype,
            srcargs=["fooarg"],
        )
    assert expected_err in str(exc.value)


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
        "sources": {"foo": {"srctype": srctype, "srcargs": srcargs}}
    }
    assert config_data == expected_data


def test_config_delete(depsconfig):
    """Delete source"""

    action = "delete"
    srcname = "foo"
    depsconfig_path = depsconfig()

    deps_command(action, depsconfig_path, srcname=srcname)
    config_data = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    expected_data = {"sources": {}}
    assert config_data == expected_data


def test_config_delete_nonexistent_source(depsconfig):
    """Delete nonexistent source"""

    action = "delete"
    srcname = "bar"
    depsconfig_path = depsconfig()

    expected_err = f"Source {srcname} doesn't exist"
    with pytest.raises(ValueError) as exc:
        deps_command(action, depsconfig_path, srcname=srcname)
    assert expected_err in str(exc.value)


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
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=select)

    out_conf = {"sources": {}}
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
    select, error = select_data

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata"}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command(action, depsconfig_path, srcnames=select)
    assert error in str(exc.value)

    captured = capsys.readouterr()
    assert not captured.err
    assert not captured.out


def test_config_show_empty(depsconfig, capsys):
    """Show empty"""

    action = "show"

    # prepare source config
    input_conf = {"sources": {}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(action, depsconfig_path, srcnames=[])

    output_conf = {"sources": {}}
    expected_out = json.dumps(output_conf, indent=2) + "\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out


def test_config_sync_empty(depsconfig, capsys):
    """Sync empty"""

    action = "sync"

    # prepare source config
    input_conf = {"sources": {}}
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
    input_conf = {
        "sources": {
            "foo": {"srctype": "mock_collector"},
            "bar": {"srctype": "mock_collector"},
            "foobar": {"srctype": "mock_collector"},
        }
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
    select, depsconfig, mock_collector, capsys
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
        }
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
    old_reqs, new_reqs, depsconfig, mock_collector, capsys
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


@pytest.mark.parametrize("select_data", NONEXISTENT_SOURCE_DATA)
def test_config_sync_nonexistent_source(select_data, depsconfig, capsys):
    """Sync nonexistent source"""

    action = "sync"
    select, error = select_data

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {"srctype": "metadata"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command(action, depsconfig_path, srcnames=select)
    assert error in str(exc.value)

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
    input_conf = {"sources": {}}
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
        }
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
    select, error = select_data

    # prepare source config
    input_conf = {
        "sources": {
            "foo": {"srctype": "metadata"},
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command(action, depsconfig_path, srcnames=select)
    assert error in str(exc.value)

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

    with pytest.raises(ValueError) as exc:
        deps_command(action, depsconfig_path, srcnames=[], depformatextra="foo")
    expected_err = "depformatextra must be used with depformat"
    assert expected_err in str(exc.value)

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


@pytest.mark.parametrize("deps", (["foo", "foo_bar", "Bar", "foobar"],))
def test_config_eval_excludes(deps, depsconfig, capsys):
    """Eval source with excludes"""

    action = "eval"

    # prepare source config
    input_conf = {"sources": {"foo": {"srctype": "metadata", "deps": deps}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command(
        action, depsconfig_path, srcnames=[], excludes=["bar", "foo-", "foob.*"]
    )

    expected_out = "foo\n"

    captured = capsys.readouterr()
    assert not captured.err
    assert captured.out == expected_out

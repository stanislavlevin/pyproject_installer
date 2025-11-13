import json
import re
from copy import deepcopy

import pytest

from pyproject_installer.deps_cmd import deps_command

COLLECTOR = "poetry"


@pytest.fixture
def poetry_deps(tmpdir, monkeypatch):
    """poetry deps"""

    def _poetry_deps(content):
        pyproject_toml_path = tmpdir / "pyproject.toml"
        pyproject_toml_path.write_text(content, encoding="utf-8")
        monkeypatch.chdir(tmpdir)
        return pyproject_toml_path

    return _poetry_deps


@pytest.mark.parametrize(
    "deps_data",
    (
        ([], []),
        (['_foo = "*"'], []),
        (['foo = { git = "https://example.com/bar.git" }'], ["foo"]),
        (['foo = { url = "https://example.com/foo-1.0.tar.gz" }'], ["foo"]),
        (['foo = { version = "^2.0.1", python = "<3.11" }'], ["foo"]),
        (
            ['foo = {version = "^2.2", markers = "python_version <= \'3.4\'"}'],
            ['foo; python_version <= "3.4"'],
        ),
        (
            ['foo = {version = "^2.2", markers = "invalid_marker == \'3.4\'"}'],
            ["foo"],
        ),
        (
            [
                "foo = [",
                '    {version = "<=1.9", python = ">=3.6,<3.8"},',
                '    {version = "^2.0", python = ">=3.8"},',
                "]",
            ],
            ["foo"],
        ),
        (['foo = { path = "foo-1.0.tar.gz" }'], ["foo"]),
        (['foo = "*"', 'bar = "*"'], ["bar", "foo"]),
        (['bar = "*"', 'foo = "*"'], ["bar", "foo"]),
        (['Foo = "*"'], ["Foo"]),
        (['foo = "~1.2.3"', 'bar = "^1.2.3"'], ["bar", "foo"]),
    ),
)
@pytest.mark.parametrize(
    "notation",
    ("tool.poetry.group.dev.dependencies", "tool.poetry.dev-dependencies"),
)
def test_poetry_collector(deps_data, notation, poetry_deps, depsconfig):
    """Collection of poetry deps"""
    # prepare source config
    srcname = "foo"

    input_conf = {
        "sources": {srcname: {"srctype": COLLECTOR, "srcargs": ["dev"]}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, out_reqs = deps_data

    poetry_content = f"[{notation}]\n"
    poetry_content += "\n".join(in_reqs) + "\n"
    poetry_deps(poetry_content)

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize("poetry_config", ("", "[tool]"))
def test_poetry_collector_missing_config(
    poetry_config,
    poetry_deps,
    depsconfig,
):
    """Collection of poetry's with missing config"""
    # prepare source config
    srcname = "foo"
    groupname = "bar"

    input_conf = {
        "sources": {srcname: {"srctype": COLLECTOR, "srcargs": [groupname]}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    poetry_deps(poetry_config + "\n")

    expected_err = re.escape(
        "Poetry is not configured: missing tool.poetry",
    )
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "poetry_config",
    ("[tool.poetry]", "[tool.poetry.group]", "[tool.poetry.group.test]"),
)
def test_poetry_collector_wrong_group(poetry_config, poetry_deps, depsconfig):
    """Collection of poetry's wrong group"""
    # prepare source config
    srcname = "foo"
    groupname = "bar"

    input_conf = {
        "sources": {srcname: {"srctype": COLLECTOR, "srcargs": [groupname]}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    poetry_deps(poetry_config + "\n")

    expected_err = re.escape(
        f"{groupname} is not configured: missing tool.poetry.group.{groupname}",
    )
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_poetry_collector_missing_dependencies(poetry_deps, depsconfig):
    """Collection of poetry's missing dependencies"""
    # prepare source config
    srcname = "foo"
    groupname = "bar"

    input_conf = {
        "sources": {srcname: {"srctype": COLLECTOR, "srcargs": [groupname]}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))
    poetry_deps(f"[tool.poetry.group.{groupname}]\n")

    expected_err = re.escape(
        f"Dependencies are not configured for {groupname}: "
        f"missing tool.poetry.group.{groupname}.dependencies",
    )
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_poetry_collector_invalid_sep(poetry_deps, depsconfig, mocker):
    """
    Collection of poetry's deps with no longer valid PEP508 marker separator
    """
    invalid_sep = "INVALID_SEP"
    mocker.patch(
        "pyproject_installer.deps_cmd.collectors.poetry.PEP508_ENV_MARK_SEP",
        invalid_sep,
    )
    # prepare source config
    srcname = "foo"
    groupname = "bar"

    input_conf = {
        "sources": {srcname: {"srctype": COLLECTOR, "srcargs": [groupname]}},
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    poetry_content = (
        f"[tool.poetry.group.{groupname}.dependencies]\n"
        'foo = {version = "1.0", markers = "python_version <= \'3.4\'"}\n'
    )
    poetry_deps(poetry_content)

    expected_err = re.escape(
        f"{COLLECTOR}: invalid PEP508 Dependency Specifier: "
        f"foo{invalid_sep}python_version <= '3.4'",
    )
    expected_err = f"^{expected_err}$"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


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
    collector = "poetry"

    input_conf = {
        "sources": {srcname: {"srctype": collector, "srcargs": ["dev"]}}
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
    poetry_config, poetry_deps, depsconfig
):
    """Collection of poetry's with missing config"""
    # prepare source config
    srcname = "foo"
    collector = "poetry"
    groupname = "bar"

    input_conf = {
        "sources": {srcname: {"srctype": collector, "srcargs": [groupname]}}
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    poetry_deps(poetry_config + "\n")

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = "Poetry is not configured: missing tool.poetry"
    assert expected_err in str(exc.value)

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
    collector = "poetry"
    groupname = "bar"

    input_conf = {
        "sources": {srcname: {"srctype": collector, "srcargs": [groupname]}}
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    poetry_deps(poetry_config + "\n")

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        f"{groupname} is not configured: missing tool.poetry.group.{groupname}"
    )
    assert expected_err in str(exc.value)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_poetry_collector_missing_dependencies(poetry_deps, depsconfig):
    """Collection of poetry's missing dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "poetry"
    groupname = "bar"

    input_conf = {
        "sources": {srcname: {"srctype": collector, "srcargs": [groupname]}}
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))
    poetry_deps(f"[tool.poetry.group.{groupname}]\n")

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        f"Dependencies are not configured for {groupname}: "
        f"missing tool.poetry.group.{groupname}.dependencies"
    )
    assert expected_err in str(exc.value)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def pipenv_deps(tmpdir, monkeypatch):
    """pipenv deps"""

    def _pipenv_deps(content):
        pipfile_path = tmpdir / "Pipfile"
        pipfile_path.write_text(content, encoding="utf-8")
        monkeypatch.chdir(tmpdir)
        return pipfile_path

    return _pipenv_deps


@pytest.mark.parametrize(
    "deps_data",
    (
        ([], []),
        (['_foo = "*"'], []),
        (['foo = "*"'], ["foo"]),
        (['foo = "1.0"'], ["foo"]),
        (['foo = { git = "https://example.com/bar.git" }'], ["foo"]),
        (['foo = { version = "1.0" }'], ["foo"]),
        (
            ['foo = { git = "https://example.com/bar.git", version = "1.0" }'],
            ["foo"],
        ),
        (
            ['foo = {version = "1.0", markers = "python_version <= \'3.4\'"}'],
            ['foo; python_version <= "3.4"'],
        ),
        (
            ['foo = {version = "1.0", markers = "invalid_marker == \'3.4\'"}'],
            ["foo"],
        ),
        (['foo = "*"', 'bar = "*"'], ["bar", "foo"]),
        (['bar = "*"', 'foo = "*"'], ["bar", "foo"]),
        (['Foo = "*"'], ["Foo"]),
        (['foo = "1.0"', 'bar = "1.0"'], ["bar", "foo"]),
        (['foo = {version = "*", sys_platform = "== \'win32\'"}'], ["foo"]),
    ),
)
def test_pipenv_collector(deps_data, pipenv_deps, depsconfig):
    """Collection of pipenv deps"""
    # prepare source config
    srcname = "foo"
    collector = "pipenv"
    category = "packages"

    in_reqs, out_reqs = deps_data

    pipenv_content = f"[{category}]\n"
    pipenv_content += "\n".join(in_reqs) + "\n"
    pipenv_path = pipenv_deps(pipenv_content)

    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(pipenv_path), category],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_pipenv_collector_missing_category(pipenv_deps, depsconfig):
    """Collection of pipenv's deps with missing category"""
    # prepare source config
    srcname = "foo"
    collector = "pipenv"
    category = "packages"

    pipenv_path = pipenv_deps("\n")

    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(pipenv_path), category],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        f"pipenv dependencies are not configured for category: {category}"
    )
    assert expected_err in str(exc.value)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

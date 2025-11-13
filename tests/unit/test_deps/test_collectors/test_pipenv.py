import json
import re
from copy import deepcopy

import pytest

from pyproject_installer.deps_cmd import deps_command

COLLECTOR = "pipenv"


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
    category = "packages"

    in_reqs, out_reqs = deps_data

    pipenv_content = f"[{category}]\n"
    pipenv_content += "\n".join(in_reqs) + "\n"
    pipenv_path = pipenv_deps(pipenv_content)

    input_conf = {
        "sources": {
            srcname: {
                "srctype": COLLECTOR,
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
    category = "packages"

    pipenv_path = pipenv_deps("\n")

    input_conf = {
        "sources": {
            srcname: {
                "srctype": COLLECTOR,
                "srcargs": [str(pipenv_path), category],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = re.escape(
        f"pipenv dependencies are not configured for category: {category}",
    )
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pipenv_collector_invalid_sep(pipenv_deps, depsconfig, mocker):
    """
    Collection of pipenv's deps with no longer valid PEP508 marker separator
    """
    invalid_sep = "INVALID_SEP"
    mocker.patch(
        "pyproject_installer.deps_cmd.collectors.pipenv.PEP508_ENV_MARK_SEP",
        invalid_sep,
    )
    # prepare source config
    srcname = "foo"
    category = "packages"

    pipenv_content = (
        f"[{category}]\n"
        'foo = {version = "1.0", markers = "python_version <= \'3.4\'"}\n'
    )
    pipenv_path = pipenv_deps(pipenv_content)

    input_conf = {
        "sources": {
            srcname: {
                "srctype": COLLECTOR,
                "srcargs": [str(pipenv_path), category],
            },
        },
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    expected_err = re.escape(
        f"{COLLECTOR}: invalid PEP508 Dependency Specifier: "
        f"foo{invalid_sep}python_version <= '3.4'",
    )
    expected_err = f"^{expected_err}$"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

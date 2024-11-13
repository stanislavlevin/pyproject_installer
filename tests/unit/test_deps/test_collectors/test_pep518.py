from copy import deepcopy
import json
import textwrap

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def pyproject_pep518(pyproject, monkeypatch):
    """pyproject.toml with PEP518 deps"""

    def _pyproject_pep518(reqs):
        toml_content = textwrap.dedent(
            f"""\
            [build-system]
            build-backend = "be"
            requires = {reqs}
            """
        )
        pyproject_path = pyproject(toml_content)
        monkeypatch.chdir(pyproject_path)
        return pyproject_path

    return _pyproject_pep518


def test_pep518_collector_missing_pyproject_toml(
    tmpdir, depsconfig, monkeypatch
):
    """Collection of pep518 reqs with missing pyproject.toml"""
    # prepare source config
    srcname = "foo"
    collector = "pep518"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    monkeypatch.chdir(tmpdir)
    assert not (tmpdir / "pyproject.toml").exists()

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = ["setuptools", "wheel"]
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_pep518_collector_missing_build_system(
    pyproject, depsconfig, monkeypatch
):
    """Collection of pep518 reqs with missing build-system"""
    # prepare source config
    srcname = "foo"
    collector = "pep518"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    pyproject_path = pyproject("")
    monkeypatch.chdir(pyproject_path)

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"][srcname]["deps"] = ["setuptools", "wheel"]
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_pep518_collector(deps_data, pyproject_pep518, depsconfig):
    """Collection of pep518 reqs"""
    # prepare source config
    srcname = "foo"
    collector = "pep518"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, out_reqs = deps_data

    pyproject_pep518(in_reqs)
    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

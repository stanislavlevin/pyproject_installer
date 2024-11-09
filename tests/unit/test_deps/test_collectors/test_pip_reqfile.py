from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def pip_reqfile(tmpdir, monkeypatch):
    """pip's requirements.txt file"""

    def _pip_reqfile(content):
        reqfile_path = tmpdir / "requirements.txt"
        reqfile_path.write_text(content, encoding="utf-8")
        monkeypatch.chdir(tmpdir)
        return reqfile_path

    return _pip_reqfile


def test_pipreqfile_collector_valid_deps(
    valid_pep508_data, pip_reqfile, depsconfig
):
    """Collection of pip's (valid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "pip_reqfile"

    in_reqs, out_reqs = valid_pep508_data

    pip_reqfile_path = pip_reqfile("\n".join(in_reqs) + "\n")

    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [str(pip_reqfile_path)]},
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_pipreqfile_collector_invalid_deps(
    invalid_pep508_data, pip_reqfile, depsconfig
):
    """Collection of pip's (invalid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "pip_reqfile"

    in_reqs, out_reqs = invalid_pep508_data

    pip_reqfile_path = pip_reqfile("\n".join(in_reqs) + "\n")

    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [str(pip_reqfile_path)]},
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize(
    "valid_pip_deps_data",
    (
        (["-r other-requirements.txt"], []),
        (["-r other-requirements.txt", "foo"], ["foo"]),
        (["-c constraints.txt"], []),
        (["-c constraints.txt", "foo"], ["foo"]),
        (["# comment"], []),
        (["# comment", "foo"], ["foo"]),
        (["foo # comment"], ["foo"]),
        (["./foo.whl"], []),
        (["./foo.whl", "bar"], ["bar"]),
        (["https://example.com/foo.whl"], []),
        (["https://example.com/foo.whl", "bar"], ["bar"]),
        (["\\"], []),
        (["foo", "\\", " > 1.0"], ["foo"]),
    ),
)
def test_pipreqfile_collector_unsupported_deps(
    valid_pip_deps_data, pip_reqfile, depsconfig
):
    """Collection of pip's unsupported reqs"""
    # prepare source config
    srcname = "foo"
    collector = "pip_reqfile"

    in_reqs, out_reqs = valid_pip_deps_data

    pip_reqfile_path = pip_reqfile("\n".join(in_reqs) + "\n")

    input_conf = {
        "sources": {
            srcname: {"srctype": collector, "srcargs": [str(pip_reqfile_path)]},
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

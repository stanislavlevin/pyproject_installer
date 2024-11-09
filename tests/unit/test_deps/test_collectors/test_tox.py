from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def tox_deps(tmpdir, monkeypatch):
    """tox deps in specified format"""

    def _tox_deps(config_type, testenv, deps):
        if config_type == "toml":
            config_path = tmpdir / "pyproject.toml"
            contents = ["[tool.tox]", "legacy_tox_ini = '''", f"[{testenv}]"]
            if deps is not None:
                contents.append("deps =")
                contents.extend((f"    {x}" for x in deps))
            contents.append("'''")

        elif config_type == "ini":
            config_path = tmpdir / "tox.ini"
            contents = [f"[{testenv}]"]
            if deps is not None:
                contents.append("deps =")
                contents.extend((f"    {x}" for x in deps))
        else:
            raise ValueError(f"Unsupported tox config type: {config_type}")

        config_path.write_text("\n".join(contents) + "\n", encoding="utf-8")
        monkeypatch.chdir(tmpdir)
        return config_path

    return _tox_deps


@pytest.mark.parametrize("config_type", ("toml", "ini"))
def test_tox_collector_valid_deps(
    valid_pep508_data, config_type, tox_deps, depsconfig
):
    """Collection of tox (valid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "tox"
    testenv = "testenv"

    in_reqs, out_reqs = valid_pep508_data

    tox_config_path = tox_deps(config_type, testenv, in_reqs)
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(tox_config_path), testenv],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize("config_type", ("toml", "ini"))
def test_tox_collector_invalid_deps(
    invalid_pep508_data, config_type, tox_deps, depsconfig
):
    """Collection of tox (invalid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "tox"
    testenv = "testenv"

    in_reqs, out_reqs = invalid_pep508_data

    tox_config_path = tox_deps(config_type, testenv, in_reqs)
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(tox_config_path), testenv],
            },
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
    "valid_tox_deps",
    (
        (["-r requirements.txt"], []),
        (["-r requirements.txt", "foo"], ["foo"]),
        (["-c constraints.txt"], []),
        (["-c constraints.txt", "foo"], ["foo"]),
    ),
)
@pytest.mark.parametrize("config_type", ("toml", "ini"))
def test_tox_collector_unsupported(
    valid_tox_deps, config_type, tox_deps, depsconfig
):
    """Collection of unsupported tox formats"""
    # prepare source config
    srcname = "foo"
    collector = "tox"
    testenv = "testenv"

    in_reqs, out_reqs = valid_tox_deps

    tox_config_path = tox_deps(config_type, testenv, in_reqs)
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(tox_config_path), testenv],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize("tox_config", ("", "[tool]", "[tool.tox]"))
def test_tox_collector_missing_configuration(
    tox_config, tmpdir, depsconfig, monkeypatch
):
    """Collection of tox with missing configuration"""
    # prepare source config
    srcname = "foo"
    collector = "tox"

    tox_config_path = tmpdir / "pyproject.toml"
    tox_config_path.write_text(tox_config + "\n", encoding="utf-8")
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(tox_config_path), "testenv"],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    monkeypatch.chdir(tmpdir)
    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = "Tox is not configured: missing tool.tox.legacy_tox_ini"
    assert expected_err in str(exc.value)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize("config_type", ("toml", "ini"))
def test_tox_collector_missing_testenv(config_type, tox_deps, depsconfig):
    """Collection of missing tox testenv"""
    # prepare source config
    srcname = "foo"
    collector = "tox"
    testenv = "foo"

    tox_config_path = tox_deps(config_type, "testenv", [])

    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(tox_config_path), testenv],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = f"Test environment is not configured: {testenv}"
    assert expected_err in str(exc.value)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize("config_type", ("toml", "ini"))
def test_tox_collector_missing_deps(config_type, tox_deps, depsconfig):
    """Collection of missing tox deps"""
    # prepare source config
    srcname = "foo"
    collector = "tox"
    testenv = "foo"

    tox_config_path = tox_deps(config_type, testenv, None)

    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(tox_config_path), testenv],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        f"Dependencies are not configured for {testenv}: missing {testenv}.deps"
    )
    assert expected_err in str(exc.value)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

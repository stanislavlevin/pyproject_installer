from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def hatch_deps(tmpdir, monkeypatch):
    """hatch's deps in specified config"""

    def _hatch_deps(config, envname, deps, extra_deps=None):
        if config == "pyproject.toml":
            contents = [f"[tool.hatch.envs.{envname}]"]
        else:
            contents = [f"[envs.{envname}]"]
        config_path = tmpdir / config
        if deps is not None:
            contents.append("dependencies = [")
            contents.extend((f'"{x}",' for x in deps))
            contents.append("]")
        if extra_deps is not None:
            contents.append("extra-dependencies = [")
            contents.extend((f'"{x}",' for x in extra_deps))
            contents.append("]")

        config_path.write_text("\n".join(contents) + "\n", encoding="utf-8")
        monkeypatch.chdir(tmpdir)
        return config_path

    return _hatch_deps


@pytest.mark.parametrize("config", ("pyproject.toml", "hatch.toml"))
def test_hatch_collector_valid_deps(
    valid_pep508_data, config, hatch_deps, depsconfig
):
    """Collection of hatch (valid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "hatch"
    envname = "test"

    in_reqs, out_reqs = valid_pep508_data

    hatch_config_path = hatch_deps(config, envname, in_reqs)
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(hatch_config_path), envname],
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


@pytest.mark.parametrize("config", ("pyproject.toml", "hatch.toml"))
def test_hatch_collector_invalid_deps(
    invalid_pep508_data, config, hatch_deps, depsconfig
):
    """Collection of hatch (invalid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "hatch"
    envname = "test"

    in_reqs, out_reqs = invalid_pep508_data

    hatch_config_path = hatch_deps(config, envname, in_reqs)
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(hatch_config_path), envname],
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


@pytest.mark.parametrize("config", ("pyproject.toml", "hatch.toml"))
def test_hatch_collector_extra_valid_deps(
    valid_pep508_data, config, hatch_deps, depsconfig
):
    """Collection of hatch extra-dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "hatch"
    envname = "test"

    in_reqs, out_reqs = valid_pep508_data

    hatch_config_path = hatch_deps(
        config, envname, deps=None, extra_deps=in_reqs
    )
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(hatch_config_path), envname],
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


@pytest.mark.parametrize("config", ("pyproject.toml", "hatch.toml"))
def test_hatch_collector_extra_invalid_deps(
    invalid_pep508_data, config, hatch_deps, depsconfig
):
    """Collection of hatch extra-dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "hatch"
    envname = "test"

    in_reqs, out_reqs = invalid_pep508_data

    hatch_config_path = hatch_deps(
        config, envname, deps=None, extra_deps=in_reqs
    )
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(hatch_config_path), envname],
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
    "hatch_config",
    ("", "[tool]", "[tool.hatch]", "[tool.hatch.envs]", "[tool.hatch.envs.a]"),
)
def test_hatch_collector_missing_configuration_pyproject(
    hatch_config, tmpdir, depsconfig, monkeypatch
):
    """Collection of hatch(pyproject.toml) with missing configuration"""
    # prepare source config
    srcname = "foo"
    collector = "hatch"
    hatchenv = "test"

    hatch_config_path = tmpdir / "pyproject.toml"
    hatch_config_path.write_text(hatch_config + "\n", encoding="utf-8")
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(hatch_config_path), hatchenv],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    monkeypatch.chdir(tmpdir)
    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        f"Hatch: missing tool.hatch.envs.{hatchenv} table in "
        f"{hatch_config_path.name}"
    )
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize("hatch_config", ("", "[envs]", "[envs.a]"))
def test_hatch_collector_missing_configuration_hatch(
    hatch_config, tmpdir, depsconfig, monkeypatch
):
    """Collection of hatch(hatch.toml) with missing configuration"""
    # prepare source config
    srcname = "foo"
    collector = "hatch"
    hatchenv = "test"

    hatch_config_path = tmpdir / "hatch.toml"
    hatch_config_path.write_text(hatch_config + "\n", encoding="utf-8")
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(hatch_config_path), hatchenv],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    monkeypatch.chdir(tmpdir)
    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        f"Hatch: missing envs.{hatchenv} table in {hatch_config_path.name}"
    )
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize("config", ("pyproject.toml", "hatch.toml"))
def test_hatch_collector_missing_deps(config, hatch_deps, depsconfig):
    """Collection of missing hatch deps"""
    # prepare source config
    srcname = "foo"
    collector = "hatch"
    hatchenv = "test"

    hatch_config_path = hatch_deps(config, hatchenv, deps=None, extra_deps=None)

    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [str(hatch_config_path), hatchenv],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        f"Hatch dependencies are not configured for {hatchenv}: "
        f"missing {hatchenv}.dependencies and {hatchenv}.extra-dependencies"
    )
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

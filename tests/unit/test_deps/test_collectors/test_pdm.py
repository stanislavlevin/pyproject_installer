from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def pdm_deps(tmpdir, monkeypatch):
    """pdm deps"""

    def _pdm_deps(group, deps):
        contents = ["[tool.pdm.dev-dependencies]"]
        if deps is not None:
            contents.append(f"{group} = [")
            contents.extend((f'"{x}",' for x in deps))
            contents.append("]")

        config_path = tmpdir / "pyproject.toml"
        config_path.write_text("\n".join(contents) + "\n", encoding="utf-8")
        monkeypatch.chdir(tmpdir)
        return config_path

    return _pdm_deps


def test_pdm_collector_valid_deps(valid_pep508_data, pdm_deps, depsconfig):
    """Collection of pdm (valid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "pdm"
    group = "test"

    in_reqs, out_reqs = valid_pep508_data

    pdm_deps(group, in_reqs)
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [group],
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


def test_pdm_collector_invalid_deps(invalid_pep508_data, pdm_deps, depsconfig):
    """Collection of pdm (invalid PEP508) dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "pdm"
    group = "test"

    in_reqs, out_reqs = invalid_pep508_data

    pdm_deps(group, in_reqs)
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [group],
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


@pytest.mark.parametrize("pdm_config", ("", "[tool]", "[tool.pdm]"))
def test_pdm_collector_missing_configuration(
    pdm_config, tmpdir, depsconfig, monkeypatch
):
    """Collection of pdm with missing configuration"""
    # prepare source config
    srcname = "foo"
    collector = "pdm"
    group = "test"

    pdm_config_path = tmpdir / "pyproject.toml"
    pdm_config_path.write_text(pdm_config + "\n", encoding="utf-8")
    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [group],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    monkeypatch.chdir(tmpdir)
    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = (
        "Pdm: missing tool.pdm.dev-dependencies table in "
        f"{pdm_config_path.name}"
    )
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pdm_collector_missing_deps(pdm_deps, depsconfig):
    """Collection of missing pdm deps"""
    # prepare source config
    srcname = "foo"
    collector = "pdm"
    group = "test"

    pdm_deps(group, deps=None)

    input_conf = {
        "sources": {
            srcname: {
                "srctype": collector,
                "srcargs": [group],
            },
        }
    }
    depsconfig_path = depsconfig(json.dumps(input_conf))

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])
    expected_err = f"Pdm dependencies are not configured for group: {group}"
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

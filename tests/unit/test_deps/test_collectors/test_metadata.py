from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


def test_metadata_collector_metadata_valid_deps(
    valid_pep508_data, pyproject_metadata, depsconfig
):
    """
    Collection of core metadata's valid PEP508 dependencies via
    prepare_metadata_for_build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, out_reqs = valid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata(reqs=in_reqs)

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_metadata_collector_metadata_invalid_deps(
    invalid_pep508_data, pyproject_metadata, depsconfig
):
    """
    Collection of core metadata's invalid PEP508 dependencies via
    prepare_metadata_for_build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, _ = invalid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata(reqs=in_reqs)

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"{collector}: invalid PEP508 Dependency Specifier: "
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_metadata_collector_wheel_valid_deps(
    valid_pep508_data, pyproject_metadata_wheel, depsconfig
):
    """
    Collection of core metadata's valid PEP508 dependencies via
    build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, out_reqs = valid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata_wheel(reqs=in_reqs)

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_metadata_collector_wheel_invalid_deps(
    invalid_pep508_data, pyproject_metadata_wheel, depsconfig
):
    """
    Collection of core metadata's invalid PEP508 dependencies via
    build_wheel
    """
    # prepare source config
    srcname = "foo"
    collector = "metadata"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, _ = invalid_pep508_data

    # configure pyproject with build backend
    pyproject_metadata_wheel(reqs=in_reqs)

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"{collector}: invalid PEP508 Dependency Specifier: "
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

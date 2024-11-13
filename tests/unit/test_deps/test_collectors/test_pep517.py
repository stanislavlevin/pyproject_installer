from copy import deepcopy
import json
import textwrap

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def pyproject_pep517_wheel(pyproject_with_backend):
    """Build backend with get_requires_for_build_wheel"""

    def _pep517_wheel(reqs):
        be_content = textwrap.dedent(
            f"""\
            def get_requires_for_build_wheel(config_settings=None):
                return {reqs}
            """
        )
        return pyproject_with_backend(be_content)

    return _pep517_wheel


def test_pep517_collector_valid_deps(
    valid_pep508_data, pyproject_pep517_wheel, depsconfig
):
    """Collection of PEP517 (valid PEP508) wheel dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "pep517"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, out_reqs = valid_pep508_data

    # configure pyproject with build backend
    pyproject_pep517_wheel(in_reqs)

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"][srcname]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


def test_pep517_collector_invalid_deps(
    invalid_pep508_data, pyproject_pep517_wheel, depsconfig
):
    """Collection of PEP517 (invalid PEP508) wheel dependencies"""
    # prepare source config
    srcname = "foo"
    collector = "pep517"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    in_reqs, _ = invalid_pep508_data

    # configure pyproject with build backend
    pyproject_pep517_wheel(in_reqs)

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"{collector}: invalid PEP508 Dependency Specifier: "
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep517_collector_missing_hook(pyproject_with_backend, depsconfig):
    """Build backend doesn't have get_requires_for_build_wheel"""
    # prepare source config
    srcname = "foo"
    collector = "pep517"
    input_conf = {"sources": {srcname: {"srctype": collector}}}
    depsconfig_path = depsconfig(json.dumps(input_conf))

    # configure pyproject with build backend
    pyproject_with_backend("")

    deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf

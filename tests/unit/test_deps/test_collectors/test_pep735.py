from copy import deepcopy
import json

import pytest

from pyproject_installer.deps_cmd import deps_command


@pytest.fixture
def pep735_deps(pyproject_toml):
    """Fill pyproject.toml with Dependency Groups dependencies (PEP735)"""

    def _pep735_deps(groups_data):
        contents = ["[dependency-groups]"]
        for group, deps in groups_data.items():
            contents.append(f"{group} = [{', '.join(deps)}]")

        parent_path = pyproject_toml("\n".join(contents) + "\n")
        return parent_path

    return _pep735_deps


@pytest.fixture
def pep735_depsconfig(depsconfig):
    """Configure depsconfig for PEP735 source of dependencies"""
    srcname = "src1"
    collector = "pep735"

    def _pep735_depsconfig(group="test"):
        input_conf = {
            "sources": {
                srcname: {
                    "srctype": collector,
                    "srcargs": [group],
                },
            }
        }
        depsconfig_path = depsconfig(json.dumps(input_conf))
        return depsconfig_path, input_conf

    return _pep735_depsconfig


VALID_INCLUDE_PEP735_DATA = (
    ({"gp1": ['"a"'], "test": ['{include-group = "gp1"}']}, ["a"]),
    ({"gP1": ['"a"'], "tEst": ['{include-group = "Gp1"}']}, ["a"]),
    (
        {"gp1": ['"a"', '"b"'], "test": ['"c"', '{include-group = "gp1"}']},
        ["a", "b", "c"],
    ),
    (
        {"gp1": ['"a"', '"b"'], "test": ['"a"', '{include-group = "gp1"}']},
        ["a", "b"],
    ),
    (
        {
            "gp1": ['"a"', '"b"'],
            "test": ['"a"', '{include-group = "gp1"}', '"b"'],
        },
        ["a", "b"],
    ),
    (
        {"gp1": ['"a"', '"b"'], "test": ['"a>1.0"', '{include-group = "gp1"}']},
        ["a", "a>1.0", "b"],
    ),
    (
        {
            "gp1": ['"a"', '"b"'],
            "test": ['"c"', '{include-group = "gp1"}', '"d"'],
        },
        ["a", "b", "c", "d"],
    ),
    (
        {
            "gp1": ['{include-group = "gp2"}', '"b"'],
            "gp2": ['"a"', '"d"'],
            "test": ['"c"', '{include-group = "gp1"}'],
        },
        ["a", "b", "c", "d"],
    ),
    (
        {
            "gp1": ['{include-group = "gp2"}', '"b"'],
            "gp2": ['"a"', '"d"'],
            "test": [
                '{include-group = "gp1"}',
                '{include-group = "gp2"}',
                '"c"',
            ],
        },
        ["a", "b", "c", "d"],
    ),
)


def test_pep735_collector_missing_depgroups(pyproject_toml, pep735_depsconfig):
    """
    Collection of PEP735 dependencies with missing 'dependency-groups' table
    """
    pyproject_toml("")
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = "pep735: missing dependency-groups table in pyproject.toml"
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep735_collector_invalid_type_depgroups(
    pyproject_toml, pep735_depsconfig
):
    """
    Collection of PEP735 dependencies with invalid type of 'dependency-groups'
    """
    pyproject_toml('dependency-groups = "test"\n')
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(TypeError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = "pep735: Dependency Groups is not a dict: "
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep735_collector_no_groups(pep735_deps, pep735_depsconfig):
    """
    Collection of PEP735 dependencies with no groups (keys)
    """
    pep735_deps({})
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = (
        "pep735: group dependencies are not configured ("
        "group: test, include chain: )"
    )
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        ({"gp1": []}, "group: test, include chain: "),
        (
            {"teSt": ['{include-group = "gP1"}']},
            "group: gP1, include chain: teSt->gP1",
        ),
        (
            {
                "gP1": ['{include-group = "gP2"}'],
                "teSt": ['{include-group = "Gp1"}'],
            },
            "group: gP2, include chain: teSt->gP1->gP2",
        ),
    ),
)
def test_pep735_collector_missing_group(
    pep735_deps, pep735_depsconfig, group_data
):
    """
    Collection of PEP735 dependencies with missing group
    """
    group_config, err_msg = group_data
    pep735_deps(group_config)
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"pep735: group dependencies are not configured ({err_msg})"
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        (
            {"tesT": [], "Test": []},
            "(group: test, include chain: ): Test, tesT",
        ),
        (
            {"gRp": [], "Grp": [], "teSt": ['{include-group = "grP"}']},
            "(group: grP, include chain: teSt->grP): Grp, gRp",
        ),
        (
            {
                "gRp1": ['{include-group = "grP2"}'],
                "Grp2": [],
                "gRp2": [],
                "teSt": ['{include-group = "grP1"}'],
            },
            "(group: grP2, include chain: teSt->gRp1->grP2): Grp2, gRp2",
        ),
    ),
)
def test_pep735_collector_duplicate_names(
    pep735_deps, pep735_depsconfig, group_data
):
    """
    Collection of PEP735 dependencies with duplicate group names
    """
    group_config, err_msg = group_data
    pep735_deps(group_config)
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"pep735: duplicate group names {err_msg}"
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        (["tesT = true"], "group: tesT, include chain: "),
        (
            ["gRp = true", 'teSt = [{include-group = "grP"}]'],
            "group: gRp, include chain: teSt->gRp",
        ),
        (
            [
                'gRp1 = [{include-group = "grP2"}]',
                "gRp2 = true",
                'teSt = [{include-group = "grP1"}]',
            ],
            "group: gRp2, include chain: teSt->gRp1->gRp2",
        ),
    ),
)
def test_pep735_collector_invalid_type_groupdeps(
    pyproject_toml, pep735_depsconfig, group_data
):
    """
    Collection of PEP735 dependencies with invalid type of group's value
    """
    group_config, err_msg = group_data
    pyproject_toml("\n".join(["[dependency-groups]"] + group_config) + "\n")
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(TypeError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"pep735: dependencies format is not a list ({err_msg}): "
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        ({"tesT": ["true"]}, "group: tesT, include chain: "),
        ({"tesT": ['"foo"', "true"]}, "group: tesT, include chain: "),
        (
            {"gRp": ["true"], "teSt": ['{include-group = "grP"}']},
            "group: gRp, include chain: teSt->gRp",
        ),
        (
            {
                "gRp1": ['{include-group = "grP2"}'],
                "Grp2": ["true"],
                "teSt": ['{include-group = "grP1"}'],
            },
            "group: Grp2, include chain: teSt->gRp1->Grp2",
        ),
    ),
)
def test_pep735_collector_invalid_type_depslist(
    group_data, pep735_deps, pep735_depsconfig
):
    """
    Collection of PEP735 dependencies with invalid type of requirement lists

    Requirement lists under dependency-groups may contain strings, tables
    (“dicts” in Python), or a mix of strings and tables.
    """
    group_config, err_msg = group_data

    pep735_deps(group_config)
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(TypeError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = (
        f"pep735: dependencies lists may contain strings or dicts ({err_msg}): "
    )
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep735_collector_valid_pep508_deps(
    valid_pep508_data, pep735_deps, pep735_depsconfig
):
    """
    Collection of PEP735 (valid PEP508) dependencies

    Strings in requirement lists must be valid Dependency Specifiers, as defined
    in PEP 508.
    """
    in_reqs, out_reqs = valid_pep508_data
    pep735_deps({"test": (f'"{x}"' for x in in_reqs)})
    depsconfig_path, input_conf = pep735_depsconfig("test")

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"]["src1"]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize(
    "group_data",
    (
        ({"tesT": None}, "tesT", "group: tesT, include chain: "),
        (
            {"gRp": None, "teSt": ['{include-group = "grP"}']},
            "gRp",
            "group: gRp, include chain: teSt->gRp",
        ),
        (
            {
                "gRp1": ['{include-group = "grP2"}'],
                "Grp2": None,
                "teSt": ['{include-group = "grP1"}'],
            },
            "Grp2",
            "group: Grp2, include chain: teSt->gRp1->Grp2",
        ),
    ),
)
def test_pep735_collector_invalid_pep508_deps(
    pep735_deps, pep735_depsconfig, invalid_pep508_data, group_data
):
    """
    Collection of PEP735 (invalid PEP508) dependencies

    Strings in requirement lists must be valid Dependency Specifiers, as defined
    in PEP 508.
    """
    group_config, group, err_msg = group_data
    in_reqs, _ = invalid_pep508_data

    pep735_deps(group_config | {group: [f'"{x}"' for x in in_reqs]})
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"pep735: invalid PEP508 Dependency Specifier ({err_msg}): "
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        {"test": []},
        {"gP1": [], "test": ['{include-group = "Gp1"}']},
        {
            "Gp1": ['{include-group = "gP2"}'],
            "gP2": [],
            "test": ['{include-group = "gP1"}'],
        },
    ),
)
def test_pep735_collector_no_deps(pep735_deps, pep735_depsconfig, group_data):
    """
    Collection of PEP735 empty (zero) dependencies
    """
    pep735_deps(group_data)
    depsconfig_path, input_conf = pep735_depsconfig()

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize(
    "group_data",
    (
        ({"test": ['"foo"'], "gp1": ['{foo = "bar"}']}, ["foo"]),
        ({"gp1": ['{foo = "bar"}'], "test": ['"foo"']}, ["foo"]),
        (
            {"test": ['"foo"'], "gp1": ['{foo = "bar"}'], "gp2": ['"_foo"']},
            ["foo"],
        ),
        (
            {"gp1": ['{foo = "bar"}'], "gp2": ['"_foo"'], "test": ['"foo"']},
            ["foo"],
        ),
        ({"test": ['"foo"'], "gp1": ['"foo1"'], "gP1": ['"foo2"']}, ["foo"]),
        ({"gp1": ['{include-group = "gp2"}'], "test": ['"foo"']}, ["foo"]),
    ),
)
def test_pep735_collector_not_eagerly_validating(
    group_data, pep735_deps, pep735_depsconfig
):
    """
    Collection of PEP735 dependencies should ignore other (not requested) groups

    Tools SHOULD NOT eagerly validate the list contents of all Dependency Groups.
    """
    in_groups, out_reqs = group_data

    pep735_deps(in_groups)
    depsconfig_path, input_conf = pep735_depsconfig()

    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    expected_conf["sources"]["src1"]["deps"] = out_reqs
    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf


@pytest.mark.parametrize(
    "invalid_deps",
    (
        ['{foo = "bar"}'],
        ['{include-group = "foo", extra_key = []}'],
        ['{extra_key = [], include-group = "foo"}'],
    ),
)
def test_pep735_collector_invalid_dep_object_specifiers(
    invalid_deps, pep735_deps, pep735_depsconfig
):
    """
    Collection of PEP735 invalid Dependency Object Specifiers dependencies

    Tables in requirement lists must be valid Dependency Object Specifiers.

    An include is defined as a table with exactly one key, "include-group",
    whose value is a string, the name of another Dependency Group.
    """
    group = "test"

    pep735_deps({group: invalid_deps})
    depsconfig_path, input_conf = pep735_depsconfig(group)

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = (
        "pep735: invalid Dependency Object Specifier ("
        f"group: {group}, include chain: ): "
    )
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "invalid_deps",
    (
        ["{include-group = []}"],
        ["{include-group = 1}"],
        ['{include-group = {foo = "bar"}}'],
    ),
)
def test_pep735_collector_invalid_dep_group_include(
    invalid_deps, pep735_deps, pep735_depsconfig
):
    """
    Collection of PEP735 invalid Dependency Group Include's dependencies

    An include is defined as a table with exactly one key, "include-group",
    whose value is a string, the name of another Dependency Group.
    """
    group = "test"

    pep735_deps({group: invalid_deps})
    depsconfig_path, input_conf = pep735_depsconfig(group)

    with pytest.raises(TypeError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = (
        "pep735: Dependency Group Include's value is not a string ("
        f"group: {group}, include chain: ): "
    )
    assert str(exc.value).startswith(expected_err)

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        (
            {
                "teSt": ['{include-group = "Test"}'],
            },
            "group: teSt, include chain: teSt->teSt",
        ),
        (
            {
                "gRp1": ['{include-group = "Test"}'],
                "teSt": ['{include-group = "grP1"}'],
            },
            "group: teSt, include chain: teSt->gRp1->teSt",
        ),
        (
            {
                "gRp1": ['{include-group = "Grp1"}'],
                "teSt": ['{include-group = "grP1"}'],
            },
            "group: gRp1, include chain: teSt->gRp1->gRp1",
        ),
        (
            {
                "gRp1": ['"b"', '{include-group = "Test"}'],
                "teSt": ['"a"', '{include-group = "grP1"}'],
            },
            "group: teSt, include chain: teSt->gRp1->teSt",
        ),
    ),
)
def test_pep735_collector_include_cycle(
    pep735_deps, pep735_depsconfig, group_data
):
    """
    Collection of PEP735 dependencies with include cycle
    """
    group_config, err_msg = group_data
    pep735_deps(group_config)
    depsconfig_path, input_conf = pep735_depsconfig()

    with pytest.raises(ValueError) as exc:
        deps_command("sync", depsconfig_path, srcnames=[])

    expected_err = f"pep735: include cycle detected ({err_msg})"
    assert str(exc.value) == expected_err

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize("group_data", VALID_INCLUDE_PEP735_DATA)
def test_pep735_collector_valid_dep_group_include(
    pep735_deps, pep735_depsconfig, group_data
):
    """
    Collection of PEP735 valid Dependency Group Include's dependencies
    """
    in_groups, out_reqs = group_data

    pep735_deps(in_groups)
    depsconfig_path, input_conf = pep735_depsconfig()
    deps_command("sync", depsconfig_path, srcnames=[])

    expected_conf = deepcopy(input_conf)
    if out_reqs:
        expected_conf["sources"]["src1"]["deps"] = out_reqs

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == expected_conf

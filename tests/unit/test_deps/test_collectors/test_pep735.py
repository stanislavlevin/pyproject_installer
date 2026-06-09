import json
import re
import sys
from copy import deepcopy

import pytest

from pyproject_installer.deps_cmd import deps_command
from pyproject_installer.lib import dependency_groups

if sys.version_info >= (3, 11):
    RaisesGroup = pytest.RaisesGroup
else:
    from pyproject_installer.lib import errors

    class RaisesGroup:
        """Python-3.10 fallback for ``pytest.RaisesGroup``.

        On 3.10 ``packaging.errors.ExceptionGroup`` is a plain ``Exception``
        subclass (PEP 654 lands in 3.11), so ``pytest.RaisesGroup`` — which
        does ``isinstance(exc, BaseExceptionGroup)`` — refuses to match.
        This shim asserts the same shape (one ``ExceptionGroup`` whose
        ``.exceptions`` are positionally instances of the given types and
        whose ``.message`` matches ``match``) using only the attributes
        packaging's shim provides.
        """

        def __init__(self, *expected_types, match=None):
            self._expected_types = expected_types
            self._match = match
            self._cm = pytest.raises(errors.ExceptionGroup)
            self._info: pytest.ExceptionInfo[errors.ExceptionGroup] | None = (
                None
            )

        def __enter__(self):
            self._info = self._cm.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            handled = self._cm.__exit__(exc_type, exc_val, exc_tb)
            assert self._info is not None
            eg = self._info.value
            if self._match is not None:
                matched = re.search(self._match, eg.message)
                assert (
                    matched
                ), f"message {eg.message!r} does not match {self._match!r}"
            actual = list(eg.exceptions)
            assert len(actual) == len(self._expected_types), (
                f"got {len(actual)} inner exceptions, "
                f"expected {len(self._expected_types)}"
            )
            for got, expected in zip(
                actual,
                self._expected_types,
                strict=True,
            ):
                assert isinstance(got, expected), (
                    f"inner exception {got!r} is not an instance of "
                    f"{expected!r}"
                )
            return handled


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
            },
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

    expected_err = re.escape(
        "pep735: missing dependency-groups table in pyproject.toml",
    )
    expected_err = f"^{expected_err}$"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep735_collector_invalid_type_depgroups(
    pyproject_toml,
    pep735_depsconfig,
):
    """
    Collection of PEP735 dependencies with invalid type of 'dependency-groups'
    """
    pyproject_toml('dependency-groups = "test"\n')
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: Dependency Groups is not a dict: ")
    expected_err = f"^{expected_err}"
    with pytest.raises(TypeError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep735_collector_no_groups(pep735_deps, pep735_depsconfig):
    """
    Collection of PEP735 dependencies with no groups (keys)
    """
    pep735_deps({})
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(LookupError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        {"gp1": []},
        {"teSt": ['{include-group = "gP1"}']},
        {
            "gP1": ['{include-group = "gP2"}'],
            "teSt": ['{include-group = "Gp1"}'],
        },
    ),
)
def test_pep735_collector_missing_group(
    pep735_deps,
    pep735_depsconfig,
    group_data,
):
    """
    Collection of PEP735 dependencies with missing group
    """
    pep735_deps(group_data)
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(LookupError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        {"tesT": [], "Test": []},
        {"gRp": [], "Grp": [], "teSt": ['{include-group = "grP"}']},
        {
            "gRp1": ['{include-group = "grP2"}'],
            "Grp2": [],
            "gRp2": [],
            "teSt": ['{include-group = "grP1"}'],
        },
    ),
)
def test_pep735_collector_duplicate_names(
    pep735_deps,
    pep735_depsconfig,
    group_data,
):
    """
    Collection of PEP735 dependencies with duplicate group names
    """
    pep735_deps(group_data)
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(
        dependency_groups.DuplicateGroupNames,
        match=expected_err,
    ):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_config",
    (
        ["tesT = true"],
        ["gRp = true", 'teSt = [{include-group = "grP"}]'],
        [
            'gRp1 = [{include-group = "grP2"}]',
            "gRp2 = true",
            'teSt = [{include-group = "grP1"}]',
        ],
    ),
)
def test_pep735_collector_invalid_type_groupdeps(
    pyproject_toml,
    pep735_depsconfig,
    group_config,
):
    """
    Collection of PEP735 dependencies with invalid type of group's value
    """
    pyproject_toml("\n".join(("[dependency-groups]", *group_config)) + "\n")
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(TypeError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        {"tesT": ["true"]},
        {"tesT": ['"foo"', "true"]},
        {"gRp": ["true"], "teSt": ['{include-group = "grP"}']},
        {
            "gRp1": ['{include-group = "grP2"}'],
            "Grp2": ["true"],
            "teSt": ['{include-group = "grP1"}'],
        },
    ),
)
def test_pep735_collector_invalid_type_depslist(
    group_data,
    pep735_deps,
    pep735_depsconfig,
):
    """
    Collection of PEP735 dependencies with invalid type of requirement lists

    Requirement lists under dependency-groups may contain strings, tables
    (“dicts” in Python), or a mix of strings and tables.
    """
    pep735_deps(group_data)
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(TypeError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep735_collector_multiple_errors_in_exceptiongroup(
    pep735_deps,
    pep735_depsconfig,
):
    """
    Collection of PEP735 dependencies with several errors in one group

    Packaging accumulates per-item errors and surfaces them together as one
    ExceptionGroup; the wrap preserves every inner exception and prepends
    'pep735: ' to the group's outer message.
    """
    pep735_deps({"test": ["true", "false"]})
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(TypeError, TypeError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


def test_pep735_collector_valid_pep508_deps(
    valid_pep508_data,
    pep735_deps,
    pep735_depsconfig,
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
        ({"tesT": None}, "tesT"),
        ({"gRp": None, "teSt": ['{include-group = "grP"}']}, "gRp"),
        (
            {
                "gRp1": ['{include-group = "grP2"}'],
                "Grp2": None,
                "teSt": ['{include-group = "grP1"}'],
            },
            "Grp2",
        ),
    ),
)
def test_pep735_collector_invalid_pep508_deps(
    pep735_deps,
    pep735_depsconfig,
    invalid_pep508_data,
    group_data,
):
    """
    Collection of PEP735 (invalid PEP508) dependencies

    Strings in requirement lists must be valid Dependency Specifiers, as defined
    in PEP 508.
    """
    group_config, group = group_data
    in_reqs, _ = invalid_pep508_data

    pep735_deps(group_config | {group: [f'"{x}"' for x in in_reqs]})
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with pytest.raises(ValueError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

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
        ({"gp1": ['{include-group = "gp2"}'], "test": ['"foo"']}, ["foo"]),
    ),
)
def test_pep735_collector_not_eagerly_validating(
    group_data,
    pep735_deps,
    pep735_depsconfig,
):
    """
    Collection of PEP735 dependencies should ignore other (not requested) groups

    Tools SHOULD NOT eagerly validate the list contents of all Dependency
    Groups.
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
    invalid_deps,
    pep735_deps,
    pep735_depsconfig,
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

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(
        dependency_groups.InvalidDependencyGroupObject,
        match=expected_err,
    ):
        deps_command("sync", depsconfig_path, srcnames=[])

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
    invalid_deps,
    pep735_deps,
    pep735_depsconfig,
):
    """
    Collection of PEP735 invalid Dependency Group Include's dependencies

    An include is defined as a table with exactly one key, "include-group",
    whose value is a string, the name of another Dependency Group.
    """
    group = "test"

    pep735_deps({group: invalid_deps})
    depsconfig_path, input_conf = pep735_depsconfig(group)

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with pytest.raises(TypeError, match=expected_err):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize(
    "group_data",
    (
        {"teSt": ['{include-group = "Test"}']},
        {
            "gRp1": ['{include-group = "Test"}'],
            "teSt": ['{include-group = "grP1"}'],
        },
        {
            "gRp1": ['{include-group = "Grp1"}'],
            "teSt": ['{include-group = "grP1"}'],
        },
        {
            "gRp1": ['"b"', '{include-group = "Test"}'],
            "teSt": ['"a"', '{include-group = "grP1"}'],
        },
    ),
)
def test_pep735_collector_include_cycle(
    pep735_deps,
    pep735_depsconfig,
    group_data,
):
    """
    Collection of PEP735 dependencies with include cycle
    """
    pep735_deps(group_data)
    depsconfig_path, input_conf = pep735_depsconfig()

    expected_err = re.escape("pep735: ")
    expected_err = f"^{expected_err}"
    with RaisesGroup(
        dependency_groups.CyclicDependencyGroup,
        match=expected_err,
    ):
        deps_command("sync", depsconfig_path, srcnames=[])

    actual_conf = json.loads(depsconfig_path.read_text(encoding="utf-8"))
    assert actual_conf == input_conf


@pytest.mark.parametrize("group_data", VALID_INCLUDE_PEP735_DATA)
def test_pep735_collector_valid_dep_group_include(
    pep735_deps,
    pep735_depsconfig,
    group_data,
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

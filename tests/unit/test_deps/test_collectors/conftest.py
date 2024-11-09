import pytest


VALID_PEP508_DEPS_DATA = (
    ([], []),
    (["foo"], ["foo"]),
    (["foo == 1.0"], ["foo==1.0"]),
    (
        ["foo @ https://example.com/foo.zip"],
        ["foo@ https://example.com/foo.zip"],
    ),
    (["foo [test]"], ["foo[test]"]),
    (["foo [test] > 1.0"], ["foo[test]>1.0"]),
    (["foo [test] > 1.0", "bar"], ["bar", "foo[test]>1.0"]),
    (["Fo_.--o"], ["Fo_.--o"]),
    (["bar", "foo"], ["bar", "foo"]),
    (["foo", "bar"], ["bar", "foo"]),
    (["foo", "bar > 1.0"], ["bar>1.0", "foo"]),
    (
        ["foo", "bar > 1.0; python_version=='1.0'"],
        ['bar>1.0; python_version == "1.0"', "foo"],
    ),
)

INVALID_PEP508_DEPS_DATA = (
    (["_foo"], []),
    (["foo", "bar !> 1.0"], ["foo"]),
    (["foo", "bar > 1.0; invalid_marker=='1.0'"], ["foo"]),
    (["foo", "bar > 1.0; invalid_marker=='1.0'", "foobar"], ["foo", "foobar"]),
)


@pytest.fixture(params=VALID_PEP508_DEPS_DATA)
def valid_pep508_data(request):
    """
    return tuple of two elements,
    first item of them is actual valid PEP508 data (supposed to be collected),
    the second one is data expected to be read from deps config after `sync`.
    """
    yield request.param


@pytest.fixture(params=INVALID_PEP508_DEPS_DATA)
def invalid_pep508_data(request):
    """
    return tuple of two elements,
    first item of them is actual invalid PEP508 data (supposed to be collected),
    the second one is data expected to be read from deps config after `sync` if
    invalid dependency specifiers are allowed by a collector.
    """
    yield request.param

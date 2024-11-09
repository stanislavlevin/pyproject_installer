import pytest


PEP508_DEPS_DATA = (
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
    (["_foo"], []),
    (["foo", "bar !> 1.0"], ["foo"]),
    (["foo", "bar > 1.0; invalid_marker=='1.0'"], ["foo"]),
)

@pytest.fixture(params=PEP508_DEPS_DATA)
def deps_data(request):
    yield request.param

import pytest

VALID_REQUIRES_PYTHON_DATA: tuple[tuple[str, dict[str, str]], ...] = (
    (">= 3.6", {"requires_python": ">=3.6"}),
    ("> 3.6", {"requires_python": ">3.6"}),
    (">=3.6, <4", {"requires_python": "<4,>=3.6"}),
    ("~=3.6", {"requires_python": "~=3.6"}),
    ("==3.6.*", {"requires_python": "==3.6.*"}),
    (">=3.12, <4", {"requires_python": "<4,>=3.12"}),
)


@pytest.fixture(params=VALID_REQUIRES_PYTHON_DATA)
def valid_requires_python_data(
    request: pytest.FixtureRequest,
) -> tuple[str, dict[str, str]]:
    """Return the Python requirement and the expected stored constraint."""
    result: tuple[str, dict[str, str]] = request.param
    return result

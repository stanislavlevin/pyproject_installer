import contextlib

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from .._vendor import tomli as tomllib

from .._vendor.packaging import markers, requirements, specifiers

__all__ = [
    "is_pep508_requirement",
    "markers",
    "requirements",
    "specifiers",
    "tomllib",
]


def is_pep508_requirement(requirement):
    """
    Returns True if string requirement is valid PEP508 specifier
    https://packaging.python.org/en/latest/specifications/dependency-specifiers/#dependency-specifiers
    """
    with contextlib.suppress(requirements.InvalidRequirement):
        requirements.Requirement(requirement)
        return True

    return False

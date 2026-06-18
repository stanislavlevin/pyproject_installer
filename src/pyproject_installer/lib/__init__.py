import contextlib
import sys

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    from .._vendor import tomli as tomllib

from .._vendor.packaging import (
    dependency_groups,
    errors,
    markers,
    metadata,
    requirements,
    specifiers,
    utils,
)

__all__ = [
    "dependency_groups",
    "errors",
    "is_pep508_requirement",
    "markers",
    "metadata",
    "requirements",
    "specifiers",
    "tomllib",
    "utils",
]


def is_pep508_requirement(requirement: str) -> bool:
    """
    Returns True if string requirement is valid PEP508 specifier
    https://packaging.python.org/en/latest/specifications/dependency-specifiers/#dependency-specifiers
    """
    with contextlib.suppress(requirements.InvalidRequirement):
        requirements.Requirement(requirement)
        return True

    return False

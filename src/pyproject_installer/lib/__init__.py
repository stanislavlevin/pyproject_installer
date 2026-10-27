import contextlib
import tomllib

from .._vendor.packaging import (
    dependency_groups,
    markers,
    metadata,
    requirements,
    specifiers,
    utils,
)

__all__ = [
    "dependency_groups",
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

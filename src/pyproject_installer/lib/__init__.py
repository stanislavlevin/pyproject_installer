try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from .._vendor import tomli as tomllib

from .._vendor.packaging import markers, requirements, specifiers

__all__ = [
    "markers",
    "requirements",
    "specifiers",
    "tomllib",
]

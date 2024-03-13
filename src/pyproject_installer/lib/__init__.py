try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from .._vendor import tomli as tomllib

from .._vendor.packaging import requirements, markers, specifiers

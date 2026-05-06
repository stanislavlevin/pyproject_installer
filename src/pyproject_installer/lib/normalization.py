from . import utils


def pep503_normalized_name(name: str) -> utils.NormalizedName:
    """
    PEP503 normalized names
    https://peps.python.org/pep-0503/#normalized-names
    """
    return utils.canonicalize_name(name)

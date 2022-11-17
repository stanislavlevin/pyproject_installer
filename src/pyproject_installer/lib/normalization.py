import re


def pep503_normalized_name(name):
    """
    PEP503 normalized names
    https://peps.python.org/pep-0503/#normalized-names
    """
    return re.sub(r"[-_.]+", "-", name).lower()

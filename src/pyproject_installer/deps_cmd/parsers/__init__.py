from .pep517 import Pep517Parser
from .pep518 import Pep518Parser
from .pip_reqfile import PipReqFileParser
from .metadata import MetadataParser


__all__ = ["parser"]

SUPPORTED_PARSERS = {
    cls.name: cls for cls in [
        Pep517Parser,
        Pep518Parser,
        PipReqFileParser,
        MetadataParser,
    ]
}


def get_parser(name):
    try:
        return SUPPORTED_PARSERS[name]
    except KeyError:
        return None

from .pep517 import Pep517Collector
from .pep518 import Pep518Collector
from .pip_reqfile import PipReqFileCollector
from .metadata import MetadataCollector


__all__ = ["parser"]

SUPPORTED_COLLECTORS = {
    cls.name: cls for cls in [
        Pep517Collector,
        Pep518Collector,
        PipReqFileCollector,
        MetadataCollector,
    ]
}


def get_collector(name):
    try:
        return SUPPORTED_COLLECTORS[name]
    except KeyError:
        return None

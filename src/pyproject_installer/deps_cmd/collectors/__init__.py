from .pep517 import Pep517Collector
from .pep518 import Pep518Collector
from .pip_reqfile import PipReqFileCollector
from .metadata import MetadataCollector
from .poetry import PoetryCollector
from .tox import ToxCollector
from .hatch import HatchCollector
from .pdm import PdmCollector


__all__ = ["get_collector", "SUPPORTED_COLLECTORS"]

SUPPORTED_COLLECTORS = {
    cls.name: cls
    for cls in [
        Pep517Collector,
        Pep518Collector,
        MetadataCollector,
        PipReqFileCollector,
        PoetryCollector,
        ToxCollector,
        HatchCollector,
        PdmCollector,
    ]
}


def get_collector(name):
    try:
        return SUPPORTED_COLLECTORS[name]
    except KeyError:
        return None

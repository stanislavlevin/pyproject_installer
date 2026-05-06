from .collector import Collector
from .hatch import HatchCollector
from .metadata import MetadataCollector
from .pdm import PdmCollector
from .pep517 import Pep517Collector
from .pep518 import Pep518Collector
from .pep735 import Pep735Collector
from .pip_reqfile import PipReqFileCollector
from .pipenv import PipenvCollector
from .poetry import PoetryCollector
from .tox import ToxCollector

__all__ = ["SUPPORTED_COLLECTORS", "get_collector"]

# Lifted out of the dict comprehension so mypy infers type[Collector],
# not ABCMeta.
_COLLECTOR_CLASSES: list[type[Collector]] = [
    Pep517Collector,
    Pep518Collector,
    MetadataCollector,
    PipReqFileCollector,
    PoetryCollector,
    ToxCollector,
    HatchCollector,
    PdmCollector,
    PipenvCollector,
    Pep735Collector,
]

SUPPORTED_COLLECTORS = {cls.name: cls for cls in _COLLECTOR_CLASSES}


def get_collector(name: str) -> type[Collector] | None:
    try:
        return SUPPORTED_COLLECTORS[name]
    except KeyError:
        return None

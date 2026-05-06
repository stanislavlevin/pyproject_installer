from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar


class Collector(ABC):
    name: ClassVar[str]

    @abstractmethod
    def collect(self) -> Iterator[str]:
        """Implements collecting list of dependencies from sources"""

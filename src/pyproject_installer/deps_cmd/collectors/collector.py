from abc import ABC, abstractmethod


class Collector(ABC):
    name = None

    @abstractmethod
    def collect(self):
        """Implements collecting list of dependencies from sources"""

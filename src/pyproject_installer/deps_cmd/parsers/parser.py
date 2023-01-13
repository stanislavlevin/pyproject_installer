from abc import ABC, abstractmethod


class Parser(ABC):
    name = None

    @abstractmethod
    def parse(self):
        """Implements parsing of source"""

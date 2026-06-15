from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar


class Collector(ABC):
    name: ClassVar[str]

    @abstractmethod
    def collect(self) -> Iterator[str]:
        """Implements collecting list of dependencies from sources"""

    def eval_env(self) -> dict[str, str]:
        """Marker environment this source contributes at eval time.

        Returns a mapping of PEP 508 marker variables to values (for
        example ``{"extra": "tests"}``). During ``eval`` it is merged
        into the marker environment used to evaluate this source's
        stored dependencies, and it takes precedence over a value
        passed on the command line (such as ``--extra``). Only the
        variables present in the returned mapping are set; everything
        else in the environment is left at its default, so unrelated
        markers (``python_version``, ``sys_platform``, ...) still
        evaluate against the current environment. The contribution
        only decides which dependencies are kept; it does not rewrite
        the dependency strings that are printed.

        Default: an empty mapping, i.e. no contribution. A collector
        that records a fixed marker variable (for example an extra)
        overrides this.
        """
        return {}

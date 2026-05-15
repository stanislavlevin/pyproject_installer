"""Generator that filters wheel member paths via fnmatch glob patterns."""

import fnmatch
import logging
from collections.abc import Iterable, Iterator, Sequence

__all__ = ["filter_exclude_paths"]

logger = logging.getLogger(__name__)


def filter_exclude_paths(
    members: Iterable[str],
    *,
    patterns: Sequence[str],
) -> Iterator[str]:
    """Yield members whose path matches no fnmatch pattern.

    Patterns are matched against the wheel's ZIP ``namelist()`` entries
    verbatim via ``fnmatch.fnmatchcase``. Those entries are always
    forward-slash separated POSIX paths with no leading ``/`` and no
    ``./`` prefix, regardless of host operating system (e.g.
    ``pkg/foo.py``, ``pkg-1.0.dist-info/METADATA``).

    Scope: wheel members only. Content synthesised downstream by the
    install pipeline (console-script wrappers from ``entry_points.txt``,
    ``INSTALLER`` written by ``--installer``, ``.pyc`` files produced
    by an external bytecompile step) is not subject to these patterns.

    No hard-coded exceptions: every member is subject to the supplied
    patterns. System-level policy for dist-info contents lives upstream
    in ``filter_dist_info``. An empty ``patterns`` is a no-op (every
    member is yielded); ``install_wheel`` skips calling this function
    entirely when ``exclude_paths`` is empty.
    """
    for m in members:
        if any(fnmatch.fnmatchcase(m, p) for p in patterns):
            logger.debug("Excluding %s", m)
            continue
        yield m

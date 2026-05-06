import re
from collections.abc import Iterator
from pathlib import Path

from ...lib import is_pep508_requirement
from .collector import Collector


class PipReqFileCollector(Collector):
    """Parses pip's requirements file

    Specification:
    - https://pip.pypa.io/en/stable/reference/requirements-file-format/#requirements-file-format
    Limitations:
    - supported only PEP508 requirements
    - line continuations are not supported
    - inline options are not supported
    """

    name = "pip_reqfile"

    def __init__(self, reqfile: str | Path) -> None:
        self.reqfile = Path(reqfile)

    def collect(self) -> Iterator[str]:
        # see pip._internal.req.req_file.ignore_comments
        comment_re = re.compile(r"(^|\s+)#.*$")

        def _parse_pip_reqline(line: str) -> str:
            return comment_re.sub("", line).strip()

        with self.reqfile.open(encoding="utf-8") as f:
            yield from filter(is_pep508_requirement, map(_parse_pip_reqline, f))

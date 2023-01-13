from pathlib import Path
import re

from .collector import Collector
from ...lib import requirements


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

    def __init__(self, reqfile):
        self.reqfile = Path(reqfile)

    def collect(self):
        with self.reqfile.open(encoding="utf-8") as f:
            for line in f:
                # see pip._internal.req.req_file.ignore_comments
                comment_re = re.compile(r"(^|\s+)#.*$")
                line = comment_re.sub("", line)
                line = line.strip()
                try:
                    requirements.Requirement(line)
                except requirements.InvalidRequirement:
                    continue
                else:
                    yield line

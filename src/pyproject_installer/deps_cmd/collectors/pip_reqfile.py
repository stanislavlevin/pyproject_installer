from pathlib import Path
import re

from packaging.requirements import Requirement, InvalidRequirement

from .collector import Collector


class PipReqFileCollector(Collector):
    """Parses pip's requirements file

    - format:
      https://pip.pypa.io/en/stable/reference/requirements-file-format/#requirements-file-format
    - supported only PEP508 requirements
    - line continuations are not supported for now,
      see pip._internal.req.req_file.join_lines for details
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
                    Requirement(line)
                except InvalidRequirement:
                    continue
                else:
                    yield line

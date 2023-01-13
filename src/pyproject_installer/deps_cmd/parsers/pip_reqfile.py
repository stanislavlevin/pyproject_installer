from pathlib import Path

from packaging.requirements import Requirement, InvalidRequirement

from .parser import Parser


class PipReqFileParser(Parser):
    """Parses pip's requirements file

    - format:
    https://pip.pypa.io/en/stable/reference/requirements-file-format/#requirements-file-format
    - supported only PEP508 requirements
    - line continuations are not supported for now,
      see pip._internal.req.req_file.join_lines for details
    """
    name = "pip_reqfile"

    def __init__(self, reqfile):
        super().__init__()
        self.reqfile = Path(reqfile)

    def parse(self):
        parsed_reqs = []
        with self.reqfile.open(encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                try:
                    parsed_req = Requirement(line)
                except InvalidRequirement:
                    continue
                else:
                    parsed_reqs.append(line)
        return parsed_reqs

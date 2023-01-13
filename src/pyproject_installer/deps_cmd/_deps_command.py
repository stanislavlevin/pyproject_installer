import json
import sys

from .parsers import get_parser

def deps_command(groups, file):
    unique_groups = set([g[0] for g in groups])
    deps = {g: [] for g in unique_groups}
    for group in groups:
        parser_group, parser_name, *parser_args = group
        parser_cls = get_parser(parser_name)
        if parser_cls is None:
            raise ValueError(f"Unsupported parser type: {parser_name!r}")
        parser = parser_cls(*parser_args)
        deps[parser_group].extend(parser.parse())

    out = json.dumps(deps, indent=2) + "\n"
    if file is not None:
        file.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)

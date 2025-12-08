import logging

logger = logging.getLogger(__name__)


SCRIPT_TEMPLATE = """\
{shebang}

import sys

from {module} import {attr}


if __name__ == "__main__":
    sys.exit({main}())
"""
SHEBANG_LENGTH_LIMIT = 127


def build_shebang(executable):
    """
    man 2 execve
    The kernel imposes a maximum length on the text that follows the
    "#!" characters at the start of a script; characters beyond the
    limit are ignored. Before Linux 5.1, the limit is 127 characters.
    Since Linux 5.1, the limit is 255 characters.
    """
    if " " not in executable and len(executable) <= SHEBANG_LENGTH_LIMIT:
        return f"#!{executable}"

    # originally taken from distlib.scripts; how it works:
    # https://github.com/pradyunsg/installer/pull/4#issuecomment-623668717
    return "#!/bin/sh\n'''exec' " + executable + ' "$0" "$@"\n' + "' '''"


def generate_entrypoints_scripts(distr, python, scriptsdir, destdir):
    """
    Optional entry_points
    https://packaging.python.org/en/latest/specifications/entry-points/
    """
    for ep_group in ("console_scripts", "gui_scripts"):
        for ep in distr.entry_points.select(group=ep_group):
            logger.debug("Installing console script: %s", ep.name)
            script_text = SCRIPT_TEMPLATE.format(
                shebang=build_shebang(python),
                module=ep.module,
                attr=ep.attr.split(".", maxsplit=1)[0],
                main=ep.attr,
            )
            rootdir = destdir / scriptsdir.relative_to(scriptsdir.root)
            rootdir.mkdir(parents=True, exist_ok=True)
            script_path = rootdir / ep.name
            script_path.write_text(script_text, encoding="utf-8")
            script_path.chmod(script_path.stat().st_mode | 0o555)

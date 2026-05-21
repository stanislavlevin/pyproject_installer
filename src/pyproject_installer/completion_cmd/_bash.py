"""Emit the bash completion script.

The script is a fixed shim that calls ``pyproject-installer`` back at
TAB time; ``cli_entry`` detects the sentinel env var and routes to
:func:`._autocomplete.run_autocomplete`, which computes the
candidates. See ``docs/designs/bash_completion.md`` for the rationale.
"""

import sys

SCRIPT_TEMPLATE = """\
_pyproject_installer()
{
    local IFS=$' \\t\\n'
    COMPREPLY=( $( COMP_WORDS="${COMP_WORDS[*]}" \\
                   COMP_CWORD=$COMP_CWORD \\
                   _PYPROJECT_INSTALLER_COMPLETE=1 "$1" 2>/dev/null ) )
}
complete -o nosort -F _pyproject_installer pyproject-installer
"""


def emit() -> None:
    """Write the bash completion script to stdout."""
    sys.stdout.write(SCRIPT_TEMPLATE)

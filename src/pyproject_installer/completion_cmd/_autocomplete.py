"""Runtime bash-completion handler.

Called by ``cli_entry`` when the bash wrapper sets
``_PYPROJECT_INSTALLER_COMPLETE=1``. Reads ``COMP_WORDS`` /
``COMP_CWORD``, prints candidates to stdout, exits. See
``docs/designs/bash_completion.md`` for the rationale.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn


def _path_candidates(current_word: str, *, dirs_only: bool) -> list[str]:
    """Filesystem paths matching ``current_word`` as prefix.

    Directories get a trailing ``/`` so bash treats them as continuation
    points; files are filtered out when ``dirs_only`` is True.

    Examples (cwd contains ``dir_a/``, ``dir_b/``, ``file_c``):

        _path_candidates("",     dirs_only=False) -> dir_a/, dir_b/, file_c
        _path_candidates("",     dirs_only=True)  -> dir_a/, dir_b/
        _path_candidates("dir_", dirs_only=True)  -> dir_a/, dir_b/
        _path_candidates("src/", dirs_only=False) -> src/<name>, ...
    """
    head, sep, name_prefix = current_word.rpartition(os.sep)
    parent = Path(head) if head else Path()
    try:
        matches = sorted(parent.glob(name_prefix + "*"))
    except OSError:
        return []
    result = []
    for match in matches:
        display = f"{head}{sep}{match.name}" if sep else match.name
        if match.is_dir():
            result.append(display + "/")
        elif not dirs_only:
            result.append(display)
    return result


def _value_candidates(
    action: argparse.Action,
    current_word: str,
) -> list[str]:
    """Candidates for an argument's VALUE.

    Priority: ``action.choices`` -> path completion driven by
    ``action.metavar`` -> empty. The metavar string is consulted
    case-insensitively: ``DIR`` means directories, ``FILE`` or
    ``PATH`` means files. Other (or absent) metavar means opaque
    string -> no candidates (bash offers nothing, no misleading
    filename fallback).

    To enable directory or file completion for a new option, just
    declare ``metavar="DIR"`` or ``metavar="FILE"`` on its
    ``add_argument`` call.
    """
    if action.choices:
        return sorted(str(c) for c in action.choices)
    metavar = action.metavar
    # argparse allows tuple metavars (per-position, for nargs > 1).
    # Only the single-string form drives path completion here.
    if not isinstance(metavar, str):
        return []
    metavar = metavar.upper()
    if metavar == "DIR":
        return _path_candidates(current_word, dirs_only=True)
    if metavar in ("FILE", "PATH"):
        return _path_candidates(current_word, dirs_only=False)
    return []


def _find_subparsers_action(
    parser: argparse.ArgumentParser,
) -> "argparse._SubParsersAction[argparse.ArgumentParser] | None":
    """Return *parser*'s SubParsersAction, or None if it has no subparsers.

    The SubParsersAction is the special argparse action registered by
    ``parser.add_subparsers()``; its ``.choices`` dict maps subcommand
    name -> child parser, which :func:`_find_active_parser` walks into.
    """
    return next(
        (
            a
            for a in parser._actions  # noqa: SLF001
            if isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
        ),
        None,
    )


def _find_active_parser(
    parser: argparse.ArgumentParser,
    typed_words: list[str],
) -> tuple[argparse.ArgumentParser, list[str]]:
    """Find which parser the cursor is currently inside.

    Reads *typed_words* left-to-right; each word that names a subparser
    on the current parser steps into that subparser. The walk stops at
    the first word that ISN'T a subparser name (or when the current
    parser has no subparsers); everything from that point on is the
    active parser's own argv.

    Returns ``(active_parser, parser_argv)``.

    Examples (for a parser tree ``root -> {build, install, deps}``
    and ``deps -> {add, show, sync}``)::

        typed_words=[]                    -> (root, [])
        typed_words=["bui"]               -> (root, ["bui"])
            # "bui" isn't a subparser name; root keeps it
        typed_words=["build"]             -> (build_parser, [])
        typed_words=["build", "--outdir", "/tmp"]
                                  -> (build_parser, ["--outdir", "/tmp"])
        typed_words=["deps", "add", "myname"]
                                  -> (add_parser, ["myname"])
            # Walks root -> deps -> add, leaves "myname" as add's argv
        typed_words=["unknown"]           -> (root, ["unknown"])
            # Unknown subcommand: walk stops immediately
    """
    active_parser = parser
    i = 0
    while i < len(typed_words):
        subparser_action = _find_subparsers_action(active_parser)
        if (
            subparser_action is None
            or typed_words[i] not in subparser_action.choices
        ):
            break
        active_parser = subparser_action.choices[typed_words[i]]
        i += 1
    return active_parser, typed_words[i:]


def _value_taking_options(
    parser: argparse.ArgumentParser,
) -> list[argparse.Action]:
    """Options on *parser* that take a value (not store_true/count/etc.)."""
    # argparse nargs for an action that consumes no value words.
    # Naming the literal sidesteps pylint C1805; `not a.nargs` would be
    # wrong because nargs can also be None ("exactly one") or "?"/"*"/"+",
    # all falsey.
    no_value = 0
    return [
        a
        for a in parser._actions  # noqa: SLF001
        if a.option_strings and a.nargs != no_value
    ]


def _option_names(parser: argparse.ArgumentParser) -> list[str]:
    """Sorted list of every option string on *parser* (long + short)."""
    return sorted(
        {
            opt
            for a in parser._actions  # noqa: SLF001
            if not isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
            for opt in a.option_strings
        },
    )


# Argparse actions designed for repeated use on a single command line.
# `append`, `append_const`, `count`, `extend` accumulate across uses;
# everything else (store, store_true/false/const, help, version, ...) is
# single-shot - a second occurrence either overrides the first or is a
# no-op, so the completion handler stops offering them once they're typed.
_REPEATABLE_ACTIONS: tuple[type[argparse.Action], ...] = (
    argparse._AppendAction,  # noqa: SLF001
    argparse._AppendConstAction,  # noqa: SLF001
    argparse._CountAction,  # noqa: SLF001
    argparse._ExtendAction,  # noqa: SLF001
)

# Argparse actions that print and call ``parser.exit()`` immediately.
# Once one of these is on the line, the binary will exit before reaching
# anything the user might type next, so completion offers nothing.
_TERMINATING_ACTIONS: tuple[type[argparse.Action], ...] = (
    argparse._HelpAction,  # noqa: SLF001
    argparse._VersionAction,  # noqa: SLF001
)


def _has_terminating_option(
    parser: argparse.ArgumentParser,
    parser_argv: list[str],
) -> bool:
    """Whether *parser_argv* contains a help-style terminating option."""
    return any(
        opt in parser_argv
        for action in parser._actions  # noqa: SLF001
        if isinstance(action, _TERMINATING_ACTIONS)
        for opt in action.option_strings
    )


def _option_name_candidates(
    parser: argparse.ArgumentParser,
    parser_argv: list[str],
) -> list[str]:
    """Option names already on the line or rejected by argparse are dropped.

    Two suppression rules apply:

    1. Mutually-exclusive groups: if any member of a group is already
       on the command line, every member is dropped - siblings because
       argparse would reject them, and the typed member itself because
       re-offering it is misleading (re-typing a store_true does
       nothing; re-typing a value option just creates clutter).
    2. Non-repeatable single-shot options: any option whose action
       isn't one of ``append``/``append_const``/``count``/``extend``
       is dropped from the candidate list once it (or any of its
       aliases) appears in *parser_argv*. So once ``--help`` has
       been typed, neither ``--help`` nor ``-h`` is offered again;
       but ``count``-style ``-v`` stays available so the user can
       stack ``-v -v``.

    Generic over all parsers.
    """
    suppressed: set[str] = set()
    for group in parser._mutually_exclusive_groups:  # noqa: SLF001
        members = [
            list(a.option_strings)
            for a in group._group_actions  # noqa: SLF001
            if a.option_strings
        ]
        any_present = any(
            opt in parser_argv for member in members for opt in member
        )
        if any_present:
            suppressed.update(opt for member in members for opt in member)
    for action in parser._actions:  # noqa: SLF001
        if not action.option_strings:
            continue
        if isinstance(action, _REPEATABLE_ACTIONS):
            continue
        if any(opt in parser_argv for opt in action.option_strings):
            suppressed.update(action.option_strings)
    return [f for f in _option_names(parser) if f not in suppressed]


def _positional_candidates(
    parser: argparse.ArgumentParser,
    parser_argv: list[str],
    value_option_names: set[str],
    current_word: str,
) -> list[str]:
    """Candidates for the current positional slot.

    Counts non-option words in *parser_argv* (skipping the word that
    immediately follows any value-taking option) to determine the cursor's
    slot index, then dispatches to that slot's action. Beyond the fixed
    slots a trailing variadic positional (``nargs in {"*","+"}``)
    absorbs every remaining slot.
    """
    positionals = [
        a
        for a in parser._actions  # noqa: SLF001
        if not a.option_strings
        and not isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
    ]
    if not positionals:
        return []

    slot = 0
    skip_next = False
    past_double_dash = False
    for word in parser_argv:
        if skip_next:
            skip_next = False
            continue
        # The first bare ``--`` ends option parsing in argparse; every
        # word after it is positional even if it looks option-like.
        if word == "--" and not past_double_dash:
            past_double_dash = True
            continue
        if not past_double_dash and word.startswith("-"):
            skip_next = word in value_option_names
            continue
        slot += 1

    if slot < len(positionals):
        return _value_candidates(positionals[slot], current_word)
    if positionals[-1].nargs in ("*", "+"):
        return _value_candidates(positionals[-1], current_word)
    return []


def compute_candidates(
    parser: argparse.ArgumentParser,
    command_words: list[str],
    current_word_index: int,
) -> list[str]:
    """Compute candidate completions for one TAB press.

    Pure function: given the command_words array (COMP_WORDS, split on
    whitespace) and the cursor index (COMP_CWORD), returns the candidates
    that match the current word's prefix.

    Four-way dispatch on context:

    1. ``prev_word`` is a value-taking option -> complete that option's VALUE.
    2. ``current_word`` starts with ``-`` -> option names
       (mutually-exclusive siblings suppressed).
    3. Active parser has subparsers -> subcommand names + parent option names.
    4. Otherwise -> positional slot dispatch, falling back to option
       names when there's no positional candidate to offer.

    A bare ``--`` already on the line ends option parsing (argparse
    convention): once seen, branches 1, 2 and the branch-4 option-name
    fallback all suppress themselves, so completion only offers
    remaining positional candidates (or nothing if those are exhausted).
    """
    n_words = len(command_words)
    current_word = (
        command_words[current_word_index]
        if current_word_index < n_words
        else ""
    )
    prev_word = (
        command_words[current_word_index - 1]
        if 0 < current_word_index <= n_words
        else ""
    )
    active_parser, parser_argv = _find_active_parser(
        parser,
        command_words[1:current_word_index],
    )
    # A help-style action (``--help``, ``--version``) on the line means
    # argparse will print and exit before reaching the cursor; nothing
    # the user types next will run, so offer no candidates.
    if _has_terminating_option(active_parser, parser_argv):
        return []
    value_options = _value_taking_options(active_parser)
    past_double_dash = "--" in parser_argv

    # 1. Value-option context.
    if prev_word.startswith("-") and not past_double_dash:
        option = next(
            (a for a in value_options if prev_word in a.option_strings),
            None,
        )
        if option is not None:
            candidates = _value_candidates(option, current_word)
            return [c for c in candidates if c.startswith(current_word)]

    # 2. Option-name context.
    if current_word.startswith("-") and not past_double_dash:
        candidates = _option_name_candidates(active_parser, parser_argv)
        return [c for c in candidates if c.startswith(current_word)]

    # 3. Subcommand context.
    subparser_action = _find_subparsers_action(active_parser)
    if subparser_action is not None:
        candidates = sorted(
            subparser_action.choices,
        ) + _option_name_candidates(active_parser, parser_argv)
        return [c for c in candidates if c.startswith(current_word)]

    # 4. Positional dispatch, falling back to option names.
    value_option_names = {
        opt for a in value_options for opt in a.option_strings
    }
    candidates = _positional_candidates(
        active_parser,
        parser_argv,
        value_option_names,
        current_word,
    )
    if not candidates and not past_double_dash:
        # No positional to dispatch to (no positionals at all, a FREE
        # positional, or slot past the fixed ones with no variadic).
        # Offer the parser's options instead so the user sees something
        # actionable instead of an empty completion. Past a bare ``--``,
        # argparse rejects further options so the fallback is suppressed.
        candidates = _option_name_candidates(active_parser, parser_argv)
    return [c for c in candidates if c.startswith(current_word)]


def run_autocomplete(parser: argparse.ArgumentParser) -> NoReturn:
    """Entry point invoked from ``cli_entry`` when the env var is set.

    Reads ``COMP_WORDS`` and ``COMP_CWORD`` from the environment, prints
    each candidate from :func:`compute_candidates` on its own line, and
    exits. Bash captures the lines into the ``COMPREPLY`` array
    (newline is in the default ``IFS``); the columnar display you see
    on ``<TAB><TAB>`` is bash's default formatting of that array, not
    how this function emits.

    Exit codes:
      - 0 on success (zero or more candidates printed)
      - 1 if the env vars are missing or malformed
    """
    try:
        command_words = os.environ["COMP_WORDS"].split()
        current_word_index = int(os.environ["COMP_CWORD"])
    except (KeyError, ValueError):
        sys.exit(1)
    candidates = compute_candidates(
        parser,
        command_words,
        current_word_index,
    )
    for candidate in candidates:
        sys.stdout.write(candidate + "\n")
    sys.exit(0)

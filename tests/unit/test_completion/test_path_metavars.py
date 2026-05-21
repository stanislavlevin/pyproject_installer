"""Every Path-typed CLI argument must declare a path-flavored metavar.

The autocomplete dispatcher in ``completion_cmd/_autocomplete.py`` picks
filesystem candidates by reading ``action.metavar``: ``DIR`` -> dirs,
``FILE``/``PATH`` -> files-and-dirs. An ``add_argument(type=Path)`` call
without a path-flavored metavar silently breaks TAB-completion for that
argument because the dispatcher has no signal to offer paths. These
tests walk the live CLI parser and fail the build before such an arg
can land.
"""

import argparse
from pathlib import Path

import pytest

from pyproject_installer.__main__ import main_parser

PATH_METAVARS = frozenset({"DIR", "FILE", "PATH"})


def parser_actions(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """Every action reachable from *parser*, recursing into subparsers."""
    actions = list(parser._actions)  # noqa: SLF001
    for action in parser._actions:  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            for child in action.choices.values():
                actions.extend(parser_actions(child))
    return actions


@pytest.fixture(scope="module")
def path_actions() -> list[argparse.Action]:
    """Every ``type=Path`` action reachable from the live CLI parser."""
    parser = main_parser(prog="pyproject-installer")
    return [a for a in parser_actions(parser) if a.type is Path]


def test_cli_has_path_typed_actions(
    path_actions: list[argparse.Action],
) -> None:
    """The CLI declares some Path-typed arguments.

    Guards against a refactor that silently strips them all and makes
    the metavar rule below vacuously true (no actions to check).
    """
    assert path_actions, "expected the CLI to declare type=Path arguments"


def test_path_typed_actions_declare_path_metavar(
    path_actions: list[argparse.Action],
) -> None:
    """Every ``type=Path`` action declares a path-flavored metavar.

    Without ``metavar in {DIR, FILE, PATH}`` the completion dispatcher
    has no signal to offer filesystem candidates for that argument -
    TAB silently returns nothing.
    """
    actions_missing_metavar = [
        (a.option_strings or [a.dest], a.metavar)
        for a in path_actions
        if a.metavar not in PATH_METAVARS
    ]
    assert not actions_missing_metavar, (
        "type=Path actions missing a path-flavored metavar "
        f"(must be one of {sorted(PATH_METAVARS)}): {actions_missing_metavar}"
    )

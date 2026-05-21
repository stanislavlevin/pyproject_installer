"""Tests for run_autocomplete from completion_cmd/_autocomplete.py."""

import argparse

import pytest

from pyproject_installer.completion_cmd import _autocomplete as ac


def test_run_autocomplete_missing_comp_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_autocomplete exits 1 when COMP_WORDS is unset."""
    monkeypatch.delenv("COMP_WORDS", raising=False)
    with pytest.raises(SystemExit) as exc:
        ac.run_autocomplete(argparse.ArgumentParser(prog="demo"))
    assert exc.value.code == 1


def test_run_autocomplete_missing_comp_cword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_autocomplete exits 1 when COMP_CWORD is unset."""
    monkeypatch.delenv("COMP_CWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        ac.run_autocomplete(argparse.ArgumentParser(prog="demo"))
    assert exc.value.code == 1


def test_run_autocomplete_malformed_cword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_autocomplete exits 1 when COMP_CWORD isn't a valid integer."""
    monkeypatch.setenv("COMP_WORDS", "demo ")
    monkeypatch.setenv("COMP_CWORD", "not_an_int")
    with pytest.raises(SystemExit) as exc:
        ac.run_autocomplete(argparse.ArgumentParser(prog="demo"))
    assert exc.value.code == 1


def test_run_autocomplete_prints_candidates_and_exits_0(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """run_autocomplete prints one candidate per line and exits 0."""
    monkeypatch.setenv("COMP_WORDS", "demo ")
    monkeypatch.setenv("COMP_CWORD", "1")
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("add")
    sub.add_parser("build")
    with pytest.raises(SystemExit) as exc:
        ac.run_autocomplete(parser)
    # move here for pylint
    success = 0
    assert exc.value.code == success
    # stripping trailing \n
    out = capsys.readouterr().out.rstrip()
    actual = out.split("\n")
    assert actual == ["add", "build", "--help", "-h"]

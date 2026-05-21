"""Tests for argparse parser from completion_cmd/_autocomplete.py."""

import argparse
from pathlib import Path

import pytest

from pyproject_installer.completion_cmd import _autocomplete as ac


@pytest.fixture
def cwd_with_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """tmp_path containing two dirs and one file; chdir into it.

    Used by path-completion tests so the expected candidate list is
    deterministic instead of depending on the host cwd.
    """
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "file_c").touch()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(scope="session")
def parser() -> argparse.ArgumentParser:
    """A synthetic parser mirroring the real CLI's shape.

    Includes: top-level global options (-v, -C), a leaf subcommand
    (build) with value-taking options and a Path positional, a subcommand
    with choices (add), a subcommand group (deps) with second-level
    subcommands.
    """
    p = argparse.ArgumentParser(prog="demo")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("-C", dest="cwd", metavar="DIR")
    sub = p.add_subparsers(required=True)

    build = sub.add_parser("build")
    build.add_argument("srcdir", type=Path, nargs="?", metavar="DIR")
    build.add_argument("--outdir", "-o", type=Path, metavar="DIR")
    build.add_argument("--sdist", action="store_true")

    add = sub.add_parser("add")
    add.add_argument("srctype", choices=("a", "b", "c"))

    deps = sub.add_parser("deps")
    deps.add_argument("--depsconfig", type=Path, metavar="FILE")
    deps_sub = deps.add_subparsers(required=True)
    deps_show = deps_sub.add_parser("show")
    deps_show.add_argument("names", nargs="*")
    deps_sync = deps_sub.add_parser("sync")
    deps_sync.add_argument("--verify", action="store_true")
    return p


@pytest.fixture(scope="session")
def double_dash_parser() -> argparse.ArgumentParser:
    """Parser used by the ``--`` sentinel tests: one FILE positional + opts."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    inst = sub.add_parser("inst")
    inst.add_argument("wheel", type=Path, nargs="?", metavar="FILE")
    inst.add_argument("--destdir", type=Path, metavar="DIR")
    inst.add_argument("--installer")  # opaque value
    return parser


def candidates(parser: argparse.ArgumentParser, words: list[str]) -> list[str]:
    """Compute candidates with cursor at the LAST word (typical TAB)."""
    return ac.compute_candidates(parser, words, len(words) - 1)


def test_compute_top_level_no_input_offers_subcommands_and_options(
    parser: argparse.ArgumentParser,
) -> None:
    """Top-level ``<TAB>`` offers sorted subcommands then option names."""
    assert candidates(parser, ["demo", ""]) == [
        "add",
        "build",
        "deps",
        "--help",
        "--verbose",
        "-C",
        "-h",
        "-v",
    ]


def test_compute_top_level_filter_by_prefix(
    parser: argparse.ArgumentParser,
) -> None:
    """Top-level candidates are filtered by the current word as a prefix."""
    assert candidates(parser, ["demo", "bu"]) == ["build"]


def test_compute_dash_prefix_offers_option_names_only(
    parser: argparse.ArgumentParser,
) -> None:
    """A `-`-prefixed current word offers only option names, not subcommands."""
    # Only the long option names pass the "--" prefix filter; no
    # subcommand names because cur starts with -.
    assert candidates(parser, ["demo", "--"]) == ["--help", "--verbose"]


@pytest.mark.usefixtures("cwd_with_dirs")
def test_compute_dash_c_option_offers_directories(
    parser: argparse.ArgumentParser,
) -> None:
    """Global `-C <TAB>` offers directories (driven by metavar=DIR)."""
    # prev="-C" with metavar="DIR" -> directory completion. cwd is a
    # tmp dir with two dirs and one file; only the dirs (sorted, with
    # trailing /) are offered.
    assert candidates(parser, ["demo", "-C", ""]) == ["dir_a/", "dir_b/"]


@pytest.mark.usefixtures("cwd_with_dirs")
def test_compute_subcommand_value_option_offers_dirs(
    parser: argparse.ArgumentParser,
) -> None:
    """Value-taking option with metavar=DIR offers directory candidates."""
    # `build --outdir <TAB>` -> directory completion in cwd_with_dirs.
    assert candidates(parser, ["demo", "build", "--outdir", ""]) == [
        "dir_a/",
        "dir_b/",
    ]


def test_compute_subcommand_positional_choices_at_slot_zero(
    parser: argparse.ArgumentParser,
) -> None:
    """A subcommand positional with `choices=` completes from those choices."""
    # `add <TAB>` -> slot 0 is `srctype` with choices.
    assert candidates(parser, ["demo", "add", ""]) == ["a", "b", "c"]


def test_compute_subcommand_positional_choices_filtered_by_prefix(
    parser: argparse.ArgumentParser,
) -> None:
    """Positional choices are filtered by the current word's prefix."""
    assert candidates(parser, ["demo", "add", "b"]) == ["b"]


def test_compute_free_positional_falls_back_to_options() -> None:
    """A FREE positional offers no value candidates -> options as fallback."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    leaf = sub.add_parser("foo")
    leaf.add_argument("name")  # FREE positional
    assert candidates(parser, ["demo", "foo", ""]) == ["--help", "-h"]


@pytest.mark.usefixtures("cwd_with_dirs")
def test_compute_value_option_token_is_skipped_for_positional_counter() -> None:
    """Tokens consumed by value-taking options don't count as positionals."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    b = sub.add_parser("b")
    b.add_argument("--outdir", "-o", type=Path, metavar="DIR")
    b.add_argument("srcdir", type=Path, nargs="?", metavar="DIR")
    b.add_argument("kind", choices=("x", "y"))
    # `b --outdir /tmp <TAB>` -> srcdir slot, not kind slot. srcdir
    # is metavar="DIR" so candidates are cwd dirs (cwd_with_dirs).
    typed = ["demo", "b", "--outdir", "/somedir", ""]
    assert candidates(parser, typed) == ["dir_a/", "dir_b/"]


def test_compute_non_repeatable_option_already_typed_is_suppressed(
    parser: argparse.ArgumentParser,
) -> None:
    """A non-repeatable option drops out of candidates once on the line."""
    # --verbose is store_true on the fixture parser; typing it then
    # --<TAB> must NOT re-offer --verbose (or -v alias).
    assert candidates(parser, ["demo", "--verbose", "--"]) == ["--help"]


def test_compute_non_repeatable_option_short_alias_suppresses_long(
    parser: argparse.ArgumentParser,
) -> None:
    """Typing one alias of a non-repeatable option suppresses every alias."""
    # Typing -v (the short alias of --verbose) must also drop --verbose.
    assert candidates(parser, ["demo", "-v", "--"]) == ["--help"]


def test_compute_help_terminates_completion(
    parser: argparse.ArgumentParser,
) -> None:
    """``--help`` makes argparse exit; nothing is reachable after it."""
    assert candidates(parser, ["demo", "--help", ""]) == []
    assert candidates(parser, ["demo", "--help", "-"]) == []
    assert candidates(parser, ["demo", "--help", "build", ""]) == []


def test_compute_short_help_alias_also_terminates(
    parser: argparse.ArgumentParser,
) -> None:
    """``-h`` is the short alias of ``--help``; same terminating effect."""
    assert candidates(parser, ["demo", "-h", ""]) == []


def test_compute_version_terminates_completion() -> None:
    """``--version`` prints and exits; no candidates after it either."""
    # The shared parser fixture has no --version, so build a one-off.
    parser = argparse.ArgumentParser(prog="demo")
    parser.add_argument("--version", action="version", version="0.1")
    parser.add_argument("--other", action="store_true")
    assert candidates(parser, ["demo", "--version", ""]) == []


def test_compute_subparser_help_terminates_completion(
    parser: argparse.ArgumentParser,
) -> None:
    """``--help`` registered on a subparser also terminates dispatch there."""
    # build's own --help -> after walking into build, the check fires.
    assert candidates(parser, ["demo", "build", "--help", ""]) == []
    assert candidates(parser, ["demo", "build", "--help", "--"]) == []


def test_compute_count_action_stays_offered() -> None:
    """``action='count'`` is repeatable -> still offered after first use."""
    parser = argparse.ArgumentParser(prog="demo")
    parser.add_argument("-v", action="count")
    # -v already typed; count actions stack (-v -v -v), so re-offer.
    assert candidates(parser, ["demo", "-v", "-"]) == ["--help", "-h", "-v"]


def test_compute_append_action_stays_offered() -> None:
    """``action='append'`` is repeatable -> still offered after first use."""
    parser = argparse.ArgumentParser(prog="demo")
    parser.add_argument("--tag", action="append")
    # --tag x already typed; append actions accumulate, so re-offer.
    assert candidates(parser, ["demo", "--tag", "x", "--"]) == [
        "--help",
        "--tag",
    ]


def test_compute_store_option_with_value_is_suppressed() -> None:
    """A regular ``store`` option is single-shot -> drops once present."""
    parser = argparse.ArgumentParser(prog="demo")
    parser.add_argument("--outdir")
    # Even though argparse would accept a second --outdir (overrides),
    # completion treats it as non-repeatable to avoid clutter.
    assert candidates(parser, ["demo", "--outdir", "x", "--"]) == ["--help"]


def test_compute_mutually_exclusive_group_is_suppressed_whole() -> None:
    """A present member drops every member of that group (including itself)."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    inst = sub.add_parser("inst")
    g = inst.add_mutually_exclusive_group()
    g.add_argument("--platlib", action="store_true")
    g.add_argument("--purelib", action="store_true")
    inst.add_argument("--other", action="store_true")
    # --purelib gone (sibling argparse would reject); --platlib gone too
    # (re-typing a store_true is pointless); --other unaffected; auto --help.
    assert candidates(parser, ["demo", "inst", "--platlib", "--"]) == [
        "--help",
        "--other",
    ]


def test_compute_subcommand_group_offers_grouped_subcommands(
    parser: argparse.ArgumentParser,
) -> None:
    """`deps <TAB>` offers grouped subcommands then deps's options."""
    assert candidates(parser, ["demo", "deps", ""]) == [
        "show",
        "sync",
        "--depsconfig",
        "--help",
        "-h",
    ]


def test_compute_grouped_subcommand_positional(
    parser: argparse.ArgumentParser,
) -> None:
    """`deps show <TAB>` -> `names` is FREE nargs=*; falls back to options."""
    assert candidates(parser, ["demo", "deps", "show", ""]) == [
        "--help",
        "-h",
    ]


def test_compute_grouped_subcommand_option_completion(
    parser: argparse.ArgumentParser,
) -> None:
    """`deps sync --<TAB>` -> sync's long options (auto --help + --verify)."""
    assert candidates(parser, ["demo", "deps", "sync", "--"]) == [
        "--help",
        "--verify",
    ]


def test_compute_variadic_nargs_star() -> None:
    """nargs='*' last positional absorbs all further slots."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    show = sub.add_parser("show")
    show.add_argument("kind", choices=("a", "b"))
    show.add_argument("names", nargs="*", choices=("x", "y"))
    # Slot 0 = kind
    assert candidates(parser, ["demo", "show", ""]) == ["a", "b"]
    # Slot 1+ = names (variadic)
    assert candidates(parser, ["demo", "show", "a", ""]) == ["x", "y"]
    assert candidates(parser, ["demo", "show", "a", "x", ""]) == ["x", "y"]


def test_compute_missing_env_returns_empty(
    parser: argparse.ArgumentParser,
) -> None:
    """When cword is past the end of words, cur defaults to empty.

    Result is the same as the no-input top-level case: sorted
    subcommands + sorted option names, no prefix filter.
    """
    # cword=5 with only 2 words -> cur=""
    expected = ["add", "build", "deps", "--help", "--verbose", "-C", "-h", "-v"]
    assert ac.compute_candidates(parser, ["demo", ""], 5) == expected


@pytest.mark.usefixtures("cwd_with_dirs")
def test_compute_subcommand_value_option_with_file_metavar_offers_files(
    parser: argparse.ArgumentParser,
) -> None:
    """Value-taking option with metavar=FILE offers dirs AND regular files."""
    # `deps --depsconfig <TAB>` -> FILE completion: dirs (trailing /)
    # AND files (cwd_with_dirs has two dirs and one file).
    assert candidates(parser, ["demo", "deps", "--depsconfig", ""]) == [
        "dir_a/",
        "dir_b/",
        "file_c",
    ]


def test_compute_value_option_with_unknown_metavar_offers_nothing() -> None:
    """A metavar outside DIR/FILE/PATH yields no path candidates."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    leaf = sub.add_parser("show")
    leaf.add_argument("--pattern", metavar="PATTERN")
    # `show --pattern <TAB>` -> opaque string, no completion.
    assert candidates(parser, ["demo", "show", "--pattern", ""]) == []


def test_compute_path_candidates_swallow_oserror(mocker) -> None:
    """Unreadable parent directory yields empty candidates, not a crash."""
    mock_path = mocker.patch.object(ac, "Path")
    mock_path.return_value.glob.side_effect = PermissionError("simulated")
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    leaf = sub.add_parser("show")
    leaf.add_argument("--config", metavar="FILE")
    assert candidates(parser, ["demo", "show", "--config", ""]) == []


def test_compute_positional_in_subcommand_with_no_positionals() -> None:
    """Leaf with only options offers them as the cur='' fallback."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    leaf = sub.add_parser("noargs")
    leaf.add_argument("--option", action="store_true")
    # No positional to dispatch to -> option-name fallback.
    assert candidates(parser, ["demo", "noargs", ""]) == [
        "--help",
        "--option",
        "-h",
    ]


def test_compute_positional_beyond_fixed_slots_falls_back_to_options() -> None:
    """Past last fixed positional with no variadic -> option-name fallback."""
    parser = argparse.ArgumentParser(prog="demo")
    sub = parser.add_subparsers()
    leaf = sub.add_parser("pick")
    leaf.add_argument("one", choices=("a", "b"))
    # Slot 1 is past the only positional; no variadic to absorb ->
    # falls back to option names.
    assert candidates(parser, ["demo", "pick", "a", ""]) == ["--help", "-h"]


@pytest.mark.usefixtures("cwd_with_dirs")
def test_compute_double_dash_then_empty_offers_positional(
    double_dash_parser: argparse.ArgumentParser,
) -> None:
    """``inst -- <TAB>``: cursor past --, wheel slot still empty -> FILE."""
    assert candidates(double_dash_parser, ["demo", "inst", "--", ""]) == [
        "dir_a/",
        "dir_b/",
        "file_c",
    ]


def test_compute_double_dash_then_filled_positional_offers_nothing(
    double_dash_parser: argparse.ArgumentParser,
) -> None:
    """``inst -- some.whl <TAB>``: positional filled, no fallback to options."""
    # Post-`--`, the wheel slot is filled; no more positionals exist
    # and the option-name fallback is suppressed -> empty completion.
    assert (
        candidates(double_dash_parser, ["demo", "inst", "--", "some.whl", ""])
        == []
    )


def test_compute_double_dash_then_option_looking_word_offers_nothing(
    double_dash_parser: argparse.ArgumentParser,
) -> None:
    """Words after ``--`` count as positionals even when option-shaped."""
    # ``--some-file.whl`` is the wheel value (not an option); slot filled.
    assert (
        candidates(
            double_dash_parser,
            ["demo", "inst", "--", "--some-file.whl", ""],
        )
        == []
    )


def test_compute_double_dash_suppresses_option_name_context(
    double_dash_parser: argparse.ArgumentParser,
) -> None:
    """``inst -- --<TAB>``: branch 2 silenced -> empty, not option names."""
    assert candidates(double_dash_parser, ["demo", "inst", "--", "--"]) == []


def test_compute_double_dash_suppresses_value_option_context(
    double_dash_parser: argparse.ArgumentParser,
) -> None:
    """``inst -- --destdir <TAB>``: prev=--destdir is a positional, not opt."""
    # Without --, prev=--destdir would dispatch to directory candidates.
    # Past --, --destdir is the wheel value; slot filled -> empty.
    assert (
        candidates(double_dash_parser, ["demo", "inst", "--", "--destdir", ""])
        == []
    )


@pytest.mark.usefixtures("cwd_with_dirs")
def test_compute_option_before_double_dash_still_consumes_value(
    double_dash_parser: argparse.ArgumentParser,
) -> None:
    """``inst --destdir /tmp -- <TAB>``: value-opt slot ok, wheel still open."""
    # --destdir consumed /tmp (slot counter skips both), then `--` ends
    # option parsing; wheel slot is still empty -> FILE candidates.
    assert candidates(
        double_dash_parser,
        ["demo", "inst", "--destdir", "/somedir", "--", ""],
    ) == ["dir_a/", "dir_b/", "file_c"]

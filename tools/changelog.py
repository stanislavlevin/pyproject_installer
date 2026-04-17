#!/usr/bin/python3
"""Release-time changelog entry generator.

Reads `git log <latest-tag>..HEAD`, filters noise-prefix commits, groups
the rest into Keep a Changelog sections based on subject prefix, and
resolves issue references in commit bodies against the project's tracker
URL (pyproject.toml [project.urls].tracker). Inserts a `## [X.Y.Z] -
YYYY-MM-DD` section at the top of CHANGELOG.md, taking X.Y.Z from the
project's version file and the date as today. If the topmost existing
section already matches the current version, it is replaced (idempotent);
otherwise a new section is prepended.

Usage (release flow): bump the version in `src/pyproject_installer/version.py`,
then run

    python3 tools/changelog.py

to regenerate CHANGELOG.md. Review the output, empty the
`### Need to sort` bucket, then commit + tag the release.

Stdlib only. No imports from the main package.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    # Python 3.10 — reuse the project's vendored tomli under backend/_vendor.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from _vendor import tomli as tomllib  # type: ignore[no-redef]

NOISE_PREFIXES = frozenset(
    {
        "ruff",
        "lint",
        "black",
        "reformat",
        "gha",
        "ci",
        "tests",
        "pylint",
        "docs",
        "readme",
    },
)

NOISE_SUBJECT_PATTERNS = (
    re.compile(r"^release:\s+bump version to "),
    re.compile(r"^Bump version to "),
)

PREFIX_TO_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "vendor": "Changed",
    "maint": "Changed",
    "deps": "Changed",
    "deprecate": "Deprecated",
    "remove": "Removed",
    "security": "Security",
}

SECTION_ORDER = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)

ISSUE_KEYWORDS = (
    r"close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved"
)
ISSUE_SHORTHAND_RE = re.compile(
    rf"\b({ISSUE_KEYWORDS})[:]?\s+#(\d+)\b",
    re.IGNORECASE,
)

_LOG_RECORD_PARTS = 3

VERSION_LITERAL_RE = re.compile(
    r"""^\s*version\s*=\s*["']([^"']+)["']""",
    re.MULTILINE,
)


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _latest_tag() -> str:
    try:
        return _run_git(["describe", "--tags", "--abbrev=0"]).strip()
    except subprocess.CalledProcessError:
        sys.exit("error: no tags in repository")


def _load_pyproject() -> dict:
    with Path("pyproject.toml").open("rb") as f:
        return tomllib.load(f)


def _tracker_url(pyproject: dict) -> str:
    try:
        tracker = pyproject["project"]["urls"]["tracker"]
    except KeyError:
        sys.exit("error: [project.urls].tracker not set in pyproject.toml")
    return tracker.rstrip("/")


def _current_version(pyproject: dict) -> str:
    try:
        version_file = pyproject["tool"]["pyproject_installer"]["backend"][
            "version_file"
        ]
    except KeyError:
        sys.exit(
            "error: [tool.pyproject_installer.backend].version_file not set",
        )
    text = Path(version_file).read_text(encoding="utf-8")
    match = VERSION_LITERAL_RE.search(text)
    if not match:
        sys.exit(f"error: version literal not found in {version_file}")
    return match.group(1)


def _build_url_issue_re(tracker_url: str) -> re.Pattern[str]:
    for scheme in ("https://", "http://"):
        if tracker_url.startswith(scheme):
            rest = tracker_url[len(scheme) :]
            break
    else:
        rest = tracker_url
    return re.compile(
        rf"\b({ISSUE_KEYWORDS})[:]?\s+https?://{re.escape(rest)}/(\d+)/?",
        re.IGNORECASE,
    )


def _extract_issue_numbers(
    body: str,
    url_issue_re: re.Pattern[str],
) -> list[int]:
    nums: list[int] = []
    seen: set[int] = set()
    for match in ISSUE_SHORTHAND_RE.finditer(body):
        n = int(match.group(2))
        if n not in seen:
            seen.add(n)
            nums.append(n)
    for match in url_issue_re.finditer(body):
        n = int(match.group(2))
        if n not in seen:
            seen.add(n)
            nums.append(n)
    return nums


def _extract_prefix(subject: str) -> str:
    head = subject.split(":", 1)[0].strip()
    # scoped prefix like feat(cli) -> feat
    return head.split("(", 1)[0]


def _is_noise(subject: str, prefix: str) -> bool:
    if prefix in NOISE_PREFIXES:
        return True
    return any(p.match(subject) for p in NOISE_SUBJECT_PATTERNS)


def _parse_log(from_ref: str) -> list[tuple[str, str, str]]:
    sep = "\x1e"
    end = "\x1f"
    fmt = f"%H{sep}%s{sep}%b{end}"
    raw = _run_git(["log", f"--format={fmt}", f"{from_ref}..HEAD"])
    entries: list[tuple[str, str, str]] = []
    for raw_record in raw.split(end):
        record = raw_record.strip("\n")
        if not record:
            continue
        parts = record.split(sep, 2)
        if len(parts) != _LOG_RECORD_PARTS:
            continue
        sha, subject, body = parts
        entries.append((sha.strip(), subject.strip(), body))
    return entries


def _render_issue_links(numbers: list[int], tracker_url: str) -> str:
    return ", ".join(f"[#{n}]({tracker_url}/{n})" for n in numbers)


def _format_entry(
    subject: str,
    numbers: list[int],
    tracker_url: str,
    short_sha: str | None,
) -> str:
    suffix = ""
    if numbers:
        suffix = f" ({_render_issue_links(numbers, tracker_url)})"
    prefix_str = f"{short_sha} " if short_sha else ""
    return f"- {prefix_str}{subject}{suffix}"


def _bucket(
    entries: list[tuple[str, str, str]],
    tracker_url: str,
) -> dict[str, list[str]]:
    url_issue_re = _build_url_issue_re(tracker_url)
    buckets: dict[str, list[str]] = {s: [] for s in SECTION_ORDER}
    buckets["Need to sort"] = []

    for sha, subject, body in entries:
        prefix = _extract_prefix(subject)
        if _is_noise(subject, prefix):
            continue

        numbers = _extract_issue_numbers(body, url_issue_re)
        section = PREFIX_TO_SECTION.get(prefix)

        if numbers and section is not None:
            buckets[section].append(
                _format_entry(subject, numbers, tracker_url, None),
            )
        else:
            buckets["Need to sort"].append(
                _format_entry(subject, numbers, tracker_url, sha[:7]),
            )

    return buckets


def _render(buckets: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for section in SECTION_ORDER:
        lines.append(f"### {section}")
        if buckets[section]:
            lines.extend(buckets[section])
        else:
            lines.append("- (none this release)")
        lines.append("")

    if buckets["Need to sort"]:
        lines.append("### Need to sort")
        lines.extend(buckets["Need to sort"])
        lines.append("")

    return "\n".join(lines)


def _write_changelog(version: str, rendered: str) -> None:
    path = Path("CHANGELOG.md")
    text = path.read_text(encoding="utf-8")
    heading = f"## [{version}] - {dt.date.today().isoformat()}"  # noqa: DTZ011

    top = text.find("## [")
    if top < 0:
        # No prior release sections — append after the preamble.
        prelude = text.rstrip() + "\n\n"
        suffix = ""
    else:
        prelude = text[:top]
        line_end = text.find("\n", top)
        topmost = text[top:line_end]
        if topmost.startswith(f"## [{version}]"):
            # Replace the topmost section (idempotent re-runs).
            next_heading = text.find("\n## [", line_end)
            end = len(text) if next_heading < 0 else next_heading + 1
            suffix = text[end:]
        else:
            # Prepend a fresh section above the topmost.
            suffix = text[top:]

    block = f"{heading}\n\n{rendered}"
    if suffix:
        block += "\n"
    path.write_text(prelude + block + suffix, encoding="utf-8")


def main() -> int:
    pyproject = _load_pyproject()
    entries = _parse_log(_latest_tag())
    buckets = _bucket(entries, _tracker_url(pyproject))
    _write_changelog(_current_version(pyproject), _render(buckets))
    return 0


if __name__ == "__main__":
    sys.exit(main())

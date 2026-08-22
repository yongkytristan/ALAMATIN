#!/usr/bin/env python3
"""Check documentation consistency and traceability (ALM-039).

Four checks over every tracked Markdown file:

1. **encoding** — the file decodes as UTF-8. A mixed-encoding file breaks every
   tool that reads it, and it happened once already.
2. **links** — every relative link resolves to a file that exists.
3. **unfinished work** — no `TODO`, `TBD`, `FIXME`, `XXX`, `Lorem ipsum`, or
   angle-bracket placeholder survives. The word "placeholder" in prose is fine;
   an unfilled one is not.
4. **index completeness** — every document is listed in `docs/README.md`, and
   every document the index lists exists.

Usage:
    python scripts/check_documentation.py
    python scripts/check_documentation.py --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "README.md"

SKIP_DIR_PARTS = frozenset({"node_modules", ".next", ".git"})

#: Unambiguous markers of unfinished work. Matched as whole words so ordinary
#: prose about placeholders is not flagged.
UNFINISHED = (
    re.compile(r"\bTODO\b"),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bXXX\b"),
    re.compile(r"(?i)lorem ipsum"),
    # An angle-bracket slot left unfilled in a table cell or a metric line.
    re.compile(r"\|\s*<[a-z_ ]+>\s*\|"),
    re.compile(r"(?i)\b(?:result|value|metric|score)\s*[:=]\s*<[a-z_ ]+>"),
)

LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def tracked_markdown() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    paths = []
    for name in output.split("\0"):
        if not name:
            continue
        path = ROOT / name
        if SKIP_DIR_PARTS & set(Path(name).parts):
            continue
        paths.append(path)
    return paths


def check_file(path: Path) -> list[str]:
    relative = path.relative_to(ROOT).as_posix()
    problems: list[str] = []

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"{relative}: not valid UTF-8 at byte {exc.start}"]

    for index, line in enumerate(text.splitlines(), start=1):
        for pattern in UNFINISHED:
            if pattern.search(line):
                problems.append(
                    f"{relative}:{index}: unfinished marker {pattern.pattern!r}"
                )

    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Strip an anchor and any title.
        cleaned = target.split("#", 1)[0].split(" ", 1)[0].strip()
        if not cleaned:
            continue
        resolved = (path.parent / cleaned).resolve()
        if not resolved.exists():
            problems.append(f"{relative}: broken link {cleaned!r}")
    return problems


def check_index(paths: list[Path]) -> list[str]:
    if not INDEX.is_file():
        return ["docs/README.md is missing; there is no documentation index"]
    text = INDEX.read_text(encoding="utf-8")
    # Targets are resolved to real paths before comparing: the index links to
    # nested documents by path, so matching on filename alone reported listed
    # documents as missing.
    listed_raw = [
        target.split("#", 1)[0].strip()
        for target in LINK.findall(text)
        if not target.startswith(("http", "mailto:", "#"))
    ]
    listed_resolved: set[Path] = set()
    problems: list[str] = []
    for target in listed_raw:
        if not target:
            continue
        resolved = (INDEX.parent / target).resolve()
        if not resolved.exists():
            problems.append(f"docs/README.md: lists missing document {target!r}")
            continue
        listed_resolved.add(resolved)

    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if not relative.startswith("docs/") or path == INDEX:
            continue
        if path.resolve() not in listed_resolved:
            problems.append(f"{relative}: not listed in docs/README.md")
    return problems


def run() -> dict[str, object]:
    paths = tracked_markdown()
    problems: list[str] = []
    for path in paths:
        problems.extend(check_file(path))
    problems.extend(check_index(paths))
    return {
        "documents_checked": len(paths),
        "problem_count": len(problems),
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for problem in report["problems"]:
            print(f"  {problem}")
        print(
            f"checked {report['documents_checked']} documents, "
            f"{report['problem_count']} problem(s)"
        )
    return 1 if report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())

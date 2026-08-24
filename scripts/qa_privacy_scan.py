#!/usr/bin/env python3
"""Scan tracked files for secrets and raw PII (ALM-032).

Runs over the files git tracks, so untracked scratch work and ignored artifacts
are out of scope by construction. Findings are reported by file, line, and rule;
the matched text itself is never printed, because printing it would copy the very
value the scan exists to keep out of logs.

Usage:
    python scripts/qa_privacy_scan.py            # scan tracked files
    python scripts/qa_privacy_scan.py --json     # machine-readable report
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

#: Binary and vendored paths that carry no reviewable source.
SKIP_DIR_PARTS = frozenset(
    {"node_modules", ".next", "__pycache__", ".git", "coverage"}
)
SKIP_SUFFIXES = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".xls", ".xlsx",
        ".pbf", ".safetensors", ".bin", ".pt", ".onnx", ".woff", ".woff2",
    }
)
MAX_BYTES = 6 * 1024 * 1024


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    why: str


SECRET_RULES = (
    Rule(
        "private_key_block",
        re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
        "a private key must never be committed",
    ),
    Rule(
        "aws_access_key_id",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "AWS access key id",
    ),
    Rule(
        "github_token",
        re.compile(r"\b gh[pousr]_[A-Za-z0-9]{36,} \b", re.VERBOSE),
        "GitHub token",
    ),
    Rule(
        "google_api_key",
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        "Google API key, the shape a geocoding provider would use",
    ),
    Rule(
        "slack_token",
        re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b"),
        "Slack token",
    ),
    Rule(
        # Assignment of a credential-looking name to a long literal. Empty
        # values and obvious placeholders are excluded by the pattern itself.
        "assigned_credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|token|credential)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"
        ),
        "a credential assigned to a literal value",
    ),
)

#: Indonesian mobile numbers, the PII shape this project redacts.
PII_RULES = (
    Rule(
        "email_address",
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        "a raw email address",
    ),
    Rule(
        "indonesian_mobile",
        re.compile(r"(?<![\w.+-])(?:\+?62|0)8\d{2}[\s.-]?\d{3,4}[\s.-]?\d{3,5}(?![\w-])"),
        "a raw Indonesian mobile number",
    ),
)

#: Lines that legitimately contain a matching shape. Each entry is a
#: (path suffix, rule name) pair with a stated reason, so an exemption is a
#: recorded decision rather than a silent hole.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("scripts/qa_privacy_scan.py", "assigned_credential"): "the rule patterns themselves",
    ("scripts/qa_privacy_scan.py", "indonesian_mobile"): "the rule patterns themselves",
    ("scripts/qa_privacy_scan.py", "private_key_block"): "the rule patterns themselves",
    ("scripts/qa_privacy_scan.py", "google_api_key"): "the rule patterns themselves",
    ("scripts/qa_privacy_scan.py", "github_token"): "the rule patterns themselves",
    ("scripts/qa_privacy_scan.py", "aws_access_key_id"): "the rule patterns themselves",
    ("scripts/qa_privacy_scan.py", "slack_token"): "the rule patterns themselves",
    ("scripts/qa_privacy_scan.py", "email_address"): "the rule patterns themselves",
    ("tests/test_qa_privacy_scan.py", "indonesian_mobile"): "synthetic separated/prefixed forms proving the rule fires",
    ("tests/test_pii.py", "indonesian_mobile"): "synthetic numbers exercising redaction",
    ("tests/test_build_human_noised_benchmark.py", "indonesian_mobile"): "synthetic number in a test asserting phone-like text is flagged",
    ("tests/test_pipeline.py", "indonesian_mobile"): "one synthetic number in the mixed-PII case",
    ("tests/test_service.py", "indonesian_mobile"): "one synthetic number in the mixed-PII case",
    # Restricted OSM review extract. Two business landmarks (a cafe and a bar)
    # have a phone number mis-entered into tag_addr:housenumber by an
    # OpenStreetMap contributor. Business contact data published under ODbL,
    # not recipient PII, and this file is never published.
    ("data/interim/osm-extraction/landmarks.csv", "indonesian_mobile"): "OSM business phone mis-entered as a housenumber; ODbL business data in a non-redistributed review file",
    ("docs/pii-handling.md", "indonesian_mobile"): "documented example of a redacted number",
    ("docs/integration.md", "indonesian_mobile"): "documented example of a redacted number",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    why: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "line": self.line, "rule": self.rule, "why": self.why}


def tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [ROOT / name for name in output.split("\0") if name]


def scannable(path: Path) -> bool:
    if not path.is_file():
        return False
    if SKIP_DIR_PARTS & set(path.relative_to(ROOT).parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= MAX_BYTES
    except OSError:
        return False


def allowed(relative: str, rule: str) -> bool:
    return (relative, rule) in ALLOWLIST


def scan_text(relative: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for index, line in enumerate(text.splitlines(), start=1):
        for rule in (*SECRET_RULES, *PII_RULES):
            if rule.pattern.search(line) and not allowed(relative, rule.name):
                findings.append(Finding(relative, index, rule.name, rule.why))
    return findings


def scan_repository() -> list[Finding]:
    findings: list[Finding] = []
    for path in tracked_files():
        if not scannable(path):
            continue
        relative = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(relative, text))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args()

    findings = scan_repository()
    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": len(findings),
                    "findings": [item.to_dict() for item in findings],
                    "allowlist_size": len(ALLOWLIST),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for finding in findings:
            # The matched text is deliberately not printed.
            print(f"{finding.path}:{finding.line}: {finding.rule} -- {finding.why}")
        if findings:
            print(f"\n{len(findings)} finding(s).")
        else:
            print("No secrets or raw PII found in tracked files.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

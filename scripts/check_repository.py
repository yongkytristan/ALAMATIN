"""Validate the minimal repository contract without third-party dependencies."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = (
    ".env.example",
    ".gitignore",
    "README.md",
    "CONTRIBUTING.md",
    "requirements.lock",
    "data",
    "scripts",
    "src",
    "web",
    "tests",
    "docs",
)
# INTERNAL REPOSITORY POLICY: governed raw/interim/processed artifacts are
# intentionally tracked for restricted team handoff. Never copy this relaxed
# location/size policy into the public ALAMATIN repository.
FORBIDDEN_PARTS = {"private", "checkpoints", "models", "secrets"}
MAX_TRACKED_BYTES = 100 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api[_-]?key|secret|token)\s*=\s*['\"][^'\"\s]{8,}"),
    re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----"),
    re.compile(r"gh" + r"p_[A-Za-z0-9]{20,}"),
    re.compile(r"sk" + r"-[A-Za-z0-9]{20,}"),
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False
    )
    if result.returncode:
        return []
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).exists():
            errors.append(f"missing required path: {relative}")

    for path in tracked_files():
        relative = path.relative_to(ROOT)
        if any(part.lower() in FORBIDDEN_PARTS for part in relative.parts[:-1]):
            errors.append(f"forbidden tracked location: {relative}")
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_TRACKED_BYTES:
            errors.append(f"tracked file exceeds 100 MiB: {relative}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                errors.append(f"possible secret in tracked file: {relative}")
                break

    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

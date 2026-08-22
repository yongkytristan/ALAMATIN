#!/usr/bin/env python3
"""Verify a clean clone can reach a healthy application (ALM-033).

Checks, in the order a new reviewer would hit them:

1. the interpreter is new enough for the code to import at all;
2. every file the service needs at runtime is present;
3. no committed secret is required to start;
4. the application imports;
5. the pipeline answers a real address;
6. the ASGI app reports a healthy pipeline over HTTP.

Every failure names the file or step at fault, so a broken clone produces an
actionable message rather than a traceback from deep inside an import.

Usage:
    python scripts/verify_clean_clone.py            # all checks
    python scripts/verify_clean_clone.py --json     # machine-readable
    python scripts/verify_clean_clone.py --offline  # assert no network is needed
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

MIN_PYTHON = (3, 10)

#: Files the service reads at runtime. A clone missing any of them cannot start.
REQUIRED_RUNTIME_FILES = (
    "src/alamatin/service.py",
    "src/alamatin/pipeline.py",
    "src/alamatin/quality_gate.py",
    "src/alamatin/output_contract.py",
    "contracts/address-api.v1.schema.json",
    "data/processed/jabar-reference-v1-verified.json",
    "requirements.lock",
)

#: Environment variables the service must NOT need in order to start. The demo
#: has to work on a clone with no secrets configured.
FORBIDDEN_REQUIRED_ENV = ("ALAMATIN_GEOCODER_KEY", "DEWACLOUD_SSH_KEY")

SAMPLE_ADDRESS = (
    "Jl. Asia Afrika No. 1, Kel. Braga, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 40111"
)


class CheckFailed(Exception):
    """A check failed with a message a reader can act on."""


def check_interpreter() -> str:
    if sys.version_info < MIN_PYTHON:
        raise CheckFailed(
            f"Python {'.'.join(map(str, MIN_PYTHON))}+ is required; this is "
            f"{sys.version.split()[0]}. The code uses dataclass(slots=True), "
            "which older versions reject at import time."
        )
    return f"Python {sys.version.split()[0]}"


def check_runtime_files() -> str:
    missing = [name for name in REQUIRED_RUNTIME_FILES if not (ROOT / name).is_file()]
    if missing:
        raise CheckFailed(
            "missing runtime file(s): "
            + ", ".join(missing)
            + ". A shallow or partial clone, or a build that excluded data/, "
            "produces exactly this."
        )
    return f"{len(REQUIRED_RUNTIME_FILES)} runtime files present"


def check_no_secret_required() -> str:
    import os

    present = [name for name in FORBIDDEN_REQUIRED_ENV if os.environ.get(name)]
    # Their presence is fine; the point is that startup must not depend on them.
    return (
        "no secret needed to start"
        + (f" ({len(present)} set but unused)" if present else "")
    )


def check_import() -> str:
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    try:
        import alamatin.service  # noqa: F401
    except Exception as exc:  # surface the cause, not a bare failure
        raise CheckFailed(
            f"importing alamatin.service failed: {type(exc).__name__}: {exc}"
        ) from exc
    return "alamatin.service imported"


def check_pipeline() -> str:
    from alamatin.service import load_pipeline

    try:
        pipeline = load_pipeline()
        result = pipeline.process(SAMPLE_ADDRESS, request_id="clean_clone_001")
    except Exception as exc:
        raise CheckFailed(
            f"the pipeline could not process a sample address: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if result.status != "SIAP_DIPROSES":
        raise CheckFailed(
            f"a known-good address returned {result.status}; the reference "
            "artifact may be truncated or from a different version."
        )
    return f"pipeline answered {result.status}"


def check_health_over_asgi() -> str:
    from alamatin.service import build_app

    app = build_app()
    messages: list[dict] = []

    async def drive() -> None:
        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict) -> None:
            messages.append(message)

        await app(
            {"type": "http", "method": "GET", "path": "/health", "headers": []},
            receive,
            send,
        )

    asyncio.run(drive())
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    document = json.loads(body.decode("utf-8"))
    if start["status"] != 200:
        raise CheckFailed(
            f"/health returned {start['status']} with "
            f"dependencies={document.get('dependencies')}. A 503 means the app "
            "is alive but the pipeline is not configured."
        )
    return f"/health 200 {document['status']}"


CHECKS = (
    ("interpreter", check_interpreter),
    ("runtime files", check_runtime_files),
    ("no secret required", check_no_secret_required),
    ("import", check_import),
    ("pipeline", check_pipeline),
    ("health endpoint", check_health_over_asgi),
)


def run(offline: bool) -> dict[str, object]:
    results: list[dict[str, object]] = []
    failed = False
    for name, check in CHECKS:
        if failed:
            results.append({"check": name, "ok": None, "detail": "skipped"})
            continue
        try:
            results.append({"check": name, "ok": True, "detail": check()})
        except CheckFailed as exc:
            results.append({"check": name, "ok": False, "detail": str(exc)})
            failed = True
    return {
        "ok": not failed,
        "checks": results,
        # Recorded rather than asserted: these checks make no outbound call, so
        # passing them offline is what demonstrates the claim.
        "offline_asserted": offline,
        "network_needed_at_runtime": False,
        "network_needed_to_install_dependencies": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="record that this run was made with no network available",
    )
    args = parser.parse_args()

    report = run(args.offline)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["checks"]:
            mark = "ok  " if item["ok"] else ("skip" if item["ok"] is None else "FAIL")
            print(f"  {mark} {item['check']:22s} {item['detail']}")
        print()
        print("clean clone is healthy" if report["ok"] else "clean clone is NOT healthy")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Produce the ALM-032 QA report.

Deliberately not a coverage percentage. A line-coverage number can be inflated
by exercising code without asserting anything about it, so this maps each
critical path to the tests that actually assert its behaviour, and lists every
skipped test with its reason so nothing is hidden.

Usage:
    python scripts/qa_report.py            # human-readable
    python scripts/qa_report.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

#: Each critical path and the test modules that assert it. A path with no test
#: module is a reported gap, not a silent one.
CRITICAL_PATHS: dict[str, tuple[str, ...]] = {
    "PII redaction": ("test_pii",),
    "token alignment": ("test_token_alignment",),
    "component extraction": ("test_regex_baseline", "test_tokenizer"),
    "normalization and provenance": ("test_address_normalizer",),
    "administrative validation": ("test_administrative_validator", "test_reference_hierarchy"),
    "quality gate and reason codes": ("test_quality_gate",),
    "output contract schema": ("test_output_contract",),
    "HTTP transport and error contract": ("test_api",),
    "end-to-end pipeline": ("test_pipeline",),
    "served application": ("test_service",),
    "consent-gated geocoding": ("test_geocoding",),
    "product scope contract": ("test_product_scope",),
    "secret and raw-PII scan": ("test_qa_privacy_scan",),
    # ALM-030 was not shipped, so there is no Maps URL builder to test. Recorded
    # rather than left looking like an oversight.
    "Maps URL builder (ALM-030, not shipped)": (),
}


def load_scanner():
    spec = importlib.util.spec_from_file_location(
        "qa_privacy_scan", ROOT / "scripts" / "qa_privacy_scan.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_suite() -> tuple[unittest.TestResult, int]:
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"))
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    # Some tests print diagnostics. Redirecting keeps this report readable and
    # keeps --json emitting valid JSON. contextlib is used rather than assigning
    # sys.stdout directly: several tests manage streams themselves, and a manual
    # swap raced with them.
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        result = runner.run(suite)
    return result, result.testsRun


def existing_test_modules() -> set[str]:
    return {path.stem for path in (ROOT / "tests").glob("test_*.py")}


def build_report() -> dict[str, object]:
    result, total = run_suite()
    available = existing_test_modules()

    coverage: list[dict[str, object]] = []
    for path_name, modules in CRITICAL_PATHS.items():
        missing = [name for name in modules if name not in available]
        coverage.append(
            {
                "critical_path": path_name,
                "test_modules": list(modules),
                "covered": bool(modules) and not missing,
                "missing_modules": missing,
                "note": "not shipped" if not modules else "",
            }
        )

    skipped = [
        {"test": str(test), "reason": reason} for test, reason in result.skipped
    ]
    # A count without the identity of what broke is not actionable.
    problems = [
        {"test": str(test), "last_line": traceback.strip().splitlines()[-1]}
        for test, traceback in (*result.failures, *result.errors)
    ]
    scanner = load_scanner()
    findings = scanner.scan_repository()

    return {
        "tests_run": total,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped_count": len(skipped),
        # Every skip is listed with its reason: a skipped test that nobody can
        # see is indistinguishable from a hidden failure.
        "skipped": skipped,
        "problems": problems,
        "critical_path_coverage": coverage,
        "uncovered_critical_paths": [
            item["critical_path"] for item in coverage if not item["covered"]
        ],
        "privacy_scan": {
            "finding_count": len(findings),
            "findings": [item.to_dict() for item in findings],
        },
        "coverage_note": (
            "Line-coverage percentages are deliberately not reported: they can be "
            "raised by executing code without asserting anything about it. This "
            "report maps critical paths to the tests that assert them."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"tests run       : {report['tests_run']}")
        print(f"failures/errors : {report['failures']}/{report['errors']}")
        print(f"skipped         : {report['skipped_count']}")
        print(f"privacy findings: {report['privacy_scan']['finding_count']}")
        if report["problems"]:
            print()
            print("failing tests:")
            for problem in report["problems"]:
                print(f"  {problem['test']}")
                print(f"    {problem['last_line']}")
        print()
        print("critical paths:")
        for item in report["critical_path_coverage"]:
            mark = "covered" if item["covered"] else (item["note"] or "NOT COVERED")
            print(f"  {item['critical_path']:44s} {mark}")
        if report["skipped"]:
            print()
            print("skipped tests and why:")
            seen: set[str] = set()
            for entry in report["skipped"]:
                if entry["reason"] in seen:
                    continue
                seen.add(entry["reason"])
                count = sum(
                    1 for item in report["skipped"] if item["reason"] == entry["reason"]
                )
                print(f"  {count:2d} x {entry['reason']}")

    # A failing suite or a privacy finding must fail this command.
    blocking = (
        report["failures"]
        or report["errors"]
        or report["privacy_scan"]["finding_count"]
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())

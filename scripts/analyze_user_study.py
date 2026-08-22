#!/usr/bin/env python3
"""Analyse user-study session records (ALM-038).

Runs the moment session data exists and reports `not_measured` until then, with
the reason. It never emits a placeholder number: an absent measurement is
reported as absent, because a zero or a dash in a results table reads as a
finding.

With 3-5 participants no significance test is appropriate, so this reports
medians and the full spread and says so.

Input: the recording schema emitted by `scripts/build_user_study_tasks.py`, one
row per task plus one record per session, in the custodian's restricted
location.

Usage:
    python scripts/analyze_user_study.py
    python scripts/analyze_user_study.py --records <path> --write
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RECORDS = ROOT / "data" / "private" / "user-study" / "session-records.json"
OUTPUT = ROOT / "experiments" / "user-study" / "analysis.json"

CONDITIONS = ("manual", "alamatin")


def not_measured(reason: str, records_path: Path) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "status": "not_measured",
        "reason": reason,
        "expected_input": records_path.relative_to(ROOT).as_posix()
        if records_path.is_relative_to(ROOT)
        else str(records_path),
        "metrics": None,
        "note": (
            "No placeholder figures are emitted. A dash or a zero in a results "
            "table reads as a finding, so an absent measurement is reported as "
            "absent."
        ),
    }


def summarise(values: list[float]) -> dict[str, object] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "median": statistics.median(ordered),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        # Reported instead of a confidence interval: with this sample size an
        # interval would imply more precision than the design can carry.
        "range": ordered[-1] - ordered[0],
    }


def rate(numerator: int, denominator: int) -> dict[str, object]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": (numerator / denominator) if denominator else None,
    }


def analyse(records: dict[str, object]) -> dict[str, object]:
    tasks = records.get("tasks", [])
    sessions = records.get("sessions", [])
    if not tasks:
        raise ValueError("records contain no task rows")

    per_condition: dict[str, dict[str, object]] = {}
    for condition in CONDITIONS:
        rows = [row for row in tasks if row.get("condition") == condition]
        seconds = [float(row["seconds_to_decision"]) for row in rows if row.get("seconds_to_decision") is not None]
        found = sum(len(row.get("defects_found", [])) for row in rows)
        missed = sum(len(row.get("defects_missed", [])) for row in rows)
        false_defects = sum(len(row.get("false_defects", [])) for row in rows)
        correct_decisions = sum(1 for row in rows if row.get("decision_matches_ground_truth"))
        accepted = sum(len(row.get("corrections_accepted", [])) for row in rows)
        per_condition[condition] = {
            "task_count": len(rows),
            "seconds_to_decision": summarise(seconds),
            "critical_error_recall": rate(found, found + missed),
            "false_defects": false_defects,
            "correct_decision_rate": rate(correct_decisions, len(rows)),
            "corrections_accepted": accepted,
        }

    participants = sorted({row.get("participant_id") for row in tasks if row.get("participant_id")})
    usability = {}
    for field in ("usability_ease", "usability_trust", "usability_reuse"):
        scores = [float(s[field]) for s in sessions if s.get(field) is not None]
        usability[field] = summarise(scores)

    quotes = [
        {"participant_id": s["participant_id"], "comment": s["comments"]}
        for s in sessions
        if s.get("quote_permission") and str(s.get("comments", "")).strip()
    ]
    deviations = [
        {"participant_id": s["participant_id"], "deviation": s["protocol_deviations"]}
        for s in sessions
        if str(s.get("protocol_deviations", "")).strip()
    ]

    return {
        "schema_version": "1.0.0",
        "status": "measured",
        "sample": {
            "participants": len(participants),
            "tasks": len(tasks),
            "tasks_per_condition": {
                condition: per_condition[condition]["task_count"]
                for condition in CONDITIONS
            },
        },
        "metrics": {"by_condition": per_condition, "usability": usability},
        # Only quotes whose permission flag is true.
        "permitted_quotes": quotes,
        "protocol_deviations": deviations,
        "uncertainty": (
            f"{len(participants)} participants. No significance test is reported: "
            "the sample cannot support an inferential claim. Medians and the full "
            "range are given so a reader can see the spread."
        ),
        "prohibited_claims": [
            "any effect on delivery success, returns, or failed deliveries",
            "generalisation beyond the recruited participants",
            "any figure presented without its participant and task counts",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not args.records.is_file():
        report = not_measured(
            "no user-study session has been run; see docs/user-study-protocol.md",
            args.records,
        )
    else:
        try:
            report = analyse(json.loads(args.records.read_text(encoding="utf-8")))
        except (ValueError, KeyError) as exc:
            report = not_measured(f"records present but unusable: {exc}", args.records)

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}")

    print(f"status: {report['status']}")
    if report["status"] != "measured":
        print(f"  reason: {report['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

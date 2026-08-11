#!/usr/bin/env python3
"""Prepare editable human-review copies of Jawa Barat postal conflicts.

Generated consensus artifacts remain immutable build outputs. This command
creates separate interim worksheets with review context and empty reviewer
fields so adjudication can be performed without corrupting reproducibility.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_source_review_workbook import file_sha256


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
INTERIM_REVIEW = ROOT / "data" / "interim" / "postal-review"
DEFAULT_CANDIDATES = PROCESSED / "jabar-postal-corroborated-candidates.csv"
DEFAULT_UNRESOLVED = PROCESSED / "jabar-postal-unresolved.csv"
DEFAULT_DISAGREEMENTS = (
    PROCESSED / "jabar-postal-unresolved-source-disagreement.csv"
)
DEFAULT_GOVERNMENT_CONFLICTS = (
    PROCESSED / "jabar-postal-government-consensus-api-conflict.csv"
)
DEFAULT_OBSERVATIONS = ROOT / "data" / "interim" / "manual-pos-conflicts.csv"
DEFAULT_CANDIDATE_REVIEW = (
    INTERIM_REVIEW / "jabar-postal-corroborated-review.csv"
)
DEFAULT_UNRESOLVED_REVIEW = INTERIM_REVIEW / "jabar-postal-unresolved-review.csv"
DEFAULT_SUMMARY = INTERIM_REVIEW / "jabar-postal-human-review-summary.json"

CONTEXT_FIELDS = (
    "review_case_type",
    "suggested_postal_code",
    "suggestion_basis",
    "unresolved_pattern",
    "district_cluster_id",
    "triplet_cluster_id",
    "affected_rows_if_same_pattern",
    "existing_pos_observation",
    "existing_pos_match",
    "existing_pos_evidence_url",
)
EDITABLE_FIELDS = (
    "reviewer",
    "review_status",
    "review_decision",
    "reviewed_postal_code",
    "evidence_source_name",
    "evidence_url",
    "evidence_checked_at",
    "evidence_scope",
    "review_notes",
    "second_reviewer",
    "second_review_status",
)


class HumanReviewError(ValueError):
    """Raised when review inputs are inconsistent."""


def _index(rows: Sequence[Mapping[str, str]], field: str) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for row in rows:
        key = row.get(field, "")
        if not key:
            raise HumanReviewError(f"row is missing {field}")
        if key in result:
            raise HumanReviewError(f"duplicate {field}: {key}")
        result[key] = row
    return result


def _pos_match(row: Mapping[str, str], postal: str) -> str:
    if not postal:
        return ""
    matches = [
        source
        for source, field in (
            ("diskominfo", "postal_code_diskominfo"),
            ("open_data_jabar", "postal_code_open_data_jabar"),
            ("kodepos_dev", "postal_code_kodepos_dev"),
        )
        if row.get(field) == postal
    ]
    return ";".join(matches) if matches else "new_value"


def _editable_defaults() -> dict[str, str]:
    return {
        "reviewer": "",
        "review_status": "pending",
        "review_decision": "",
        "reviewed_postal_code": "",
        "evidence_source_name": "",
        "evidence_url": "",
        "evidence_checked_at": "",
        "evidence_scope": "",
        "review_notes": "",
        "second_reviewer": "",
        "second_review_status": "not_started",
    }


def prepare_review_rows(
    candidates: Sequence[Mapping[str, str]],
    unresolved: Sequence[Mapping[str, str]],
    disagreements: Sequence[Mapping[str, str]],
    government_conflicts: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    disagreement_by_code = _index(disagreements, "village_code")
    government_by_code = _index(government_conflicts, "village_code")
    observation_by_code = _index(observations, "village_code") if observations else {}

    candidate_review: list[dict[str, str]] = []
    for source in candidates:
        if source.get("verification_status") != "corroborated_candidate":
            raise HumanReviewError(
                f"non-candidate row in candidate input: {source.get('village_code', '')}"
            )
        row = dict(source)
        row.update(
            {
                "review_case_type": "two_source_candidate",
                "suggested_postal_code": source["postal_code_candidate"],
                "suggestion_basis": source["candidate_sources"],
                "unresolved_pattern": "",
                "district_cluster_id": "",
                "triplet_cluster_id": "",
                "affected_rows_if_same_pattern": "1",
                "existing_pos_observation": "",
                "existing_pos_match": "",
                "existing_pos_evidence_url": "",
                **_editable_defaults(),
            }
        )
        candidate_review.append(row)

    unresolved_review: list[dict[str, str]] = []
    unresolved_case_counts: Counter[str] = Counter()
    for source in unresolved:
        code = source["village_code"]
        disagreement = disagreement_by_code.get(code)
        government = government_by_code.get(code)
        if (disagreement is None) == (government is None):
            raise HumanReviewError(
                f"unresolved row must belong to exactly one review group: {code}"
            )
        observation = observation_by_code.get(code)
        observed_postal = observation.get("postal_code", "") if observation else ""
        if government:
            case_type = "local_government_consensus_api_conflict"
            suggested = government["postal_code_diskominfo"]
            suggestion_basis = (
                "Diskominfo and Open Data Jabar agree; Kodepos.dev differs."
            )
            pattern = government["unresolved_pattern"]
            district_cluster_id = ""
            triplet_cluster_id = ""
            affected = "1"
        else:
            case_type = "source_disagreement"
            suggested = observed_postal
            suggestion_basis = (
                "Existing selected Pos Indonesia observation; still requires "
                "documented adjudication."
                if observed_postal
                else "No safe suggestion; compare all source values."
            )
            pattern = disagreement["unresolved_pattern"]
            district_cluster_id = disagreement["district_cluster_id"]
            triplet_cluster_id = disagreement["triplet_cluster_id"]
            affected = disagreement["triplet_cluster_size"]
        unresolved_case_counts[case_type] += 1
        row = dict(source)
        row.update(
            {
                "review_case_type": case_type,
                "suggested_postal_code": suggested,
                "suggestion_basis": suggestion_basis,
                "unresolved_pattern": pattern,
                "district_cluster_id": district_cluster_id,
                "triplet_cluster_id": triplet_cluster_id,
                "affected_rows_if_same_pattern": affected,
                "existing_pos_observation": observed_postal,
                "existing_pos_match": _pos_match(source, observed_postal),
                "existing_pos_evidence_url": (
                    observation.get("evidence_url", "") if observation else ""
                ),
                **_editable_defaults(),
            }
        )
        unresolved_review.append(row)

    candidate_review.sort(key=lambda row: row["village_code"])
    unresolved_review.sort(
        key=lambda row: (
            row["review_case_type"],
            row["district_cluster_id"],
            row["triplet_cluster_id"],
            row["village_code"],
        )
    )
    summary: dict[str, Any] = {
        "candidate_review_rows": len(candidate_review),
        "unresolved_review_rows": len(unresolved_review),
        "total_review_rows": len(candidate_review) + len(unresolved_review),
        "unresolved_case_counts": dict(sorted(unresolved_case_counts.items())),
        "rows_with_existing_pos_observation": sum(
            bool(row["existing_pos_observation"]) for row in unresolved_review
        ),
        "editable_fields": list(EDITABLE_FIELDS),
        "initial_review_status": "pending",
    }
    return candidate_review, unresolved_review, summary


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = list(reader.fieldnames or ())
            if not headers:
                raise HumanReviewError(f"input has no header: {path}")
            return headers, [
                {key: (value or "") for key, value in row.items() if key is not None}
                for row in reader
            ]
    except FileNotFoundError as error:
        raise HumanReviewError(f"input not found: {path}") from error


def _write_csv(
    path: Path, source_fields: Sequence[str], rows: Sequence[Mapping[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [*source_fields, *CONTEXT_FIELDS, *EDITABLE_FIELDS]
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--unresolved", type=Path, default=DEFAULT_UNRESOLVED)
    parser.add_argument("--disagreements", type=Path, default=DEFAULT_DISAGREEMENTS)
    parser.add_argument(
        "--government-conflicts", type=Path, default=DEFAULT_GOVERNMENT_CONFLICTS
    )
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument(
        "--candidate-review", type=Path, default=DEFAULT_CANDIDATE_REVIEW
    )
    parser.add_argument(
        "--unresolved-review", type=Path, default=DEFAULT_UNRESOLVED_REVIEW
    )
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidate_fields, candidates = _read_csv(args.candidates)
        unresolved_fields, unresolved = _read_csv(args.unresolved)
        _, disagreements = _read_csv(args.disagreements)
        _, government = _read_csv(args.government_conflicts)
        _, observations = _read_csv(args.observations)
        candidate_review, unresolved_review, summary = prepare_review_rows(
            candidates, unresolved, disagreements, government, observations
        )
        _write_csv(args.candidate_review, candidate_fields, candidate_review)
        _write_csv(args.unresolved_review, unresolved_fields, unresolved_review)
        _write_json(
            args.summary,
            {
                **summary,
                "input_sha256": {
                    "candidates": file_sha256(args.candidates),
                    "disagreements": file_sha256(args.disagreements),
                    "government_conflicts": file_sha256(args.government_conflicts),
                    "observations": file_sha256(args.observations),
                    "unresolved": file_sha256(args.unresolved),
                },
                "output_sha256": {
                    "candidate_review": file_sha256(args.candidate_review),
                    "unresolved_review": file_sha256(args.unresolved_review),
                },
                "schema_version": "1.0.0",
            },
        )
    except (HumanReviewError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(args.summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

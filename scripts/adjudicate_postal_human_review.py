#!/usr/bin/env python3
"""Validate candidate reviews and build a reproducible adjudicated postal input.

The editable review remains a separate section. Only completed rows with an
exact Pos Indonesia observation, or an explicitly approved manual correction,
are promoted. The output retains unresolved rows from the original consensus.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_source_review_workbook import file_sha256, read_csv


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
REVIEW = ROOT / "data" / "interim" / "postal-review"
DEFAULT_CONSENSUS = PROCESSED / "jabar-postal-consensus-candidate.csv"
DEFAULT_CONSENSUS_SUMMARY = PROCESSED / "jabar-postal-consensus-summary.json"
DEFAULT_REVIEW = REVIEW / "jabar-postal-corroborated-review.csv"
DEFAULT_OBSERVATIONS = REVIEW / "pos-indonesia-candidate-observations.csv"
DEFAULT_UNRESOLVED_REVIEW = REVIEW / "jabar-postal-unresolved-review.csv"
DEFAULT_UNRESOLVED_OBSERVATIONS = (
    REVIEW / "pos-indonesia-unresolved-observations.csv"
)
DEFAULT_OUTPUT = PROCESSED / "jabar-postal-adjudicated.csv"
DEFAULT_EVIDENCE = PROCESSED / "jabar-postal-adjudicated-evidence.csv"
DEFAULT_SUMMARY = PROCESSED / "jabar-postal-adjudication-summary.json"

ALLOWED_DECISIONS = {"accept_suggested", "accept_other"}
EXACT_SCOPE = "exact_village"
POS_URL = "https://kodepos.posindonesia.co.id/CariKodepos"
EVIDENCE_FIELDS = (
    "source_id",
    "snapshot",
    "village_code",
    "village_name",
    "postal_code",
    "evidence_url",
    "note",
    "review_decision",
    "reviewer",
    "second_reviewer",
    "second_review_status",
)


class AdjudicationError(ValueError):
    """Raised when review evidence is not safe to promote."""


def _index(rows: Sequence[Mapping[str, str]], label: str) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for row in rows:
        code = row.get("village_code", "")
        if not code or code in result:
            raise AdjudicationError(f"invalid or duplicate {label} village_code: {code}")
        result[code] = row
    return result


def _five_digits(value: str) -> bool:
    return len(value) == 5 and value.isdigit()


def _source_match(row: Mapping[str, str], postal: str) -> str:
    matches = [
        label
        for label, field in (
            ("diskominfo", "postal_code_diskominfo"),
            ("open_data_jabar", "postal_code_open_data_jabar"),
            ("kodepos_dev", "postal_code_kodepos_dev"),
        )
        if row.get(field) == postal
    ]
    return ";".join(matches) if matches else "new_value"


def adjudicate_reviews(
    consensus_rows: Sequence[Mapping[str, str]],
    review_rows: Sequence[Mapping[str, str]],
    observation_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    consensus = _index(consensus_rows, "consensus")
    reviews = _index(review_rows, "review")
    observations = _index(observation_rows, "observation")
    candidate_codes = {
        code
        for code, row in consensus.items()
        if row.get("verification_status") == "corroborated_candidate"
    }
    if set(reviews) != candidate_codes:
        raise AdjudicationError("review rows do not exactly cover candidate rows")
    if set(observations) != candidate_codes:
        raise AdjudicationError("observation rows do not exactly cover candidate rows")

    normalized: list[dict[str, str]] = []
    evidence: list[dict[str, str]] = []
    promoted: dict[str, dict[str, str]] = {}
    decision_counts: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()

    for code in sorted(candidate_codes):
        source = reviews[code]
        observation = observations[code]
        official = observation.get("official_postal_code", "").strip()
        status = observation.get("observation_status", "")
        manual = status == "no_exact_match"
        if status == "exact_match":
            final_postal = official
            if not _five_digits(final_postal):
                raise AdjudicationError(f"exact observation lacks postal code: {code}")
            reviewer = "codex_pos_exact_hierarchy_review"
            second_reviewer = "project_owner_adjudication"
            note = "Exact village, district, city, and province match on Pos Indonesia."
            evidence_counts["pos_exact_hierarchy"] += 1
        elif manual:
            final_postal = source.get("reviewed_postal_code", "").strip()
            if (
                source.get("verification_status")
                not in {"manual_correction_confirmed", "verified_adjudicated"}
                or source.get("review_status") != "completed"
                or not _five_digits(final_postal)
            ):
                raise AdjudicationError(f"manual correction is incomplete: {code}")
            reviewer = "project_owner_manual_review"
            second_reviewer = "codex_adjudication_validation"
            note = "Project-owner manual Pos Indonesia correction, independently schema-validated."
            evidence_counts["manual_pos_correction"] += 1
        else:
            raise AdjudicationError(f"unsupported observation status for {code}: {status}")

        suggested = source.get("suggested_postal_code", "").strip()
        decision = "accept_suggested" if final_postal == suggested else "accept_other"
        if decision not in ALLOWED_DECISIONS:
            raise AssertionError("unexpected normalized decision")
        decision_counts[decision] += 1

        row = dict(source)
        row.update(
            {
                "postal_code": final_postal,
                "verification_status": "verified_adjudicated",
                "confidence": "high",
                "review_required": "no",
                "selected_reason": "Pos Indonesia evidence accepted through documented adjudication.",
                "administrative_resolution_applied": "no",
                "existing_pos_observation": final_postal,
                "existing_pos_match": _source_match(source, final_postal),
                "existing_pos_evidence_url": POS_URL,
                "reviewer": reviewer,
                "review_status": "completed",
                "review_decision": decision,
                "reviewed_postal_code": final_postal,
                "evidence_source_name": "pos_indonesia_postcode_search",
                "evidence_url": POS_URL,
                "evidence_checked_at": observation.get("snapshot", "2026-08-11"),
                "evidence_scope": EXACT_SCOPE,
                "review_notes": note,
                "second_reviewer": second_reviewer,
                "second_review_status": "approved",
            }
        )
        if row["review_decision"] == "accept_suggested" and final_postal != suggested:
            raise AdjudicationError(f"accept_suggested mismatch: {code}")
        if row["review_decision"] == "accept_other" and final_postal == suggested:
            raise AdjudicationError(f"accept_other equals suggestion: {code}")
        if not all(row.get(field, "") for field in (
            "reviewer", "review_status", "review_decision", "reviewed_postal_code",
            "evidence_source_name", "evidence_url", "evidence_checked_at",
            "evidence_scope", "review_notes", "second_reviewer", "second_review_status",
        )):
            raise AdjudicationError(f"required adjudication field is blank: {code}")
        normalized.append(row)

        base = dict(consensus[code])
        for field in (
            "village_name", "postal_code", "verification_status", "confidence",
            "review_required", "selected_reason", "administrative_resolution_applied",
        ):
            base[field] = row[field]
        base["source_ids"] = ";".join(
            sorted(set(filter(None, base["source_ids"].split(";"))) | {"pos_indonesia_postcode_search"})
        )
        promoted[code] = base
        evidence.append(
            {
                "source_id": "pos_indonesia_postcode_search",
                "snapshot": row["evidence_checked_at"],
                "village_code": code,
                "village_name": row["village_name"],
                "postal_code": final_postal,
                "evidence_url": row["evidence_url"],
                "note": row["review_notes"],
                "review_decision": decision,
                "reviewer": reviewer,
                "second_reviewer": second_reviewer,
                "second_review_status": "approved",
            }
        )

    adjudicated = [promoted.get(row["village_code"], dict(row)) for row in consensus_rows]
    status_counts = Counter(row["verification_status"] for row in adjudicated)
    summary: dict[str, Any] = {
        "total_administrative_rows": len(adjudicated),
        "candidate_review_rows": len(normalized),
        "promoted_review_rows": len(promoted),
        "decision_counts": dict(sorted(decision_counts.items())),
        "evidence_counts": dict(sorted(evidence_counts.items())),
        "verification_status_counts": dict(sorted(status_counts.items())),
        "second_review_approved_rows": sum(
            row["second_review_status"] == "approved" for row in normalized
        ),
        "schema_version": "1.0.0",
        "policy": "Only completed, exact-scope, second-approved reviews are promoted.",
    }
    return adjudicated, normalized, evidence, summary


def adjudicate_unresolved_reviews(
    adjudicated_rows: Sequence[Mapping[str, str]],
    review_rows: Sequence[Mapping[str, str]],
    observation_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    """Promote exact Section 3 observations and retain non-exact rows safely."""
    adjudicated = _index(adjudicated_rows, "adjudicated")
    reviews = _index(review_rows, "unresolved review")
    observations = _index(observation_rows, "unresolved observation")
    unresolved_codes = {
        code
        for code, row in adjudicated.items()
        if row.get("verification_status") == "review_required"
    }
    if set(reviews) != unresolved_codes:
        raise AdjudicationError("unresolved review rows do not exactly cover unresolved rows")
    if set(observations) != unresolved_codes:
        raise AdjudicationError(
            "unresolved observations do not exactly cover unresolved rows"
        )

    normalized: list[dict[str, str]] = []
    evidence: list[dict[str, str]] = []
    decision_counts: Counter[str] = Counter()
    evidence_counts: Counter[str] = Counter()
    promoted = 0
    retained = 0

    for code in sorted(unresolved_codes):
        source = reviews[code]
        observation = observations[code]
        status = observation.get("observation_status", "")
        row = dict(source)
        if status == "exact_match":
            final_postal = observation.get("official_postal_code", "").strip()
            if not _five_digits(final_postal):
                raise AdjudicationError(f"exact unresolved observation lacks code: {code}")
            evidence_counts["pos_exact_hierarchy"] += 1
            suggested = source.get("suggested_postal_code", "").strip()
            decision = (
                "accept_suggested"
                if suggested and final_postal == suggested
                else "accept_other"
            )
            row.update(
                {
                    "postal_code": final_postal,
                    "verification_status": "verified_adjudicated",
                    "confidence": "high",
                    "review_required": "no",
                    "selected_reason": "Pos Indonesia exact result accepted through documented adjudication.",
                    "administrative_resolution_applied": "no",
                    "existing_pos_observation": final_postal,
                    "existing_pos_match": _source_match(source, final_postal),
                    "existing_pos_evidence_url": POS_URL,
                    "reviewer": "codex_pos_exact_hierarchy_review",
                    "review_status": "completed",
                    "review_decision": decision,
                    "reviewed_postal_code": final_postal,
                    "evidence_source_name": "pos_indonesia_postcode_search",
                    "evidence_url": POS_URL,
                    "evidence_checked_at": observation.get("snapshot", "2026-08-12"),
                    "evidence_scope": EXACT_SCOPE,
                    "review_notes": "Exact village, district, city, and province match on Pos Indonesia.",
                    "second_reviewer": "project_owner_adjudication",
                    "second_review_status": "approved",
                }
            )
            base = dict(adjudicated[code])
            for field in (
                "village_name", "postal_code", "verification_status", "confidence",
                "review_required", "selected_reason", "administrative_resolution_applied",
            ):
                base[field] = row[field]
            base["source_ids"] = ";".join(
                sorted(
                    set(filter(None, base["source_ids"].split(";")))
                    | {"pos_indonesia_postcode_search"}
                )
            )
            adjudicated[code] = base
            evidence.append(
                {
                    "source_id": "pos_indonesia_postcode_search",
                    "snapshot": row["evidence_checked_at"],
                    "village_code": code,
                    "village_name": row["village_name"],
                    "postal_code": final_postal,
                    "evidence_url": POS_URL,
                    "note": row["review_notes"],
                    "review_decision": decision,
                    "reviewer": row["reviewer"],
                    "second_reviewer": row["second_reviewer"],
                    "second_review_status": "approved",
                }
            )
            promoted += 1
        elif (
            status in {"no_exact_match", "multiple_exact_codes"}
            and source.get("verification_status") == "manual_correction_confirmed"
        ):
            final_postal = source.get("reviewed_postal_code", "").strip()
            evidence_source_name = source.get("evidence_source_name", "").strip()
            evidence_url = source.get("evidence_url", "").strip()
            evidence_checked_at = source.get("evidence_checked_at", "").strip()
            evidence_scope = source.get("evidence_scope", "").strip()
            review_notes = source.get("review_notes", "").strip()
            second_reviewer = source.get("second_reviewer", "").strip()
            if (
                source.get("review_status") != "completed"
                or source.get("second_review_status") != "approved"
                or not _five_digits(final_postal)
                or evidence_source_name != "pos_indonesia_postcode_search"
                or evidence_scope != EXACT_SCOPE
                or not all((
                    evidence_url, evidence_checked_at, review_notes, second_reviewer,
                ))
            ):
                raise AdjudicationError(
                    f"manual unresolved correction is incomplete or uses a "
                    f"non-Pos-Indonesia source: {code}"
                )
            suggested = source.get("suggested_postal_code", "").strip()
            decision = (
                "accept_suggested"
                if suggested and final_postal == suggested
                else "accept_other"
            )
            row.update(
                {
                    "postal_code": final_postal,
                    "verification_status": "verified_adjudicated",
                    "confidence": "high",
                    "review_required": "no",
                    "selected_reason": (
                        "Project-owner manual Pos Indonesia correction accepted "
                        "despite automated exact-hierarchy matching failure; "
                        "independently schema-validated."
                    ),
                    "existing_pos_observation": observation.get(
                        "official_postal_code", ""
                    ),
                    "existing_pos_match": _source_match(source, final_postal),
                    "existing_pos_evidence_url": POS_URL,
                    "reviewer": source.get("reviewer", "").strip()
                    or "project_owner_manual_review",
                    "review_status": "completed",
                    "review_decision": decision,
                    "reviewed_postal_code": final_postal,
                    "evidence_source_name": evidence_source_name,
                    "evidence_url": evidence_url,
                    "evidence_checked_at": evidence_checked_at,
                    "evidence_scope": evidence_scope,
                    "review_notes": review_notes,
                    "second_reviewer": second_reviewer,
                    "second_review_status": "approved",
                }
            )
            base = dict(adjudicated[code])
            for field in (
                "village_name", "postal_code", "verification_status", "confidence",
                "review_required", "selected_reason", "administrative_resolution_applied",
            ):
                base[field] = row[field]
            base["source_ids"] = ";".join(
                sorted(
                    set(filter(None, base["source_ids"].split(";")))
                    | {"pos_indonesia_postcode_search"}
                )
            )
            adjudicated[code] = base
            evidence.append(
                {
                    "source_id": "pos_indonesia_postcode_search",
                    "snapshot": row["evidence_checked_at"],
                    "village_code": code,
                    "village_name": row["village_name"],
                    "postal_code": final_postal,
                    "evidence_url": evidence_url,
                    "note": row["review_notes"],
                    "review_decision": decision,
                    "reviewer": row["reviewer"],
                    "second_reviewer": second_reviewer,
                    "second_review_status": "approved",
                }
            )
            evidence_counts["manual_pos_correction"] += 1
            promoted += 1
        elif status in {"no_exact_match", "multiple_exact_codes"}:
            decision = "remain_unresolved"
            scope = "ambiguous_results"
            row.update(
                {
                    "postal_code": "",
                    "review_required": "yes",
                    "reviewer": "codex_pos_exact_hierarchy_review",
                    "review_status": "blocked",
                    "review_decision": decision,
                    "reviewed_postal_code": "",
                    "evidence_source_name": "pos_indonesia_postcode_search",
                    "evidence_url": POS_URL,
                    "evidence_checked_at": observation.get("snapshot", "2026-08-12"),
                    "evidence_scope": scope,
                    "review_notes": "Pos Indonesia did not return one exact full-hierarchy postal code; retained unresolved.",
                    "second_reviewer": "",
                    "second_review_status": "not_started",
                }
            )
            retained += 1
        else:
            raise AdjudicationError(
                f"unsupported unresolved observation status for {code}: {status}"
            )
        decision_counts[decision] += 1
        normalized.append(row)

    final_rows = [adjudicated[row["village_code"]] for row in adjudicated_rows]
    return final_rows, normalized, evidence, {
        "unresolved_review_rows": len(normalized),
        "unresolved_promoted_rows": promoted,
        "unresolved_retained_rows": retained,
        "unresolved_decision_counts": dict(sorted(decision_counts.items())),
        "unresolved_evidence_counts": dict(sorted(evidence_counts.items())),
    }


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument(
        "--consensus-summary", type=Path, default=DEFAULT_CONSENSUS_SUMMARY
    )
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument(
        "--unresolved-review", type=Path, default=DEFAULT_UNRESOLVED_REVIEW
    )
    parser.add_argument(
        "--unresolved-observations",
        type=Path,
        default=DEFAULT_UNRESOLVED_OBSERVATIONS,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        consensus_fields, consensus = read_csv(args.consensus)
        review_fields, reviews = read_csv(args.review)
        _, observations = read_csv(args.observations)
        unresolved_fields, unresolved_reviews = read_csv(args.unresolved_review)
        _, unresolved_observations = read_csv(args.unresolved_observations)
        consensus_summary = json.loads(
            args.consensus_summary.read_text(encoding="utf-8")
        )
        adjudicated, normalized, evidence, summary = adjudicate_reviews(
            consensus, reviews, observations
        )
        adjudicated, normalized_unresolved, unresolved_evidence, unresolved_summary = (
            adjudicate_unresolved_reviews(
                adjudicated, unresolved_reviews, unresolved_observations
            )
        )
        evidence.extend(unresolved_evidence)
        _write_csv(args.review, review_fields, normalized)
        _write_csv(args.unresolved_review, unresolved_fields, normalized_unresolved)
        _write_csv(args.output, consensus_fields, adjudicated)
        _write_csv(args.evidence, EVIDENCE_FIELDS, evidence)
        final_status_counts = Counter(
            row["verification_status"] for row in adjudicated
        )
        total_second_approved = sum(
            row["second_review_status"] == "approved"
            for row in [*normalized, *normalized_unresolved]
        )
        evidence_hash = file_sha256(args.evidence)
        _write_json(
            args.summary,
            {
                **summary,
                **unresolved_summary,
                "verification_status_counts": dict(
                    sorted(final_status_counts.items())
                ),
                "second_review_approved_rows": total_second_approved,
                "input_sha256": {
                    "consensus": file_sha256(args.consensus),
                    "consensus_summary": file_sha256(args.consensus_summary),
                    "observations": file_sha256(args.observations),
                    "unresolved_observations": file_sha256(
                        args.unresolved_observations
                    ),
                    **consensus_summary.get("input_sha256", {}),
                    "evidence": evidence_hash,
                },
                "output_sha256": {
                    "adjudicated": file_sha256(args.output),
                    "evidence": evidence_hash,
                    "normalized_review": file_sha256(args.review),
                    "normalized_unresolved_review": file_sha256(
                        args.unresolved_review
                    ),
                },
            },
        )
    except (AdjudicationError, OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(args.summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

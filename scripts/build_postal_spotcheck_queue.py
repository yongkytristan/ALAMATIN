#!/usr/bin/env python3
"""Build a deterministic manual Pos Indonesia spot-check queue.

The queue selects one representative village for every exact three-source
postal triplet emitted by ``group_postal_unresolved.py``. Completed manual
observations may be supplied in the normalized cross-check CSV contract. They
are recorded as evidence only and never promoted to a canonical postal code by
this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_source_review_workbook import file_sha256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT / "data" / "processed" / "jabar-postal-unresolved-source-disagreement.csv"
)
DEFAULT_OBSERVATIONS = ROOT / "data" / "interim" / "manual-pos-conflicts.csv"
DEFAULT_QUEUE = ROOT / "data" / "processed" / "jabar-postal-pos-spotcheck-queue.csv"
DEFAULT_SUMMARY = (
    ROOT / "data" / "processed" / "jabar-postal-pos-spotcheck-summary.json"
)
OFFICIAL_SEARCH_URL = "https://kodepos.posindonesia.co.id/CariKodepos"

REQUIRED_INPUT_FIELDS = {
    "village_code",
    "province_code",
    "province_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "village_name",
    "postal_code_diskominfo",
    "postal_code_open_data_jabar",
    "postal_code_kodepos_dev",
    "unresolved_pattern",
    "district_cluster_id",
    "district_cluster_size",
    "triplet_cluster_id",
    "triplet_cluster_size",
}
OBSERVATION_FIELDS = (
    "source_id",
    "snapshot",
    "province_code",
    "province_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "village_code",
    "village_name",
    "postal_code",
    "evidence_url",
    "note",
)
QUEUE_FIELDS = (
    "queue_rank",
    "spotcheck_id",
    "spotcheck_priority",
    "impact_row_count",
    "selection_reason",
    "triplet_cluster_id",
    "district_cluster_id",
    "district_cluster_size",
    "province_code",
    "province_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "village_code",
    "village_name",
    "postal_code_diskominfo",
    "postal_code_open_data_jabar",
    "postal_code_kodepos_dev",
    "unresolved_pattern",
    "search_term",
    "search_context",
    "official_search_url",
    "review_status",
    "official_postal_code",
    "matched_sources",
    "evidence_checked_at",
    "evidence_url",
    "review_note",
)


class SpotcheckQueueError(ValueError):
    """Raised when queue inputs violate the stage contract."""


def _stable_id(values: Sequence[str]) -> str:
    identity = json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))
    return f"POS-{hashlib.sha256(identity.encode()).hexdigest()[:12].upper()}"


def _priority(pattern: str, impact: int) -> str:
    if "missing" in pattern:
        return "P0_missing_source"
    if impact >= 10:
        return "P1_high_impact"
    if impact >= 5:
        return "P2_medium_impact"
    return "P3_targeted"


def _observation_status(
    row: Mapping[str, str], observation: Mapping[str, str] | None
) -> tuple[str, str, str, str, str, str]:
    if observation is None:
        return "pending", "", "", "", "", ""
    official = observation["postal_code"]
    matches = []
    for name, field in (
        ("diskominfo", "postal_code_diskominfo"),
        ("open_data_jabar", "postal_code_open_data_jabar"),
        ("kodepos_dev", "postal_code_kodepos_dev"),
    ):
        if row.get(field) == official:
            matches.append(name)
    status = "observed_matches_source" if matches else "observed_new_value"
    return (
        status,
        official,
        ";".join(matches),
        observation["snapshot"],
        observation["evidence_url"],
        observation["note"],
    )


def build_spotcheck_queue(
    rows: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, str]] = (),
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    by_village: dict[str, Mapping[str, str]] = {}
    for observation in observations:
        if observation.get("source_id") != "pos_indonesia_postcode_search":
            raise SpotcheckQueueError(
                f"unexpected observation source: {observation.get('source_id', '')}"
            )
        code = observation.get("village_code", "")
        postal = observation.get("postal_code", "")
        if code in by_village:
            raise SpotcheckQueueError(f"duplicate observation for {code}")
        if len(postal) != 5 or not postal.isdigit():
            raise SpotcheckQueueError(f"invalid observation postal code for {code}")
        by_village[code] = observation

    by_triplet: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        missing = REQUIRED_INPUT_FIELDS - set(row)
        if missing:
            raise SpotcheckQueueError(
                f"input is missing fields: {', '.join(sorted(missing))}"
            )
        triplet_id = row["triplet_cluster_id"]
        by_triplet.setdefault(triplet_id, []).append(row)

    queue: list[dict[str, str]] = []
    used_observation_codes: set[str] = set()
    for triplet_id, members in by_triplet.items():
        ordered = sorted(members, key=lambda row: row["village_code"])
        representative = ordered[0]
        declared_size = int(representative["triplet_cluster_size"])
        if declared_size != len(members):
            raise SpotcheckQueueError(
                f"triplet size mismatch for {triplet_id}: "
                f"declared {declared_size}, found {len(members)}"
            )
        observation = by_village.get(representative["village_code"])
        if observation is not None:
            for field in (
                "province_code",
                "city_code",
                "district_code",
                "village_code",
            ):
                if observation[field] != representative[field]:
                    raise SpotcheckQueueError(
                        f"observation {representative['village_code']} has "
                        f"mismatched {field}"
                    )
            used_observation_codes.add(representative["village_code"])
        observed = _observation_status(representative, observation)
        queue.append(
            {
                "queue_rank": "",
                "spotcheck_id": _stable_id(
                    (triplet_id, representative["village_code"])
                ),
                "spotcheck_priority": _priority(
                    representative["unresolved_pattern"], declared_size
                ),
                "impact_row_count": str(declared_size),
                "selection_reason": (
                    "Lowest village code representing one exact source-postal "
                    "triplet; result is evidence for follow-up, not automatic "
                    "propagation to the cluster."
                ),
                "triplet_cluster_id": triplet_id,
                "district_cluster_id": representative["district_cluster_id"],
                "district_cluster_size": representative["district_cluster_size"],
                "province_code": representative["province_code"],
                "province_name": representative["province_name"],
                "city_code": representative["city_code"],
                "city_name": representative["city_name"],
                "district_code": representative["district_code"],
                "district_name": representative["district_name"],
                "village_code": representative["village_code"],
                "village_name": representative["village_name"],
                "postal_code_diskominfo": representative[
                    "postal_code_diskominfo"
                ],
                "postal_code_open_data_jabar": representative[
                    "postal_code_open_data_jabar"
                ],
                "postal_code_kodepos_dev": representative[
                    "postal_code_kodepos_dev"
                ],
                "unresolved_pattern": representative["unresolved_pattern"],
                "search_term": representative["village_name"],
                "search_context": " | ".join(
                    (
                        representative["village_name"],
                        representative["district_name"],
                        representative["city_name"],
                        representative["province_name"],
                    )
                ),
                "official_search_url": OFFICIAL_SEARCH_URL,
                "review_status": observed[0],
                "official_postal_code": observed[1],
                "matched_sources": observed[2],
                "evidence_checked_at": observed[3],
                "evidence_url": observed[4],
                "review_note": observed[5],
            }
        )

    unused_observations = set(by_village) - used_observation_codes
    if unused_observations:
        raise SpotcheckQueueError(
            "observations do not target selected representatives: "
            + ", ".join(sorted(unused_observations))
        )

    priority_order = {
        "P0_missing_source": 0,
        "P1_high_impact": 1,
        "P2_medium_impact": 2,
        "P3_targeted": 3,
    }
    queue.sort(
        key=lambda row: (
            priority_order[row["spotcheck_priority"]],
            -int(row["impact_row_count"]),
            -int(row["district_cluster_size"]),
            row["city_code"],
            row["district_code"],
            row["triplet_cluster_id"],
            row["village_code"],
        )
    )
    for rank, row in enumerate(queue, start=1):
        row["queue_rank"] = str(rank)

    statuses = Counter(row["review_status"] for row in queue)
    priorities = Counter(row["spotcheck_priority"] for row in queue)
    observed_impact = sum(
        int(row["impact_row_count"])
        for row in queue
        if row["review_status"] != "pending"
    )
    summary: dict[str, Any] = {
        "queue_rows": len(queue),
        "represented_unresolved_rows": sum(
            int(row["impact_row_count"]) for row in queue
        ),
        "priority_counts": dict(sorted(priorities.items())),
        "review_status_counts": dict(sorted(statuses.items())),
        "observed_queue_rows": len(queue) - statuses.get("pending", 0),
        "pending_queue_rows": statuses.get("pending", 0),
        "observed_represented_rows": observed_impact,
        "policy": (
            "One representative per exact postal triplet. Manual results are "
            "evidence only and must not be propagated automatically."
        ),
    }
    return queue, summary


def _read_csv(path: Path, required: set[str] | None = None) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = set(reader.fieldnames or ())
            if required and not required <= headers:
                raise SpotcheckQueueError(
                    f"{path} missing fields: {', '.join(sorted(required - headers))}"
                )
            return [
                {key: (value or "") for key, value in row.items() if key is not None}
                for row in reader
            ]
    except FileNotFoundError as error:
        raise SpotcheckQueueError(f"input not found: {path}") from error


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=QUEUE_FIELDS)
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
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows = _read_csv(args.input, REQUIRED_INPUT_FIELDS)
        observations = (
            _read_csv(args.observations, set(OBSERVATION_FIELDS))
            if args.observations.exists()
            else []
        )
        queue, summary = build_spotcheck_queue(rows, observations)
        _write_csv(args.queue, queue)
        _write_json(
            args.summary,
            {
                **summary,
                "input_sha256": file_sha256(args.input),
                "observations_sha256": (
                    file_sha256(args.observations) if args.observations.exists() else None
                ),
                "output_sha256": {"queue": file_sha256(args.queue)},
                "schema_version": "1.0.0",
            },
        )
    except (OSError, SpotcheckQueueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(args.summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

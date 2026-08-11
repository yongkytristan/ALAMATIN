#!/usr/bin/env python3
"""Group unresolved Jawa Barat postal rows for targeted manual verification.

Rows where Diskominfo and Open Data Jabar already agree against Kodepos.dev are
kept in a separate report. The priority clustering covers rows without any
two-source decision from the previous stage and groups them by city, district,
missing/difference pattern, and exact source postal triplet.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_source_review_workbook import file_sha256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "processed" / "jabar-postal-unresolved.csv"
DEFAULT_DETAIL = (
    ROOT / "data" / "processed" / "jabar-postal-unresolved-source-disagreement.csv"
)
DEFAULT_CLUSTERS = (
    ROOT / "data" / "processed" / "jabar-postal-unresolved-clusters.csv"
)
DEFAULT_GOVERNMENT_CONFLICTS = (
    ROOT
    / "data"
    / "processed"
    / "jabar-postal-government-consensus-api-conflict.csv"
)
DEFAULT_SUMMARY = (
    ROOT / "data" / "processed" / "jabar-postal-unresolved-group-summary.json"
)
DETAIL_EXTRA_FIELDS = (
    "unresolved_pattern",
    "district_cluster_id",
    "district_cluster_size",
    "triplet_cluster_id",
    "triplet_cluster_size",
    "review_priority",
)
CLUSTER_FIELDS = (
    "district_cluster_id",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "unresolved_pattern",
    "row_count",
    "triplet_cluster_count",
    "diskominfo_postal_values",
    "open_data_jabar_postal_values",
    "kodepos_dev_postal_values",
    "example_village_codes",
    "example_village_names",
)


class UnresolvedGroupError(ValueError):
    """Raised when unresolved rows violate the expected stage contract."""


def classify_unresolved(row: Mapping[str, str]) -> str:
    diskominfo = row.get("postal_code_diskominfo", "")
    open_data_jabar = row.get("postal_code_open_data_jabar", "")
    kodepos_dev = row.get("postal_code_kodepos_dev", "")
    if diskominfo and diskominfo == open_data_jabar and kodepos_dev != diskominfo:
        return "government_sources_agree_api_differs"
    if all((diskominfo, open_data_jabar, kodepos_dev)) and len(
        {diskominfo, open_data_jabar, kodepos_dev}
    ) == 3:
        return "all_three_different"
    if not diskominfo and open_data_jabar and kodepos_dev != open_data_jabar:
        return "diskominfo_missing_api_odj_different"
    if not open_data_jabar and diskominfo and kodepos_dev != diskominfo:
        return "open_data_jabar_missing_api_diskominfo_different"
    if not kodepos_dev and diskominfo and open_data_jabar != diskominfo:
        return "api_missing_local_sources_different"
    raise UnresolvedGroupError(
        f"unrecognized unresolved pattern for {row.get('village_code', '')}"
    )


def _stable_id(prefix: str, values: Sequence[str]) -> str:
    identity = json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))
    return f"{prefix}-{hashlib.sha256(identity.encode()).hexdigest()[:12].upper()}"


def group_unresolved(
    rows: Sequence[Mapping[str, str]],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, Any],
]:
    source_disagreement: list[dict[str, str]] = []
    government_conflicts: list[dict[str, str]] = []
    patterns: Counter[str] = Counter()
    for raw in rows:
        row = {key: str(value) for key, value in raw.items()}
        if (
            row.get("verification_status") != "review_required"
            or row.get("review_required") != "yes"
            or row.get("postal_code")
            or row.get("postal_code_candidate")
        ):
            raise UnresolvedGroupError(
                f"row is not unresolved: {row.get('village_code', '')}"
            )
        pattern = classify_unresolved(row)
        patterns[pattern] += 1
        row["unresolved_pattern"] = pattern
        if pattern == "government_sources_agree_api_differs":
            government_conflicts.append(row)
        else:
            source_disagreement.append(row)

    district_groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    triplet_groups: dict[tuple[str, str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in source_disagreement:
        district_key = (
            row["city_code"],
            row["district_code"],
            row["unresolved_pattern"],
        )
        triplet_key = district_key + (
            row["postal_code_diskominfo"],
            row["postal_code_open_data_jabar"],
            row["postal_code_kodepos_dev"],
        )
        district_groups[district_key].append(row)
        triplet_groups[triplet_key].append(row)

    cluster_rows: list[dict[str, str]] = []
    for district_key, members in district_groups.items():
        city_code, district_code, pattern = district_key
        cluster_id = _stable_id("DIST", district_key)
        triplet_count = sum(1 for key in triplet_groups if key[:3] == district_key)
        ordered = sorted(members, key=lambda row: row["village_code"])
        cluster_rows.append(
            {
                "district_cluster_id": cluster_id,
                "city_code": city_code,
                "city_name": ordered[0]["city_name"],
                "district_code": district_code,
                "district_name": ordered[0]["district_name"],
                "unresolved_pattern": pattern,
                "row_count": str(len(members)),
                "triplet_cluster_count": str(triplet_count),
                "diskominfo_postal_values": ";".join(
                    sorted({row["postal_code_diskominfo"] for row in members if row["postal_code_diskominfo"]})
                ),
                "open_data_jabar_postal_values": ";".join(
                    sorted({row["postal_code_open_data_jabar"] for row in members if row["postal_code_open_data_jabar"]})
                ),
                "kodepos_dev_postal_values": ";".join(
                    sorted({row["postal_code_kodepos_dev"] for row in members if row["postal_code_kodepos_dev"]})
                ),
                "example_village_codes": ";".join(
                    row["village_code"] for row in ordered[:5]
                ),
                "example_village_names": ";".join(
                    row["village_name"] for row in ordered[:5]
                ),
            }
        )
        for row in members:
            triplet_key = district_key + (
                row["postal_code_diskominfo"],
                row["postal_code_open_data_jabar"],
                row["postal_code_kodepos_dev"],
            )
            row["district_cluster_id"] = cluster_id
            row["district_cluster_size"] = str(len(members))
            row["triplet_cluster_id"] = _stable_id("TRIP", triplet_key)
            row["triplet_cluster_size"] = str(len(triplet_groups[triplet_key]))
            row["review_priority"] = (
                "highest" if "missing" in pattern else "high"
            )

    cluster_rows.sort(
        key=lambda row: (
            -int(row["row_count"]),
            row["city_code"],
            row["district_code"],
            row["unresolved_pattern"],
        )
    )
    cluster_rank = {
        row["district_cluster_id"]: index
        for index, row in enumerate(cluster_rows)
    }
    source_disagreement.sort(
        key=lambda row: (
            cluster_rank[row["district_cluster_id"]],
            -int(row["triplet_cluster_size"]),
            row["triplet_cluster_id"],
            row["village_code"],
        )
    )
    government_conflicts.sort(key=lambda row: row["village_code"])
    summary: dict[str, Any] = {
        "total_unresolved_rows": len(rows),
        "source_disagreement_rows": len(source_disagreement),
        "government_consensus_api_conflict_rows": len(government_conflicts),
        "pattern_counts": dict(sorted(patterns.items())),
        "district_cluster_count": len(cluster_rows),
        "triplet_cluster_count": len(triplet_groups),
        "city_count": len({row["city_code"] for row in source_disagreement}),
        "district_count": len(
            {row["district_code"] for row in source_disagreement}
        ),
        "top_district_clusters": cluster_rows[:20],
    }
    return source_disagreement, cluster_rows, government_conflicts, summary


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = list(reader.fieldnames or ())
            rows = [
                {key: (value or "") for key, value in row.items() if key is not None}
                for row in reader
            ]
    except FileNotFoundError as error:
        raise UnresolvedGroupError(f"input not found: {path}") from error
    if not headers:
        raise UnresolvedGroupError(f"input has no header: {path}")
    return headers, rows


def _write_csv(
    path: Path, headers: Sequence[str], rows: Sequence[Mapping[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
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
    parser.add_argument("--detail", type=Path, default=DEFAULT_DETAIL)
    parser.add_argument("--clusters", type=Path, default=DEFAULT_CLUSTERS)
    parser.add_argument(
        "--government-conflicts", type=Path, default=DEFAULT_GOVERNMENT_CONFLICTS
    )
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        headers, rows = _read_csv(args.input)
        detail, clusters, government_conflicts, summary = group_unresolved(rows)
        _write_csv(args.detail, [*headers, *DETAIL_EXTRA_FIELDS], detail)
        _write_csv(args.clusters, CLUSTER_FIELDS, clusters)
        _write_csv(
            args.government_conflicts,
            [*headers, "unresolved_pattern"],
            government_conflicts,
        )
        _write_json(
            args.summary,
            {
                **summary,
                "input_sha256": file_sha256(args.input),
                "output_sha256": {
                    "clusters": file_sha256(args.clusters),
                    "detail": file_sha256(args.detail),
                    "government_conflicts": file_sha256(args.government_conflicts),
                },
                "schema_version": "1.0.0",
            },
        )
    except (UnresolvedGroupError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(args.summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

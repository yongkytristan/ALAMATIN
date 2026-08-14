#!/usr/bin/env python3
"""Select a stratified candidate pool for ALM-012's public-address benchmark.

Reads the raw NPSN rows fetched by scripts/fetch_npsn_school_addresses.py,
keeps only an explicit allowlist of public-facility fields (never a personal
name, personal phone number, or household address), and draws a deterministic
sample spread across school level and kabupaten/kota so the benchmark is not
dominated by one region.

This script only selects and redacts candidate rows. It does not invent or
rewrite address text -- a human must still write the natural-language,
"as if typed at checkout" version; see
scripts/build_human_noised_benchmark.py for that step.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = ROOT / "data" / "interim" / "school-address-benchmark"
DEFAULT_OUTPUT = DEFAULT_INPUT_DIR / "candidates.csv"
DEFAULT_SUMMARY = DEFAULT_INPUT_DIR / "candidates-summary.json"
MIN_ADDRESS_LENGTH = 8
OUTPUT_FIELDS = (
    "base_address_id",
    "source_id",
    "source_record_id",
    "school_level",
    "school_name",
    "status_sekolah",
    "kabupaten_kota",
    "kecamatan",
    "reference_address",
    "source_year",
)


class CandidateSelectionError(ValueError):
    """Raised when candidates cannot be selected safely."""


def _load_raw(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CandidateSelectionError(f"raw fetch file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise CandidateSelectionError(f"raw fetch file is not valid JSON: {path}") from error


def extract_candidates(level: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    source_id = payload["source_id"]
    seen_npsn: set[str] = set()
    candidates: list[dict[str, str]] = []
    for row in payload["rows"]:
        npsn = str(row.get("npsn", "")).strip()
        address = str(row.get("alamat_sekolah", "")).strip()
        kabupaten = str(row.get("nama_kabupaten_kota", "")).strip()
        kecamatan = str(row.get("kemendagri_nama_kecamatan", "")).strip()
        if not npsn or npsn in seen_npsn:
            continue
        if len(address) < MIN_ADDRESS_LENGTH or not kabupaten or not kecamatan:
            continue
        seen_npsn.add(npsn)
        candidates.append(
            {
                "base_address_id": f"npsn_{level}_{npsn}",
                "source_id": source_id,
                "source_record_id": npsn,
                "school_level": level.upper(),
                "school_name": str(row.get("nama_sekolah", "")).strip(),
                "status_sekolah": str(row.get("status_sekolah", "")).strip(),
                "kabupaten_kota": kabupaten,
                "kecamatan": kecamatan,
                "reference_address": address,
                "source_year": str(row.get("tahun", "")).strip(),
            }
        )
    return candidates


def stratified_select(
    candidates: list[dict[str, str]], target: int, rng: random.Random
) -> list[dict[str, str]]:
    if not candidates:
        raise CandidateSelectionError("no candidates available to select from")
    buckets: dict[tuple[str, str], list[dict[str, str]]] = {}
    for candidate in candidates:
        key = (candidate["school_level"], candidate["kabupaten_kota"])
        buckets.setdefault(key, []).append(candidate)
    for pool in buckets.values():
        rng.shuffle(pool)

    ordered_keys = sorted(buckets)
    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()
    cursors = {key: 0 for key in ordered_keys}
    while len(selected) < min(target, len(candidates)):
        progressed = False
        for key in ordered_keys:
            if len(selected) >= target:
                break
            pool = buckets[key]
            cursor = cursors[key]
            if cursor >= len(pool):
                continue
            candidate = pool[cursor]
            cursors[key] = cursor + 1
            if candidate["base_address_id"] in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(candidate["base_address_id"])
            progressed = True
        if not progressed:
            break
    return sorted(selected, key=lambda row: row["base_address_id"])


def write_csv_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--levels", nargs="+", default=["sd", "sma"])
    parser.add_argument("--target", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.target < 1:
            raise CandidateSelectionError("--target must be positive")
        all_candidates: list[dict[str, str]] = []
        pool_counts: dict[str, int] = {}
        for level in args.levels:
            raw_path = args.input_dir / f"npsn-{level}-raw.json"
            payload = _load_raw(raw_path)
            level_candidates = extract_candidates(level, payload)
            pool_counts[level] = len(level_candidates)
            all_candidates.extend(level_candidates)

        selected = stratified_select(all_candidates, args.target, random.Random(args.seed))
        write_csv_atomic(args.output, selected)

        by_kabupaten: dict[str, int] = {}
        by_level: dict[str, int] = {}
        for row in selected:
            by_kabupaten[row["kabupaten_kota"]] = by_kabupaten.get(row["kabupaten_kota"], 0) + 1
            by_level[row["school_level"]] = by_level.get(row["school_level"], 0) + 1

        summary = {
            "schema_version": "1.0.0",
            "seed": args.seed,
            "target": args.target,
            "pool_size_after_filtering": pool_counts,
            "selected_count": len(selected),
            "selected_by_level": dict(sorted(by_level.items())),
            "selected_by_kabupaten_kota": dict(sorted(by_kabupaten.items())),
            "kabupaten_kota_covered": len(by_kabupaten),
        }
        write_json_atomic(args.summary, summary)
    except (OSError, CandidateSelectionError) as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

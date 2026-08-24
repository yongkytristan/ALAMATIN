#!/usr/bin/env python3
"""Assemble ALM-014's five evaluation splits and seal the real test.

Splits (per docs/evaluation_protocol.md sections 7-8):

- `synthetic_train` / `synthetic_dev` / `synthetic_test`: already produced by
  scripts/generate_synthetic_addresses.py (data/synthetic/{train,val,test}.json).
  This script only records their counts and content hashes.
- `real_dev`: a governed subset of the ALM-013 gold human-noised benchmark for
  repeated ML iteration. Its row-level content is not redistributed.
- `sealed_real_test`: the remaining gold examples. The full content and the
  full manifest (ordered example IDs, per-item hashes) are written ONLY to
  `data/private/` (gitignored, never committed). A separate, boundary-safe
  manifest -- opaque split id, count, schema/taxonomy versions, creation
  timestamp, and a single SHA-256 content hash, nothing that reveals content
  -- is written to the restricted evidence archive, matching the information
  boundary in evaluation_protocol.md section 7.

The 70/130 real_dev/sealed_real_test split is stratified by kabupaten/kota so
neither split is skewed toward one region, using candidates.csv (the only
place kabupaten_kota is recorded for these examples).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.evaluation_metrics import canonical_json_sha256  # noqa: E402
from alamatin.label_schema import SCHEMA_VERSION, validate_bio_sequence  # noqa: E402

DEFAULT_GOLD = ROOT / "data" / "interim" / "school-address-benchmark" / "gold-labels.json"
DEFAULT_CANDIDATES = ROOT / "data" / "interim" / "school-address-benchmark" / "candidates.csv"
DEFAULT_SYNTHETIC_DIR = ROOT / "data" / "synthetic"
DEFAULT_SPLITS_DIR = ROOT / "data" / "interim" / "evaluation-splits"
DEFAULT_PRIVATE_DIR = ROOT / "data" / "private" / "sealed-real-test"
TAXONOMY_VERSION = "1.0.0"
SPLIT_VERSION = "sealed_real_test_v1"
REAL_DEV_TARGET = 70
SEALED_TARGET = 130


class SplitBuildError(ValueError):
    """Raised when the evaluation splits cannot be assembled safely."""


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stratified_split(
    examples: list[dict[str, Any]],
    kabupaten_by_id: dict[str, str],
    real_dev_target: int,
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for example in examples:
        kabupaten = kabupaten_by_id.get(example["base_address_id"])
        if kabupaten is None:
            raise SplitBuildError(f"{example['base_address_id']}: no kabupaten_kota on record")
        buckets.setdefault(kabupaten, []).append(example)
    for pool in buckets.values():
        rng.shuffle(pool)

    total = len(examples)
    real_dev: list[dict[str, Any]] = []
    sealed: list[dict[str, Any]] = []
    for kabupaten in sorted(buckets):
        pool = buckets[kabupaten]
        share = round(len(pool) * real_dev_target / total)
        real_dev.extend(pool[:share])
        sealed.extend(pool[share:])

    # Rounding can drift the total slightly off target; correct deterministically.
    while len(real_dev) < real_dev_target and sealed:
        real_dev.append(sealed.pop())
    while len(real_dev) > real_dev_target and real_dev:
        sealed.append(real_dev.pop())

    return (
        sorted(real_dev, key=lambda item: item["base_address_id"]),
        sorted(sealed, key=lambda item: item["base_address_id"]),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--synthetic-dir", type=Path, default=DEFAULT_SYNTHETIC_DIR)
    parser.add_argument("--splits-dir", type=Path, default=DEFAULT_SPLITS_DIR)
    parser.add_argument("--private-dir", type=Path, default=DEFAULT_PRIVATE_DIR)
    parser.add_argument("--real-dev-target", type=int, default=REAL_DEV_TARGET)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument(
        "--custodian",
        default="Data & Research Lead (project owner); must not also act as ML & Evaluation Lead",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        gold = json.loads(args.gold.read_text(encoding="utf-8"))
        with args.candidates.open("r", encoding="utf-8-sig", newline="") as stream:
            kabupaten_by_id = {row["base_address_id"]: row["kabupaten_kota"] for row in csv.DictReader(stream)}

        for example in gold["examples"]:
            valid, reason = validate_bio_sequence(example["labels"])
            if not valid:
                raise SplitBuildError(f"{example['base_address_id']}: invalid gold labels: {reason}")

        real_dev, sealed = stratified_split(
            gold["examples"], kabupaten_by_id, args.real_dev_target, random.Random(args.seed)
        )

        synthetic_summary = {}
        for name, split_key in (("train", "synthetic_train"), ("val", "synthetic_dev"), ("test", "synthetic_test")):
            path = args.synthetic_dir / f"{name}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            synthetic_summary[split_key] = {
                "example_count": len(payload["examples"]),
                "sha256": _file_sha256(path),
            }

        created_at = datetime.now(timezone.utc).isoformat()

        real_dev_payload = {
            "split": "real_dev",
            "schema_version": SCHEMA_VERSION,
            "created_at": created_at,
            "seed": args.seed,
            "example_count": len(real_dev),
            "examples": real_dev,
        }
        args.splits_dir.mkdir(parents=True, exist_ok=True)
        real_dev_path = args.splits_dir / "real_dev.json"
        temp_real_dev = real_dev_path.with_name(f".{real_dev_path.name}.part")
        temp_real_dev.write_text(
            json.dumps(real_dev_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_real_dev.replace(real_dev_path)

        sealed_payload = {
            "split": "sealed_real_test",
            "split_version": SPLIT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "created_at": created_at,
            "seed": args.seed,
            "example_count": len(sealed),
            "examples": sealed,
        }
        args.private_dir.mkdir(parents=True, exist_ok=True)
        sealed_path = args.private_dir / "sealed_real_test.json"
        temp_sealed = sealed_path.with_name(f".{sealed_path.name}.part")
        temp_sealed.write_text(
            json.dumps(sealed_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_sealed.replace(sealed_path)

        content_hash = canonical_json_sha256(sealed_payload)
        full_manifest = {
            "split_version": SPLIT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "taxonomy_version": TAXONOMY_VERSION,
            "created_at": created_at,
            "example_count": len(sealed),
            "content_sha256": content_hash,
            "ordered_example_ids": [example["base_address_id"] for example in sealed],
            "per_item_sha256": {
                example["base_address_id"]: canonical_json_sha256(example) for example in sealed
            },
            "custodian": args.custodian,
        }
        full_manifest_path = args.private_dir / "sealed-test-full-manifest.json"
        temp_full = full_manifest_path.with_name(f".{full_manifest_path.name}.part")
        temp_full.write_text(
            json.dumps(full_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_full.replace(full_manifest_path)

        boundary_manifest = {
            "split_version": SPLIT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "taxonomy_version": TAXONOMY_VERSION,
            "created_at": created_at,
            "example_count": len(sealed),
            "content_sha256": content_hash,
            "custodian": args.custodian,
            "access_control_location": "data/private/sealed-real-test/ (gitignored, local to custodian only)",
            "note": (
                "No example IDs, label distribution, or content are included here by design -- "
                "see evaluation_protocol.md section 7. The full manifest (ordered IDs, per-item "
                "hashes) exists only in the custodian's restricted copy."
            ),
        }
        boundary_manifest_path = args.splits_dir / "sealed-test-boundary-manifest.json"
        temp_boundary = boundary_manifest_path.with_name(f".{boundary_manifest_path.name}.part")
        temp_boundary.write_text(
            json.dumps(boundary_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_boundary.replace(boundary_manifest_path)

        summary = {
            "schema_version": SCHEMA_VERSION,
            "created_at": created_at,
            "splits": {
                **synthetic_summary,
                "real_dev": {"example_count": len(real_dev), "sha256": _file_sha256(real_dev_path)},
                "sealed_real_test": {
                    "example_count": len(sealed),
                    "content_sha256": content_hash,
                    "manifest": "sealed-test-boundary-manifest.json",
                },
            },
        }
        summary_path = args.splits_dir / "split-summary.json"
        temp_summary = summary_path.with_name(f".{summary_path.name}.part")
        temp_summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_summary.replace(summary_path)
    except (OSError, KeyError, SplitBuildError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

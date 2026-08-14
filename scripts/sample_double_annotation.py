#!/usr/bin/env python3
"""Draw the ALM-013 double-annotation sample and build a blind worksheet.

The sample always includes every example the automated pass flagged as
uncertain, plus enough additional randomly selected examples to reach the
target size -- so the human reviewer both fixes known weak spots and gives a
genuine, representative read on the automated pass's overall reliability.

The worksheet never shows the automated candidate label. The reviewer sees
only the tokens (index-prefixed) and fills in `spans` with their own
independent judgement, in the form ``TYPE:start-end;TYPE:start-end`` (end
exclusive), for example ``JALAN:0-2;KECAMATAN:4-5;KOTA_KABUPATEN:7-8``.
Tokens with no entity are left out of `spans` -- they default to ``O``.
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
DEFAULT_CANDIDATES = ROOT / "data" / "interim" / "school-address-benchmark" / "bio-candidates.json"
DEFAULT_WORKSHEET = ROOT / "data" / "interim" / "school-address-benchmark" / "double-annotation-worksheet.csv"
DEFAULT_MANIFEST = ROOT / "data" / "interim" / "school-address-benchmark" / "double-annotation-manifest.json"
WORKSHEET_FIELDS = ("base_address_id", "indexed_tokens", "spans", "annotator_id", "notes")


class SamplingError(ValueError):
    """Raised when a double-annotation sample cannot be drawn safely."""


def select_sample(
    examples: list[dict[str, Any]], target: int, rng: random.Random
) -> list[dict[str, Any]]:
    if not examples:
        raise SamplingError("no candidate examples to sample from")
    flagged = [example for example in examples if example["flags"]]
    unflagged = [example for example in examples if not example["flags"]]
    rng.shuffle(unflagged)

    selected = list(flagged)
    selected_ids = {example["base_address_id"] for example in selected}
    for example in unflagged:
        if len(selected) >= target:
            break
        if example["base_address_id"] not in selected_ids:
            selected.append(example)
            selected_ids.add(example["base_address_id"])
    return sorted(selected, key=lambda item: item["base_address_id"])


def _indexed_tokens(tokens: list[str]) -> str:
    return " ".join(f"{index}:{token}" for index, token in enumerate(tokens))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--target", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.target < 1:
            raise SamplingError("--target must be positive")
        payload = json.loads(args.candidates.read_text(encoding="utf-8"))
        examples = payload["examples"]
        sample = select_sample(examples, args.target, random.Random(args.seed))

        worksheet_rows = [
            {
                "base_address_id": example["base_address_id"],
                "indexed_tokens": _indexed_tokens(example["tokens"]),
                "spans": "",
                "annotator_id": "",
                "notes": "",
            }
            for example in sample
        ]
        args.worksheet.parent.mkdir(parents=True, exist_ok=True)
        temp_worksheet = args.worksheet.with_name(f".{args.worksheet.name}.part")
        with temp_worksheet.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=WORKSHEET_FIELDS)
            writer.writeheader()
            writer.writerows(worksheet_rows)
        temp_worksheet.replace(args.worksheet)

        manifest = {
            "schema_version": "1.0.0",
            "seed": args.seed,
            "target": args.target,
            "sample_size": len(sample),
            "flagged_in_sample": sum(1 for example in sample if example["flags"]),
            "unflagged_in_sample": sum(1 for example in sample if not example["flags"]),
            "total_pool": len(examples),
            "sampled_ids": sorted(example["base_address_id"] for example in sample),
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        temp_manifest = args.manifest.with_name(f".{args.manifest.name}.part")
        temp_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_manifest.replace(args.manifest)
    except (OSError, KeyError, SamplingError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in manifest.items() if k != "sampled_ids"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

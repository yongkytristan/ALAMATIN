#!/usr/bin/env python3
"""Draw a deterministic, category-stratified audit sample from synthetic splits.

ALM-011 requires sampling 50 rows across noise categories for manual spot
review. This script never selects a value or repairs a label; it only picks
which already-generated examples the human/reviewer audit log should cover.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPLIT_DIR = ROOT / "data" / "synthetic"
DEFAULT_OUTPUT = ROOT / "data" / "synthetic" / "audit-sample.json"


class AuditSampleError(ValueError):
    """Raised when a stratified sample cannot be drawn safely."""


def _load_examples(split_dir: Path) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for split_name in ("train", "val", "test"):
        payload = json.loads((split_dir / f"{split_name}.json").read_text(encoding="utf-8"))
        for example in payload["examples"]:
            examples.append({**example, "split": split_name})
    if not examples:
        raise AuditSampleError("no examples found to sample from")
    return examples


def stratified_sample(
    examples: list[dict[str, Any]], sample_size: int, rng: random.Random
) -> list[dict[str, Any]]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    for example in examples:
        for category in example["categories"]:
            by_category.setdefault(category, []).append(example)

    categories = sorted(by_category)
    if not categories:
        raise AuditSampleError("no noise categories present in the examples")

    selected: dict[str, dict[str, Any]] = {}
    order = list(categories)
    rng.shuffle(order)
    for category in order:
        if len(selected) >= sample_size:
            break
        pool = by_category[category]
        rng.shuffle(pool)
        for candidate in pool:
            if candidate["id"] not in selected:
                selected[candidate["id"]] = candidate
                break

    remaining_pool = [example for example in examples if example["id"] not in selected]
    rng.shuffle(remaining_pool)
    for example in remaining_pool:
        if len(selected) >= sample_size:
            break
        selected[example["id"]] = example

    ordered = sorted(selected.values(), key=lambda example: example["id"])
    return ordered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=110)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        examples = _load_examples(args.split_dir)
        sample = stratified_sample(examples, args.sample_size, random.Random(args.seed))
        category_counts: dict[str, int] = {}
        for example in sample:
            for category in example["categories"]:
                category_counts[category] = category_counts.get(category, 0) + 1
        payload = {
            "seed": args.seed,
            "sample_size": len(sample),
            "requested_size": args.sample_size,
            "category_coverage": dict(sorted(category_counts.items())),
            "examples": [
                {
                    "id": example["id"],
                    "split": example["split"],
                    "categories": example["categories"],
                    "text": " ".join(example["tokens"]),
                    "tokens": example["tokens"],
                    "labels": example["labels"],
                }
                for example in sample
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.part")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(args.output)
    except (AuditSampleError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in payload.items() if k != "examples"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Assemble ALM-013 gold labels for the human-noised public-address benchmark.

Merges three inputs into one governed gold file:

- the automated candidate pass (scripts/annotate_human_noised_benchmark.py)
  for every example NOT in the double-annotation sample;
- the human reviewer's independent labels
  (scripts/compute_annotation_agreement.py's ``--human-labels`` output) for
  every example IN the sample;
- adjudicated overrides (a completed ``adjudication-log.csv``) applied on top
  of the human labels wherever the human and the automated pass disagreed.

Every example not in the double-annotation sample is recorded as
``automated_accepted``, not individually re-verified -- its trustworthiness
rests on the measured agreement rate from the sampled subset
(``annotation-agreement.json``), not a per-example human sign-off. This is
disclosed in the output, not hidden.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.label_schema import BIO_LABELS, ENTITY_TYPES, SCHEMA_VERSION, validate_bio_sequence  # noqa: E402

DEFAULT_CANDIDATES = ROOT / "data" / "interim" / "school-address-benchmark" / "bio-candidates.json"
DEFAULT_MANIFEST = ROOT / "data" / "interim" / "school-address-benchmark" / "double-annotation-manifest.json"
DEFAULT_HUMAN_LABELS = ROOT / "data" / "interim" / "school-address-benchmark" / "double-annotation-human-labels.json"
DEFAULT_ADJUDICATION = ROOT / "data" / "interim" / "school-address-benchmark" / "adjudication-log.csv"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "school-address-benchmark" / "gold-labels.json"
AUTOMATED_ANNOTATOR_ID = "auto-rule-v1"


class GoldAssemblyError(ValueError):
    """Raised when the gold label set cannot be assembled safely."""


def _apply_adjudication(labels: list[str], start: int, end: int, decision: str, base_id: str) -> None:
    decision = decision.strip()
    if decision == "O":
        for index in range(start, end):
            labels[index] = "O"
        return
    if decision not in ENTITY_TYPES:
        raise GoldAssemblyError(f"{base_id}: invalid adjudicated_label {decision!r}")
    for position, index in enumerate(range(start, end)):
        labels[index] = f"{'B' if position == 0 else 'I'}-{decision}"


def assemble(
    candidates: dict[str, Any],
    manifest: dict[str, Any],
    human_labels_by_id: dict[str, Any],
    adjudication_rows: list[dict[str, str]],
) -> dict[str, Any]:
    sampled_ids = set(manifest["sampled_ids"])
    missing_human = sampled_ids - human_labels_by_id.keys()
    if missing_human:
        raise GoldAssemblyError(f"sampled but not reviewed: {sorted(missing_human)}")

    unresolved = [
        f"{row['base_address_id']} [{row['start']}-{row['end']}]"
        for row in adjudication_rows
        if not row["adjudicated_label"].strip()
    ]
    if unresolved:
        raise GoldAssemblyError("unresolved adjudication rows: " + ", ".join(unresolved))

    adjudication_by_id: dict[str, list[dict[str, str]]] = {}
    for row in adjudication_rows:
        adjudication_by_id.setdefault(row["base_address_id"], []).append(row)

    examples = []
    for candidate in candidates["examples"]:
        base_id = candidate["base_address_id"]
        if base_id in sampled_ids:
            human = human_labels_by_id[base_id]
            labels = list(human["labels"])
            tokens = human["tokens"]
            for row in adjudication_by_id.get(base_id, []):
                _apply_adjudication(labels, int(row["start"]), int(row["end"]), row["adjudicated_label"], base_id)
            provenance = (
                "double_annotated_adjudicated"
                if base_id in adjudication_by_id
                else "double_annotated_agreed"
            )
            annotator_id = human["annotator_id"]
        else:
            tokens = candidate["tokens"]
            labels = list(candidate["labels"])
            provenance = "automated_accepted"
            annotator_id = AUTOMATED_ANNOTATOR_ID

        valid, reason = validate_bio_sequence(labels)
        if not valid:
            raise GoldAssemblyError(f"{base_id}: final labels are invalid: {reason}")

        examples.append(
            {
                "base_address_id": base_id,
                "tokens": tokens,
                "labels": labels,
                "status": "gold",
                "annotation_provenance": provenance,
                "annotator_id": annotator_id,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "label_order": list(BIO_LABELS),
        "example_count": len(examples),
        "double_annotated_count": len(sampled_ids),
        "automated_accepted_count": len(examples) - len(sampled_ids),
        "examples": sorted(examples, key=lambda item: item["base_address_id"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--human-labels", type=Path, default=DEFAULT_HUMAN_LABELS)
    parser.add_argument("--adjudication", type=Path, default=DEFAULT_ADJUDICATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        human_labels_by_id = json.loads(args.human_labels.read_text(encoding="utf-8"))
        with args.adjudication.open("r", encoding="utf-8-sig", newline="") as stream:
            adjudication_rows = list(csv.DictReader(stream))

        payload = assemble(candidates, manifest, human_labels_by_id, adjudication_rows)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.part")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(args.output)
    except (OSError, KeyError, GoldAssemblyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {k: v for k, v in payload.items() if k != "examples"},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

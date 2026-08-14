#!/usr/bin/env python3
"""Compute automated-vs-human agreement for the ALM-013 double-annotation sample.

Reads a completed double-annotation worksheet (see
scripts/sample_double_annotation.py), converts each reviewer's ``spans``
notation into a full BIO label sequence, and compares it against the
automated candidate label for the same example using the shared entity
metric functions (treating the human's independent labels as gold and the
automated pass as the prediction being scored). Every example where the two
disagree is written to an adjudication worksheet for a human to resolve --
this script never picks a winner on its own.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.evaluation_metrics import (  # noqa: E402
    entity_metrics,
    entity_metrics_by_type,
    extract_bio_entities,
)
from alamatin.label_schema import ENTITY_TYPES, validate_bio_sequence  # noqa: E402

DEFAULT_CANDIDATES = ROOT / "data" / "interim" / "school-address-benchmark" / "bio-candidates.json"
DEFAULT_WORKSHEET = ROOT / "data" / "interim" / "school-address-benchmark" / "double-annotation-worksheet.csv"
DEFAULT_AGREEMENT = ROOT / "data" / "interim" / "school-address-benchmark" / "annotation-agreement.json"
DEFAULT_ADJUDICATION = ROOT / "data" / "interim" / "school-address-benchmark" / "adjudication-log.csv"
DEFAULT_HUMAN_LABELS = ROOT / "data" / "interim" / "school-address-benchmark" / "double-annotation-human-labels.json"
SPAN_PATTERN = re.compile(r"^([A-Z_]+):(\d+)-(\d+)$")
ADJUDICATION_FIELDS = (
    "base_address_id",
    "start",
    "end",
    "span_text",
    "automated_label",
    "human_label",
    "adjudicated_label",
    "rationale",
)


class AgreementError(ValueError):
    """Raised when the completed worksheet cannot be scored safely."""


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        return ","


def parse_spans(spans_text: str, token_count: int, base_address_id: str) -> list[str]:
    labels = ["O"] * token_count
    spans_text = spans_text.strip()
    if not spans_text:
        return labels
    for chunk in spans_text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = SPAN_PATTERN.match(chunk)
        if not match:
            raise AgreementError(f"{base_address_id}: unparseable span {chunk!r}")
        entity, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        if entity not in ENTITY_TYPES:
            raise AgreementError(f"{base_address_id}: unknown entity type {entity!r}")
        if not (0 <= start < end <= token_count):
            raise AgreementError(f"{base_address_id}: span out of range {chunk!r}")
        for index in range(start, end):
            labels[index] = f"{'B' if index == start else 'I'}-{entity}"
    return labels


def _span_text(tokens: list[str], span: tuple[str, int, int]) -> str:
    _, start, end = span
    return " ".join(tokens[start:end])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--agreement", type=Path, default=DEFAULT_AGREEMENT)
    parser.add_argument("--adjudication", type=Path, default=DEFAULT_ADJUDICATION)
    parser.add_argument("--human-labels", type=Path, default=DEFAULT_HUMAN_LABELS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidates_by_id = {
            example["base_address_id"]: example
            for example in json.loads(args.candidates.read_text(encoding="utf-8"))["examples"]
        }
        with args.worksheet.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(4096)
            stream.seek(0)
            worksheet_rows = list(csv.DictReader(stream, delimiter=_sniff_delimiter(sample)))
        if not worksheet_rows:
            raise AgreementError("worksheet has no rows")

        gold_sequences: list[list[str]] = []
        predicted_sequences: list[list[str]] = []
        adjudication_rows: list[dict[str, str]] = []
        human_labels_by_id: dict[str, dict[str, Any]] = {}
        missing_review: list[str] = []

        for row in worksheet_rows:
            base_id = row["base_address_id"]
            candidate = candidates_by_id.get(base_id)
            if candidate is None:
                raise AgreementError(f"{base_id}: not found in candidate pool")
            if not row["spans"].strip() and not row["annotator_id"].strip():
                missing_review.append(base_id)
                continue
            if not row["annotator_id"].strip():
                raise AgreementError(f"{base_id}: annotator_id is empty")

            tokens = candidate["tokens"]
            human_labels = parse_spans(row["spans"], len(tokens), base_id)
            valid, reason = validate_bio_sequence(human_labels)
            if not valid:
                raise AgreementError(f"{base_id}: human spans produce invalid BIO: {reason}")

            gold_sequences.append(human_labels)
            predicted_sequences.append(candidate["labels"])
            human_labels_by_id[base_id] = {
                "tokens": tokens,
                "labels": human_labels,
                "annotator_id": row["annotator_id"].strip(),
            }

            human_spans = extract_bio_entities(human_labels)
            automated_spans = extract_bio_entities(candidate["labels"])
            if human_spans != automated_spans:
                for span in sorted(human_spans - automated_spans):
                    adjudication_rows.append(
                        {
                            "base_address_id": base_id,
                            "start": span[1],
                            "end": span[2],
                            "span_text": _span_text(tokens, span),
                            "automated_label": "O",
                            "human_label": span[0],
                            "adjudicated_label": "",
                            "rationale": "",
                        }
                    )
                for span in sorted(automated_spans - human_spans):
                    adjudication_rows.append(
                        {
                            "base_address_id": base_id,
                            "start": span[1],
                            "end": span[2],
                            "span_text": _span_text(tokens, span),
                            "automated_label": span[0],
                            "human_label": "O",
                            "adjudicated_label": "",
                            "rationale": "",
                        }
                    )

        if missing_review:
            raise AgreementError(
                "worksheet still has unreviewed rows: " + ", ".join(sorted(missing_review))
            )

        overall = entity_metrics(gold_sequences, predicted_sequences)
        by_type = entity_metrics_by_type(gold_sequences, predicted_sequences)

        disagreement_ids = {row["base_address_id"] for row in adjudication_rows}
        report = {
            "schema_version": "1.0.0",
            "reviewed_count": len(gold_sequences),
            "exact_match_examples": len(gold_sequences) - len(disagreement_ids),
            "disagreement_examples": len(disagreement_ids),
            "overall": {
                "true_positive": overall.true_positive,
                "false_positive": overall.false_positive,
                "false_negative": overall.false_negative,
                "precision": overall.precision,
                "recall": overall.recall,
                "f1": overall.f1,
            },
            "by_type": {
                entity: {
                    "true_positive": result.true_positive,
                    "false_positive": result.false_positive,
                    "false_negative": result.false_negative,
                    "precision": result.precision,
                    "recall": result.recall,
                    "f1": result.f1,
                }
                for entity, result in by_type.items()
            },
        }
        args.agreement.parent.mkdir(parents=True, exist_ok=True)
        temp_agreement = args.agreement.with_name(f".{args.agreement.name}.part")
        temp_agreement.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_agreement.replace(args.agreement)

        args.adjudication.parent.mkdir(parents=True, exist_ok=True)
        temp_adjudication = args.adjudication.with_name(f".{args.adjudication.name}.part")
        with temp_adjudication.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=ADJUDICATION_FIELDS)
            writer.writeheader()
            writer.writerows(adjudication_rows)
        temp_adjudication.replace(args.adjudication)

        args.human_labels.parent.mkdir(parents=True, exist_ok=True)
        temp_human_labels = args.human_labels.with_name(f".{args.human_labels.name}.part")
        temp_human_labels.write_text(
            json.dumps(human_labels_by_id, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_human_labels.replace(args.human_labels)
    except (OSError, KeyError, AgreementError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in report.items() if k != "by_type"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

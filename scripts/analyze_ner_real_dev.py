#!/usr/bin/env python3
"""Run NER v1 on real_dev and produce the ALM-019 evidence package.

This command refuses sealed-test paths and payloads. It stores token labels and
exact spans, but never logits or uncalibrated probability-like values.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from alamatin.evaluation_metrics import (  # noqa: E402
    critical_exact_match,
    entity_metrics,
    entity_metrics_by_type,
    latency_summary_ms,
)
from alamatin.real_dev_error_analysis import (  # noqa: E402
    ERROR_CATEGORIES,
    build_error_case,
    build_error_matrix,
    classify_error_categories,
    repair_orphan_i_tags,
    validate_real_dev_payload,
)


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_sources(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["base_address_id"]: row for row in csv.DictReader(handle)}


def metric_record(result: Any) -> dict[str, Any]:
    return asdict(result)


def build_action_register(cases: list[dict[str, Any]]) -> dict[str, Any]:
    invalid = [case["case_id"] for case in cases if case["bio_repairs"]]
    generator = [case["case_id"] for case in cases if "generator" in case["components"]]
    landmark = [case["case_id"] for case in cases if "landmark" in case["categories"]]
    annotation = [
        case["case_id"]
        for case in cases
        if case["annotation_provenance"] == "automated_accepted"
    ]
    return {
        "schema_version": "1.0.0",
        "actions": [
            {
                "action_id": "ALM019-A01",
                "priority": "P0",
                "owner_component": "validator",
                "decision": "Add a frozen BIO decoder/validator before candidate comparison.",
                "target_issue": 20,
                "selection_basis": "P0: invalid system output observed in 14/70 real_dev examples.",
                "evidence_case_count": len(invalid),
                "evidence_case_ids": invalid,
            },
            {
                "action_id": "ALM019-A02",
                "priority": "P0",
                "owner_component": "generator",
                "decision": "Add synthetic variants matching observed surface categories, then run a controlled real_dev comparison.",
                "target_issue": 20,
                "selection_basis": "P0 hypothesis: surface-category failures are frequent and usually break critical exact match.",
                "evidence_case_count": len(generator),
                "evidence_case_ids": generator,
            },
            {
                "action_id": "ALM019-A03",
                "priority": "P1",
                "owner_component": "model",
                "decision": "Measure a targeted DETAIL_LOKASI candidate; do not block the deadline candidate if critical exact match does not improve.",
                "target_issue": 20,
                "selection_basis": "P1: low-frequency landmark slice with limited critical-field impact.",
                "evidence_case_count": len(landmark),
                "evidence_case_ids": landmark,
            },
            {
                "action_id": "ALM019-A04",
                "priority": "P1",
                "owner_component": "annotation",
                "decision": "Spot-review automated gold cases touched by model errors before treating them as training corrections.",
                "target_issue": 20,
                "selection_basis": "P1 safeguard: high frequency, but no annotation defect is confirmed.",
                "evidence_case_count": len(annotation),
                "evidence_case_ids": annotation,
            },
        ],
        "deferred_before_deadline": [
            {
                "failure_family": "normalizer/administrative-reference failures",
                "reason": "Not executed by this NER-only analysis; evaluate in the integrated pipeline rather than attributing them to NER.",
                "follow_up": "ALM-028/ALM-034",
            },
            {
                "failure_family": "genuinely ambiguous-region resolution",
                "reason": "Requires validator/reference evidence and a clarification contract; NER labels alone cannot resolve it safely.",
                "follow_up": "ALM-028",
            },
            {
                "failure_family": "rare landmark recall",
                "reason": "Track as P1 unless a controlled ALM-020 candidate improves it without reducing critical fields.",
                "follow_up": "ALM-020",
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "data" / "interim" / "evaluation-splits" / "real_dev.json",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        default=ROOT / "models" / "ner-v1-release" / "ner-v1",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "data" / "interim" / "school-address-benchmark" / "candidates.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "experiments" / "ner-v1-real-dev",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--checkpoint-name", default="ner-v1.0.0")
    args = parser.parse_args(argv)

    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    validate_real_dev_payload(payload, str(args.dataset.resolve()))
    if args.batch_size < 1:
        raise ValueError("batch size must be positive")

    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    from alamatin.token_alignment import predictions_to_word_labels

    artifact = args.artifact.resolve()
    model_file = artifact / "model.safetensors"
    tokenizer = AutoTokenizer.from_pretrained(artifact)
    model = AutoModelForTokenClassification.from_pretrained(artifact)
    model.eval()
    torch.set_num_threads(1)

    examples = payload["examples"]
    source_records = read_sources(args.sources)
    raw_predictions: list[list[str]] = []
    latencies_ms: list[float] = []
    for start in range(0, len(examples), args.batch_size):
        batch = examples[start : start + args.batch_size]
        encoding = tokenizer(
            [example["tokens"] for example in batch],
            is_split_into_words=True,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        started = time.perf_counter()
        with torch.no_grad():
            predicted_ids = model(**encoding).logits.argmax(dim=-1).tolist()
        batch_elapsed = (time.perf_counter() - started) * 1000
        per_example_latency = batch_elapsed / len(batch)
        latencies_ms.extend([per_example_latency] * len(batch))
        for batch_index, example in enumerate(batch):
            raw_predictions.append(
                predictions_to_word_labels(
                    predicted_ids[batch_index],
                    encoding.word_ids(batch_index=batch_index),
                    word_count=len(example["tokens"]),
                )
            )

    evaluated_predictions = [
        repair_orphan_i_tags(labels)[0] for labels in raw_predictions
    ]
    gold = [list(example["labels"]) for example in examples]
    overall = entity_metrics(gold, evaluated_predictions)
    by_type = entity_metrics_by_type(gold, evaluated_predictions)
    critical = critical_exact_match(gold, evaluated_predictions)
    latency = latency_summary_ms(latencies_ms)

    cases = [
        case
        for example, prediction in zip(examples, raw_predictions)
        if (
            case := build_error_case(
                example,
                prediction,
                source_records.get(example["base_address_id"]),
            )
        )
        is not None
    ]
    category_exposures: dict[str, list[str]] = {
        category: [] for category in ERROR_CATEGORIES
    }
    for example, prediction in zip(examples, evaluated_predictions):
        categories = classify_error_categories(
            example["tokens"],
            example["labels"],
            prediction,
            source_records.get(example["base_address_id"]),
        )
        for category in categories:
            category_exposures[category].append(
                f"RD-{example['base_address_id']}"
            )
    prediction_document = {
        "schema_version": "1.0.0",
        "split": "real_dev",
        "dataset_canonical_json_sha256": canonical_json_sha256(payload),
        "model_sha256": sha256_file(model_file),
        "decoder": "orphan_i_to_b_v1",
        "examples": [
            {
                "base_address_id": example["base_address_id"],
                "raw_predicted_labels": raw,
                "evaluated_predicted_labels": evaluated,
                "bio_repairs": repair_orphan_i_tags(raw)[1],
            }
            for example, raw, evaluated in zip(
                examples, raw_predictions, evaluated_predictions
            )
        ],
    }
    metrics = {
        "schema_version": "1.0.0",
        "split": "real_dev",
        "example_count": len(examples),
        "system": {
            "checkpoint": args.checkpoint_name,
            "model_sha256": sha256_file(model_file),
            "decoder": "orphan_i_to_b_v1",
        },
        "overall": metric_record(overall),
        "by_type": {entity: metric_record(result) for entity, result in by_type.items()},
        "critical_exact_match": metric_record(critical),
        "raw_invalid_bio": {
            "example_count": sum(bool(repair_orphan_i_tags(raw)[1]) for raw in raw_predictions),
            "repair_count": sum(len(repair_orphan_i_tags(raw)[1]) for raw in raw_predictions),
        },
        "error_example_count": len(cases),
        "latency_note": "Diagnostic batched CPU model-forward timing; not the ALM-034 production latency benchmark.",
        "diagnostic_latency_ms": metric_record(latency),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    boundary = json.loads(
        (args.dataset.parent / "sealed-test-boundary-manifest.json").read_text(encoding="utf-8")
    )
    matrix = {
        "schema_version": "1.0.0",
        "split": "real_dev",
        "case_count": len(cases),
        "matrix": build_error_matrix(cases, category_exposures),
        "information_boundary": {
            "sealed_test_opened": False,
            "sealed_split_id": boundary["split_version"],
            "sealed_example_count": boundary["example_count"],
            "sealed_content_sha256": boundary["content_sha256"],
            "evidence_source": "sealed-test-boundary-manifest.json only",
        },
    }

    write_json(args.output_dir / "predictions.json", prediction_document)
    write_json(args.output_dir / "metrics.json", metrics)
    write_json(args.output_dir / "error_cases.json", {"cases": cases})
    write_json(args.output_dir / "error_matrix.json", matrix)
    write_json(args.output_dir / "action_register.json", build_action_register(cases))
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

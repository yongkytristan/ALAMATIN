#!/usr/bin/env python3
"""Fine-tune the ALM-020 targeted candidate from the private NER v1 release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_config(path: Path) -> dict[str, Any]:
    config = read_json(path)
    required = {
        "base_model", "parent_checkpoint", "dataset", "output_dir", "seed",
        "selection_policy", "traceability", "training",
    }
    missing = required - config.keys()
    if missing:
        raise ValueError(f"candidate config missing fields: {sorted(missing)}")
    if config["traceability"].get("training_uses_real_dev") is not False:
        raise ValueError("candidate training must explicitly exclude real_dev")
    if config["traceability"].get("checkpoint_selection_split") != "synthetic_dev":
        raise ValueError("checkpoint selection must use synthetic_dev")
    if not config["selection_policy"].get("frozen_before_candidate_run"):
        raise ValueError("candidate selection policy must be frozen before training")
    return config


def load_examples(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = read_json(path)
    examples = document.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError(f"dataset has no examples: {path}")
    for index, example in enumerate(examples):
        if len(example.get("tokens", ())) != len(example.get("labels", ())):
            raise ValueError(f"token/label length mismatch in {path} example {index}")
    return document, examples


def metric_record(result: Any) -> dict[str, float]:
    return {key: float(value) for key, value in result.items() if isinstance(value, (int, float))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "ner-final-candidate.json"
    )
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    config = load_config(config_path)

    # Heavy dependencies stay runtime-only so CI can validate the runner and
    # selection policy without downloading the model stack.
    import numpy as np
    import torch
    from datasets import Dataset
    from seqeval.metrics import accuracy_score, f1_score, precision_score, recall_score
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    from alamatin.label_schema import BIO_LABELS, ID_TO_LABEL, LABEL_TO_ID
    from alamatin.token_alignment import tokenize_and_align

    seed = int(config["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    set_seed(seed)

    parent = (ROOT / config["parent_checkpoint"]["artifact_path"]).resolve()
    parent_model = parent / "model.safetensors"
    expected_parent_hash = config["parent_checkpoint"]["model_sha256"]
    actual_parent_hash = sha256_file(parent_model)
    if actual_parent_hash != expected_parent_hash:
        raise ValueError("parent checkpoint checksum differs from frozen config")

    train_paths = [(ROOT / value).resolve() for value in config["dataset"]["train"]]
    dev_path = (ROOT / config["dataset"]["dev"]).resolve()
    train_documents = [load_examples(path) for path in train_paths]
    dev_document, dev_examples = load_examples(dev_path)
    train_examples = [
        example for _, examples in train_documents for example in examples
    ]
    for document, _ in (*train_documents, (dev_document, dev_examples)):
        label_order = document.get("label_order")
        if label_order is not None and tuple(label_order) != BIO_LABELS:
            raise ValueError("dataset label order differs from canonical schema")

    tokenizer = AutoTokenizer.from_pretrained(parent, use_fast=True)
    if not tokenizer.is_fast:
        raise ValueError("fast tokenizer is required")
    max_length = int(config.get("max_length", 512))

    def preprocess(example: dict[str, Any]) -> dict[str, Any]:
        return tokenize_and_align(example, tokenizer=tokenizer, max_length=max_length)

    tokenized_train = Dataset.from_list(train_examples).map(preprocess)
    tokenized_dev = Dataset.from_list(dev_examples).map(preprocess)

    def compute_metrics(eval_predictions: tuple[Any, Any]) -> dict[str, float]:
        logits, label_ids = eval_predictions
        prediction_ids = np.argmax(logits, axis=-1)
        gold_sequences: list[list[str]] = []
        predicted_sequences: list[list[str]] = []
        for predictions, labels in zip(prediction_ids, label_ids):
            gold: list[str] = []
            predicted: list[str] = []
            for prediction_id, label_id in zip(predictions, labels):
                if int(label_id) == -100:
                    continue
                gold.append(ID_TO_LABEL[int(label_id)])
                predicted.append(ID_TO_LABEL[int(prediction_id)])
            gold_sequences.append(gold)
            predicted_sequences.append(predicted)
        return {
            "accuracy": float(accuracy_score(gold_sequences, predicted_sequences)),
            "precision": float(precision_score(gold_sequences, predicted_sequences)),
            "recall": float(recall_score(gold_sequences, predicted_sequences)),
            "f1": float(f1_score(gold_sequences, predicted_sequences)),
        }

    model = AutoModelForTokenClassification.from_pretrained(parent)
    output_root = (ROOT / config["output_dir"]).resolve()
    checkpoint_dir = output_root / "checkpoints"
    settings = config["training"]
    training_args = TrainingArguments(
        output_dir=str(checkpoint_dir),
        eval_strategy=settings["eval_strategy"],
        save_strategy=settings["save_strategy"],
        learning_rate=float(settings["learning_rate"]),
        per_device_train_batch_size=int(settings["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(settings["per_device_eval_batch_size"]),
        num_train_epochs=float(settings["num_train_epochs"]),
        weight_decay=float(settings["weight_decay"]),
        logging_steps=int(settings["logging_steps"]),
        report_to=settings["report_to"],
        seed=seed,
        data_seed=seed,
        load_best_model_at_end=bool(settings["load_best_model_at_end"]),
        metric_for_best_model=settings["metric_for_best_model"],
        greater_is_better=bool(settings["greater_is_better"]),
        save_total_limit=int(settings["save_total_limit"]),
        save_only_model=True,
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_dev,
        data_collator=DataCollatorForTokenClassification(
            tokenizer=tokenizer, label_pad_token_id=-100
        ),
        compute_metrics=compute_metrics,
    )
    train_result = trainer.train()
    dev_metrics = trainer.evaluate(tokenized_dev, metric_key_prefix="dev")

    inference_dir = output_root / "inference"
    trainer.save_model(str(inference_dir))
    tokenizer.save_pretrained(str(inference_dir))
    model_files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(inference_dir.iterdir())
        if path.is_file()
    }
    package_versions = {
        package: importlib.metadata.version(package)
        for package in ("accelerate", "datasets", "numpy", "seqeval", "torch", "transformers")
    }
    history = [
        {
            key: value
            for key, value in row.items()
            if key in {"epoch", "eval_loss", "eval_accuracy", "eval_precision", "eval_recall", "eval_f1"}
        }
        for row in trainer.state.log_history
        if "eval_f1" in row
    ]
    metrics = {
        "schema_version": "1.0.0",
        "selection": {
            "split": "synthetic_dev",
            "metric": "eval_f1",
            "selected_checkpoint": Path(trainer.state.best_model_checkpoint).name,
            "selected_epoch": next(
                row["epoch"]
                for row in history
                if row["eval_f1"] == trainer.state.best_metric
            ),
            "value": trainer.state.best_metric,
        },
        "train": metric_record(train_result.metrics),
        "dev": metric_record(dev_metrics),
        "dev_history": history,
    }
    manifest = {
        "schema_version": "1.0.0",
        "run_id": config["run_id"],
        "base_model": config["base_model"],
        "parent_checkpoint": {
            **config["parent_checkpoint"],
            "verified_model_sha256": actual_parent_hash,
        },
        "seed": seed,
        "config": {
            "path": str(config_path.relative_to(ROOT)).replace("\\", "/"),
            "canonical_json_sha256": canonical_json_sha256(config),
        },
        "datasets": {
            "train": [
                {
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "example_count": len(examples),
                    "canonical_json_sha256": canonical_json_sha256(document),
                }
                for path, (document, examples) in zip(train_paths, train_documents)
            ],
            "dev": {
                "path": str(dev_path.relative_to(ROOT)).replace("\\", "/"),
                "example_count": len(dev_examples),
                "canonical_json_sha256": canonical_json_sha256(dev_document),
            },
            "real_dev_used_for_training": False,
            "sealed_test_accessed": False,
        },
        "traceability": config["traceability"],
        "selection_policy": config["selection_policy"],
        "packages": package_versions,
        "artifact_files": model_files,
    }
    write_json(output_root / "metrics.json", metrics)
    write_json(output_root / "run_manifest.json", manifest)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

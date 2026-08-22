"""Reproduce the ALAMATIN mBERT NER v1 training run."""

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


def canonical_json_sha256(path: Path) -> str:
    """Hash JSON content independently of indentation and line endings."""
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    required = {"base_model", "dataset", "output_dir", "seed", "training"}
    missing = sorted(required - document.keys())
    if missing:
        raise ValueError(f"training config missing fields: {missing}")
    model = document["base_model"]
    if not model.get("name") or not model.get("revision"):
        raise ValueError("base_model name and immutable revision are required")
    training = document["training"]
    if not training.get("load_best_model_at_end"):
        raise ValueError("load_best_model_at_end must be enabled")
    if training.get("metric_for_best_model") != "f1":
        raise ValueError("the dev checkpoint selection metric must be f1")
    lora = document.get("lora")
    if lora is not None:
        required_lora = {"r", "alpha", "dropout", "target_modules", "bias"}
        missing_lora = sorted(required_lora - lora.keys())
        if missing_lora:
            raise ValueError(f"LoRA config missing fields: {missing_lora}")
        if not lora["target_modules"]:
            raise ValueError("LoRA target_modules cannot be empty")
    return document


def read_dataset(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document.get("examples"), list) or not document["examples"]:
        raise ValueError(f"dataset has no examples: {path}")
    return document


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "ner-v1.json",
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Skip the synthetic test split; dev selection is always evaluated.",
    )
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = load_config(config_path)

    # Runtime imports stay inside main so repository policy tests remain
    # standard-library-only.
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

    dataset_paths = {
        name: (ROOT / relative).resolve()
        for name, relative in config["dataset"].items()
    }
    documents = {name: read_dataset(path) for name, path in dataset_paths.items()}
    for name, document in documents.items():
        if tuple(document.get("label_order", ())) != BIO_LABELS:
            raise ValueError(f"{name} label_order differs from canonical schema")

    model_name = config["base_model"]["name"]
    model_revision = config["base_model"]["revision"]
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        revision=model_revision,
        use_fast=True,
    )
    if not tokenizer.is_fast:
        raise RuntimeError("a fast tokenizer is required for word_ids alignment")

    max_length = int(config.get("max_length", 512))

    def preprocess(example: dict[str, Any]) -> dict[str, Any]:
        return tokenize_and_align(
            example,
            tokenizer=tokenizer,
            max_length=max_length,
        )

    tokenized = {
        name: Dataset.from_list(document["examples"]).map(preprocess)
        for name, document in documents.items()
    }

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

    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        revision=model_revision,
        num_labels=len(BIO_LABELS),
        id2label=ID_TO_LABEL,
        label2id=LABEL_TO_ID,
    )
    trainable_parameters: dict[str, int] | None = None
    if config.get("lora") is not None:
        from peft import LoraConfig, TaskType, get_peft_model

        lora = config["lora"]
        model = get_peft_model(
            model,
            LoraConfig(
                task_type=TaskType.TOKEN_CLS,
                r=int(lora["r"]),
                lora_alpha=int(lora["alpha"]),
                lora_dropout=float(lora["dropout"]),
                target_modules=list(lora["target_modules"]),
                bias=str(lora["bias"]),
            ),
        )
        trainable, total = model.get_nb_trainable_parameters()
        trainable_parameters = {
            "trainable": int(trainable),
            "total": int(total),
        }
        model.print_trainable_parameters()
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
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["dev"],
        data_collator=DataCollatorForTokenClassification(
            tokenizer=tokenizer,
            label_pad_token_id=-100,
        ),
        compute_metrics=compute_metrics,
    )
    train_result = trainer.train()
    dev_metrics = trainer.evaluate(tokenized["dev"], metric_key_prefix="dev")
    test_metrics = (
        {}
        if args.skip_test
        else trainer.evaluate(tokenized["test"], metric_key_prefix="test")
    )

    inference_dir = output_root / "inference"
    trainer.save_model(str(inference_dir))
    tokenizer.save_pretrained(str(inference_dir))

    metrics = {
        "train": train_result.metrics,
        "dev": dev_metrics,
        "test": test_metrics,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "best_metric": trainer.state.best_metric,
        "trainable_parameters": trainable_parameters,
    }
    write_json(output_root / "metrics.json", metrics)
    write_json(
        output_root / "label_map.json",
        {
            "label2id": LABEL_TO_ID,
            "id2label": {str(key): value for key, value in ID_TO_LABEL.items()},
        },
    )
    packages = [
        "accelerate",
        "datasets",
        "numpy",
        "seqeval",
        "torch",
        "transformers",
    ]
    if config.get("lora") is not None:
        packages.append("peft")
    package_versions = {
        package: importlib.metadata.version(package)
        for package in packages
    }
    artifact_files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(inference_dir.iterdir())
        if path.is_file()
    }
    write_json(
        output_root / "run_manifest.json",
        {
            "schema_version": "1.0.0",
            "run_id": config["run_id"],
            "config": {
                "path": str(config_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(config_path),
            },
            "base_model": config["base_model"],
            "lora": config.get("lora"),
            "seed": seed,
            "datasets": {
                name: {
                    "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "canonical_json_sha256": canonical_json_sha256(path),
                }
                for name, path in dataset_paths.items()
            },
            "packages": package_versions,
            "artifact_files": artifact_files,
            "metrics_path": "metrics.json",
            "label_map_path": "label_map.json",
        },
    )
    print(f"Best dev checkpoint: {trainer.state.best_model_checkpoint}")
    print(f"Inference artifact: {inference_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify an ALAMATIN NER v1 inference artifact and run a smoke prediction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections.abc import Sequence


ENTITY_TYPES: tuple[str, ...] = (
    "JALAN", "NOMOR", "RT", "RW", "KELURAHAN", "KECAMATAN",
    "KOTA_KABUPATEN", "PROVINSI", "KODEPOS", "DETAIL_LOKASI",
)
BIO_LABELS: tuple[str, ...] = (
    "O",
    *(label for entity in ENTITY_TYPES for label in (f"B-{entity}", f"I-{entity}")),
)


def predictions_to_word_labels(
    predicted_ids: Sequence[int],
    word_ids: Sequence[int | None],
    *,
    word_count: int,
    id_to_label: dict[int, str],
) -> list[str]:
    """Project first-subword predictions without repository-local imports."""

    if len(predicted_ids) != len(word_ids):
        raise ValueError("prediction and word-id counts differ")
    predictions: list[str | None] = [None] * word_count
    for prediction_id, word_id in zip(predicted_ids, word_ids):
        if word_id is None or predictions[word_id] is not None:
            continue
        predictions[word_id] = id_to_label[prediction_id]
    if any(label is None for label in predictions):
        raise ValueError("not every original word received a prediction")
    return [label for label in predictions if label is not None]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument(
        "--text",
        default=(
            "Jl. Braga No. 99 RT 01 RW 02 Kelurahan Braga Kecamatan "
            "Sumur Bandung Kota Bandung Jawa Barat 40111 dekat alun-alun"
        ),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help=(
            "Optional governed dataset used to prove prediction coverage for "
            "all 10 canonical entity types."
        ),
    )
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    artifact = args.artifact.resolve()
    tokenizer = AutoTokenizer.from_pretrained(artifact)
    model = AutoModelForTokenClassification.from_pretrained(artifact)
    configured_labels = tuple(model.config.id2label[index] for index in range(model.config.num_labels))
    if configured_labels != BIO_LABELS:
        raise ValueError("artifact label map differs from the canonical 10-entity schema")

    encoding = tokenizer(args.text, return_tensors="pt")
    model.eval()
    with torch.no_grad():
        prediction_ids = model(**encoding).logits.argmax(dim=-1)[0].tolist()
    tokens = tokenizer.convert_ids_to_tokens(encoding["input_ids"][0])
    predictions = [model.config.id2label[index] for index in prediction_ids]
    result = {
        "entity_types": list(ENTITY_TYPES),
        "input": args.text,
        "tokens": tokens,
        "predicted_labels": predictions,
    }

    if args.dataset:
        document = json.loads(args.dataset.read_text(encoding="utf-8"))
        examples = document.get("examples", [])
        if not examples:
            raise ValueError("coverage dataset has no examples")

        # Select at most one candidate per entity from gold, then prove that
        # the checkpoint itself emits every entity type on those candidates.
        candidate_indices: list[int] = []
        for entity in ENTITY_TYPES:
            index = next(
                (
                    position
                    for position, example in enumerate(examples)
                    if f"B-{entity}" in example["labels"]
                ),
                None,
            )
            if index is None:
                raise ValueError(f"coverage dataset has no gold {entity} example")
            if index not in candidate_indices:
                candidate_indices.append(index)

        coverage: dict[str, int] = {}
        for index in candidate_indices:
            example = examples[index]
            word_encoding = tokenizer(
                example["tokens"],
                is_split_into_words=True,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            word_ids = word_encoding.word_ids()
            with torch.no_grad():
                word_prediction_ids = (
                    model(**word_encoding).logits.argmax(dim=-1)[0].tolist()
                )
            word_predictions = predictions_to_word_labels(
                word_prediction_ids,
                word_ids,
                word_count=len(example["tokens"]),
                id_to_label=model.config.id2label,
            )
            predicted_entities = {
                label.split("-", maxsplit=1)[1]
                for label in word_predictions
                if label != "O"
            }
            for entity in predicted_entities:
                coverage.setdefault(entity, index)

        missing = sorted(set(ENTITY_TYPES) - coverage.keys())
        if missing:
            raise ValueError(f"checkpoint did not emit entity types: {missing}")
        result["entity_coverage"] = {
            entity: {"example_index": coverage[entity]}
            for entity in ENTITY_TYPES
        }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

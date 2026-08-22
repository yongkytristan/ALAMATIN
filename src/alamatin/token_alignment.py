"""Token-to-subword label alignment for transformer NER models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .label_schema import ID_TO_LABEL, LABEL_TO_ID


IGNORE_INDEX = -100


def align_word_labels(
    word_ids: Sequence[int | None],
    word_labels: Sequence[str],
) -> list[int]:
    """Label only the first subword of every original input token.

    Special tokens, padding, and continuation subwords receive ``-100`` so
    Hugging Face loss functions and metric code ignore them.
    """

    aligned: list[int] = []
    seen_word_ids: set[int] = set()

    for word_id in word_ids:
        if word_id is None:
            aligned.append(IGNORE_INDEX)
            continue

        if not 0 <= word_id < len(word_labels):
            raise ValueError(
                f"word_id {word_id} is outside label sequence "
                f"of length {len(word_labels)}"
            )

        if word_id in seen_word_ids:
            aligned.append(IGNORE_INDEX)
            continue

        label = word_labels[word_id]
        if label not in LABEL_TO_ID:
            raise ValueError(f"unknown BIO label: {label}")

        aligned.append(LABEL_TO_ID[label])
        seen_word_ids.add(word_id)

    return aligned


def tokenize_and_align(
    example: dict[str, Any],
    *,
    tokenizer: Any,
    max_length: int = 512,
) -> dict[str, Any]:
    """Tokenize pre-split words and attach first-subword training labels."""

    tokens = example["tokens"]
    labels = example["labels"]

    if len(tokens) != len(labels):
        raise ValueError("token and label counts differ")
    if any(not isinstance(token, str) or not token.strip() for token in tokens):
        raise ValueError("empty or whitespace-only tokens are not supported")

    encoding = tokenizer(
        tokens,
        is_split_into_words=True,
        truncation=True,
        max_length=max_length,
    )
    encoding["labels"] = align_word_labels(encoding.word_ids(), labels)
    return encoding


def predictions_to_word_labels(
    predicted_ids: Sequence[int],
    word_ids: Sequence[int | None],
    *,
    word_count: int,
) -> list[str]:
    """Project first-subword predictions back to original input tokens."""

    if len(predicted_ids) != len(word_ids):
        raise ValueError("prediction and word-id counts differ")
    if word_count < 0:
        raise ValueError("word_count must be non-negative")

    word_predictions: list[str | None] = [None] * word_count

    for prediction_id, word_id in zip(predicted_ids, word_ids):
        if word_id is None:
            continue
        if not 0 <= word_id < word_count:
            raise ValueError(f"word_id out of range: {word_id}")
        if word_predictions[word_id] is not None:
            continue
        if prediction_id not in ID_TO_LABEL:
            raise ValueError(f"unknown prediction ID: {prediction_id}")

        word_predictions[word_id] = ID_TO_LABEL[prediction_id]

    if any(label is None for label in word_predictions):
        raise ValueError(
            "not every original word received a prediction; "
            "the input may have been truncated"
        )

    return [label for label in word_predictions if label is not None]

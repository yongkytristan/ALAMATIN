"""Reference metric definitions for the ALAMATIN evaluation protocol."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from .label_schema import ENTITY_TYPES, validate_bio_sequence


EntitySpan = tuple[str, int, int]

CRITICAL_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "JALAN",
        "NOMOR",
        "KELURAHAN",
        "KECAMATAN",
        "KOTA_KABUPATEN",
        "PROVINSI",
        "KODEPOS",
    }
)


@dataclass(frozen=True)
class EntityMetricResult:
    """Exact-span entity counts and derived metrics."""

    true_positive: int
    false_positive: int
    false_negative: int
    precision: float | None
    recall: float | None
    f1: float | None


@dataclass(frozen=True)
class RecallResult:
    """Counts for a binary recall metric at address-example level."""

    true_positive: int
    false_negative: int
    recall: float | None


@dataclass(frozen=True)
class RateResult:
    """Numerator, denominator, and rate for a bounded event."""

    numerator: int
    denominator: int
    rate: float | None


@dataclass(frozen=True)
class LatencySummary:
    """Nearest-rank latency percentiles in milliseconds."""

    sample_count: int
    p50_ms: float
    p95_ms: float


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _entity_result(tp: int, fp: int, fn: int) -> EntityMetricResult:
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return EntityMetricResult(tp, fp, fn, precision, recall, f1)


def extract_bio_entities(labels: Sequence[str]) -> frozenset[EntitySpan]:
    """Convert a valid BIO sequence to ``(type, start, end_exclusive)`` spans."""

    valid, reason = validate_bio_sequence(labels)
    if not valid:
        raise ValueError(reason)

    spans: set[EntitySpan] = set()
    current_type: str | None = None
    start = 0

    for index, label in enumerate((*labels, "O")):
        if label == "O":
            prefix = "O"
            entity_type = None
        else:
            prefix, entity_type = label.split("-", maxsplit=1)

        if current_type is not None and (prefix != "I" or entity_type != current_type):
            spans.add((current_type, start, index))
            current_type = None

        if prefix == "B":
            current_type = entity_type
            start = index

    return frozenset(spans)


def _paired_entities(
    gold_sequences: Sequence[Sequence[str]],
    predicted_sequences: Sequence[Sequence[str]],
) -> list[tuple[frozenset[EntitySpan], frozenset[EntitySpan]]]:
    if len(gold_sequences) != len(predicted_sequences):
        raise ValueError("gold and prediction example counts differ")

    pairs = []
    for index, (gold, predicted) in enumerate(zip(gold_sequences, predicted_sequences)):
        if len(gold) != len(predicted):
            raise ValueError(f"token count differs for example {index}")
        pairs.append((extract_bio_entities(gold), extract_bio_entities(predicted)))
    return pairs


def entity_metrics(
    gold_sequences: Sequence[Sequence[str]],
    predicted_sequences: Sequence[Sequence[str]],
) -> EntityMetricResult:
    """Compute micro exact-span precision, recall, and F1."""

    tp = fp = fn = 0
    for gold, predicted in _paired_entities(gold_sequences, predicted_sequences):
        tp += len(gold & predicted)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
    return _entity_result(tp, fp, fn)


def entity_metrics_by_type(
    gold_sequences: Sequence[Sequence[str]],
    predicted_sequences: Sequence[Sequence[str]],
) -> dict[str, EntityMetricResult]:
    """Compute exact-span metrics independently for every canonical type."""

    pairs = _paired_entities(gold_sequences, predicted_sequences)
    results: dict[str, EntityMetricResult] = {}
    for entity_type in ENTITY_TYPES:
        tp = fp = fn = 0
        for gold, predicted in pairs:
            gold_type = {span for span in gold if span[0] == entity_type}
            predicted_type = {span for span in predicted if span[0] == entity_type}
            tp += len(gold_type & predicted_type)
            fp += len(predicted_type - gold_type)
            fn += len(gold_type - predicted_type)
        results[entity_type] = _entity_result(tp, fp, fn)
    return results


def critical_exact_match(
    gold_sequences: Sequence[Sequence[str]],
    predicted_sequences: Sequence[Sequence[str]],
    critical_types: frozenset[str] = CRITICAL_ENTITY_TYPES,
) -> RateResult:
    """Return the address-level exact match rate for critical entity spans."""

    unknown = critical_types - set(ENTITY_TYPES)
    if unknown:
        raise ValueError(f"unknown critical entity types: {sorted(unknown)}")

    correct = 0
    pairs = _paired_entities(gold_sequences, predicted_sequences)
    for gold, predicted in pairs:
        gold_critical = {span for span in gold if span[0] in critical_types}
        predicted_critical = {span for span in predicted if span[0] in critical_types}
        correct += gold_critical == predicted_critical
    return RateResult(correct, len(pairs), _ratio(correct, len(pairs)))


def binary_recall(
    gold_positive: Sequence[bool], predicted_positive: Sequence[bool]
) -> RecallResult:
    """Compute address-level recall for conflict or ambiguity detection."""

    if len(gold_positive) != len(predicted_positive):
        raise ValueError("gold and prediction example counts differ")
    true_positive = sum(
        gold and predicted for gold, predicted in zip(gold_positive, predicted_positive)
    )
    false_negative = sum(
        gold and not predicted
        for gold, predicted in zip(gold_positive, predicted_positive)
    )
    return RecallResult(
        true_positive,
        false_negative,
        _ratio(true_positive, true_positive + false_negative),
    )


def false_correction_rate(proposal_is_correct: Sequence[bool]) -> RateResult:
    """Return incorrect proposals divided by all emitted correction proposals."""

    incorrect = sum(not is_correct for is_correct in proposal_is_correct)
    total = len(proposal_is_correct)
    return RateResult(incorrect, total, _ratio(incorrect, total))


def nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    """Return a nearest-rank percentile for non-empty finite observations."""

    if not values:
        raise ValueError("at least one observation is required")
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in (0, 100]")
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("observations must be finite and non-negative")

    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[rank - 1]


def latency_summary_ms(values_ms: Sequence[float]) -> LatencySummary:
    """Summarize per-address CPU latency observations."""

    return LatencySummary(
        len(values_ms),
        nearest_rank_percentile(values_ms, 50),
        nearest_rank_percentile(values_ms, 95),
    )


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON-compatible manifest using canonical serialization settings."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

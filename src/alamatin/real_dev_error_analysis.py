"""Deterministic helpers for ALM-019 real-dev NER error analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
import re
from typing import Any

from .evaluation_metrics import CRITICAL_ENTITY_TYPES, extract_bio_entities
from .label_schema import ENTITY_TYPES, LABEL_TO_ID, validate_bio_sequence


ERROR_CATEGORIES: tuple[str, ...] = (
    "typo",
    "abbreviation",
    "rt_rw",
    "landmark",
    "missing_field",
    "conflict",
    "ambiguous_region",
    "other_surface_form",
)

_ABBREVIATIONS = {
    "jl", "jln", "kp", "kpg", "gg", "no", "ds", "kel", "kec",
    "kecmtn", "kcmtn", "kab", "kb", "kota", "rt", "rw",
}
_LANDMARK_WORDS = {
    "dekat", "sebelah", "depan", "belakang", "samping", "masjid",
    "gereja", "pasar", "sekolah", "kantor", "jembatan", "gang", "gg",
}
_ADMIN_PREFIXES = {
    "KECAMATAN": {"kec", "kecamatan", "kecmtn", "kcmtn"},
    "KOTA_KABUPATEN": {"kab", "kabupaten", "kb", "kota"},
}


def repair_orphan_i_tags(labels: Sequence[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Convert orphan ``I-X`` tags to ``B-X`` and record every repair."""

    repaired: list[str] = []
    changes: list[dict[str, Any]] = []
    previous_prefix = "O"
    previous_entity: str | None = None
    for index, original in enumerate(labels):
        if original not in LABEL_TO_ID:
            raise ValueError(f"unknown label at index {index}: {original}")
        label = original
        if original.startswith("I-"):
            entity = original[2:]
            if not (
                previous_prefix in {"B", "I"} and previous_entity == entity
            ):
                label = f"B-{entity}"
                changes.append({"index": index, "from": original, "to": label})
        repaired.append(label)
        if label == "O":
            previous_prefix = "O"
            previous_entity = None
        else:
            previous_prefix, previous_entity = label.split("-", maxsplit=1)

    valid, reason = validate_bio_sequence(repaired)
    if not valid:
        raise ValueError(f"BIO repair failed: {reason}")
    return repaired, changes


def spans_as_records(
    tokens: Sequence[str], labels: Sequence[str]
) -> list[dict[str, Any]]:
    """Return exact BIO spans with their original token text."""

    return [
        {
            "entity_type": entity_type,
            "start": start,
            "end": end,
            "text": " ".join(tokens[start:end]),
        }
        for entity_type, start, end in sorted(
            extract_bio_entities(labels), key=lambda span: (span[1], span[2], span[0])
        )
    ]


def _token_key(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.casefold())


def _value_key(value: str, entity_type: str | None = None) -> str:
    words = [_token_key(word) for word in value.split()]
    words = [word for word in words if word]
    if entity_type in _ADMIN_PREFIXES:
        words = [word for word in words if word not in _ADMIN_PREFIXES[entity_type]]
    return "".join(words)


def _entity_values(
    tokens: Sequence[str], labels: Sequence[str], entity_type: str
) -> list[str]:
    return [
        " ".join(tokens[start:end])
        for found_type, start, end in extract_bio_entities(labels)
        if found_type == entity_type
    ]


def classify_error_categories(
    tokens: Sequence[str],
    gold_labels: Sequence[str],
    predicted_labels: Sequence[str],
    source_record: Mapping[str, str] | None = None,
) -> list[str]:
    """Assign transparent, multi-label surface categories to one failed case.

    ``typo`` and ``conflict`` are evidence-based comparisons between gold
    administrative spans and the governed source record. They are deliberately
    conservative; uncertain cases remain ``other_surface_form`` rather than
    being presented as a verified conflict.
    """

    categories: set[str] = set()
    token_keys = {_token_key(token) for token in tokens}
    # Categories are derived only from the input, gold, and governed source.
    # Predictions must not determine their own evaluation slice.
    present_types = {
        entity for entity, _, _ in extract_bio_entities(gold_labels)
    }

    if token_keys & _ABBREVIATIONS:
        categories.add("abbreviation")
    if {"RT", "RW"} & present_types or {"rt", "rw"} & token_keys:
        categories.add("rt_rw")
    if "DETAIL_LOKASI" in present_types or token_keys & _LANDMARK_WORDS:
        categories.add("landmark")

    if source_record:
        expected = {
            "JALAN": source_record.get("reference_address", ""),
            "KECAMATAN": source_record.get("kecamatan", ""),
            "KOTA_KABUPATEN": source_record.get("kabupaten_kota", ""),
        }
        gold_types = {entity for entity, _, _ in extract_bio_entities(gold_labels)}
        if any(value and entity not in gold_types for entity, value in expected.items()):
            categories.add("missing_field")

        for entity_type in ("KECAMATAN", "KOTA_KABUPATEN"):
            observed = _entity_values(tokens, gold_labels, entity_type)
            reference = _value_key(expected[entity_type], entity_type)
            if not observed or not reference:
                continue
            similarities = [
                SequenceMatcher(
                    None,
                    _value_key(value, entity_type),
                    reference,
                ).ratio()
                for value in observed
                if _value_key(value, entity_type)
            ]
            if similarities:
                best = max(similarities)
                if 0.65 <= best < 0.95:
                    categories.add("typo")
                elif best < 0.65:
                    categories.add("conflict")

            distinct = {
                _value_key(value, entity_type)
                for value in observed
                if _value_key(value, entity_type)
            }
            if len(distinct) > 1:
                categories.add("ambiguous_region")

    if not categories:
        categories.add("other_surface_form")
    return [category for category in ERROR_CATEGORIES if category in categories]


def build_error_case(
    example: Mapping[str, Any],
    raw_prediction: Sequence[str],
    source_record: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """Build one traceable error record, or ``None`` for an exact match."""

    tokens = list(example["tokens"])
    gold = list(example["labels"])
    repaired, repairs = repair_orphan_i_tags(raw_prediction)
    if gold == repaired and not repairs:
        return None

    base_id = str(example["base_address_id"])
    components = ["model"] if gold != repaired else []
    if repairs:
        components.append("validator")
    categories = classify_error_categories(tokens, gold, repaired, source_record)
    generator_hypothesis = any(
        category in {"typo", "abbreviation", "rt_rw", "landmark", "missing_field"}
        for category in categories
    )
    if generator_hypothesis:
        components.append("generator")

    gold_critical = {
        span for span in extract_bio_entities(gold) if span[0] in CRITICAL_ENTITY_TYPES
    }
    predicted_critical = {
        span
        for span in extract_bio_entities(repaired)
        if span[0] in CRITICAL_ENTITY_TYPES
    }
    critical_failure = gold_critical != predicted_critical

    return {
        "case_id": f"RD-{base_id}",
        "base_address_id": base_id,
        "annotation_provenance": example.get("annotation_provenance"),
        "tokens": tokens,
        "gold_labels": gold,
        "raw_predicted_labels": list(raw_prediction),
        "evaluated_predicted_labels": repaired,
        "gold_spans": spans_as_records(tokens, gold),
        "predicted_spans": spans_as_records(tokens, repaired),
        "bio_repairs": repairs,
        "categories": categories,
        "components": components,
        "generator_gap_is_hypothesis": generator_hypothesis,
        "critical_exact_match_failed": critical_failure,
        "severity": "P0" if critical_failure else "P1",
    }


def build_error_matrix(
    cases: Sequence[Mapping[str, Any]],
    category_exposures: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Aggregate category/component counts without double-counting cases."""

    category_exposures = category_exposures or {}
    category_rows = {}
    for category in ERROR_CATEGORIES:
        matching = [case for case in cases if category in case["categories"]]
        exposure_ids = list(category_exposures.get(category, ()))
        denominator = len(exposure_ids) if exposure_ids else None
        critical_failures = sum(
            bool(case.get("critical_exact_match_failed")) for case in matching
        )
        if category in {"conflict", "ambiguous_region"} and matching:
            severity = "P0"
        elif critical_failures >= 5:
            severity = "P0"
        elif matching:
            severity = "P1"
        else:
            severity = "not_observed"
        category_rows[category] = {
            "exposure_count": denominator,
            "error_case_count": len(matching),
            "error_rate": len(matching) / denominator if denominator else None,
            "critical_failure_count": critical_failures,
            "severity": severity,
            "case_ids": [case["case_id"] for case in matching],
        }

    component_definitions = {
        "model": "Observed exact-span disagreement after deterministic BIO repair.",
        "generator": "Suspected coverage gap only; requires ALM-020 controlled ablation.",
        "normalizer": "Not observable: this run evaluates NER only and does not execute normalization.",
        "validator": "Observed raw invalid BIO output that required orphan-I repair.",
        "annotation": "No confirmed annotation defect; provenance is retained for review.",
    }
    component_rows = {}
    for component, definition in component_definitions.items():
        matching = [case for case in cases if component in case["components"]]
        component_rows[component] = {
            "case_count": len(matching) if component != "normalizer" else None,
            "case_ids": [case["case_id"] for case in matching],
            "interpretation": definition,
            "evidence_status": (
                "not_observable"
                if component == "normalizer"
                else "hypothesis"
                if component == "generator"
                else "confirmed_absent"
                if component == "annotation"
                else "observed"
            ),
        }
    return {"categories": category_rows, "components": component_rows}


def validate_real_dev_payload(payload: Mapping[str, Any], dataset_path: str) -> None:
    """Enforce the ALM-019 information boundary before inference."""

    lowered = dataset_path.replace("\\", "/").casefold()
    if "sealed" in lowered or payload.get("split") != "real_dev":
        raise ValueError("ALM-019 may evaluate only a payload explicitly marked real_dev")
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("real_dev payload has no examples")
    ids = [example.get("base_address_id") for example in examples]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("real_dev requires unique base_address_id values")

"""Canonical NER label schema shared by annotation, training, and evaluation."""

from __future__ import annotations

from collections.abc import Sequence


SCHEMA_VERSION = "1.0.0"

ENTITY_TYPES: tuple[str, ...] = (
    "JALAN",
    "NOMOR",
    "RT",
    "RW",
    "KELURAHAN",
    "KECAMATAN",
    "KOTA_KABUPATEN",
    "PROVINSI",
    "KODEPOS",
    "DETAIL_LOKASI",
)

BIO_LABELS: tuple[str, ...] = (
    "O",
    *(label for entity in ENTITY_TYPES for label in (f"B-{entity}", f"I-{entity}")),
)

LABEL_TO_ID: dict[str, int] = {label: index for index, label in enumerate(BIO_LABELS)}
ID_TO_LABEL: dict[int, str] = {index: label for label, index in LABEL_TO_ID.items()}


def validate_bio_sequence(labels: Sequence[str]) -> tuple[bool, str | None]:
    """Return whether a label sequence obeys the canonical BIO transitions."""

    previous_prefix = "O"
    previous_entity: str | None = None
    for index, label in enumerate(labels):
        if label not in LABEL_TO_ID:
            return False, f"unknown label at index {index}: {label}"
        if label == "O":
            previous_prefix = "O"
            previous_entity = None
            continue
        prefix, entity = label.split("-", maxsplit=1)
        if prefix == "I" and not (
            previous_prefix in {"B", "I"} and previous_entity == entity
        ):
            return False, f"orphan I-tag at index {index}: {label}"
        previous_prefix = prefix
        previous_entity = entity
    return True, None

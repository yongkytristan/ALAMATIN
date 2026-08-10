"""Core ALAMATIN package."""

from .label_schema import (
    BIO_LABELS,
    ENTITY_TYPES,
    ID_TO_LABEL,
    LABEL_TO_ID,
    SCHEMA_VERSION,
    validate_bio_sequence,
)

__all__ = [
    "BIO_LABELS",
    "ENTITY_TYPES",
    "ID_TO_LABEL",
    "LABEL_TO_ID",
    "SCHEMA_VERSION",
    "validate_bio_sequence",
]

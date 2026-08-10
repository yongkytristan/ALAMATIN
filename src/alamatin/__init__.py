"""Core ALAMATIN package."""

from .evaluation_metrics import (
    CRITICAL_ENTITY_TYPES,
    EntityMetricResult,
    LatencySummary,
    RateResult,
    RecallResult,
    binary_recall,
    canonical_json_sha256,
    critical_exact_match,
    entity_metrics,
    entity_metrics_by_type,
    extract_bio_entities,
    false_correction_rate,
    latency_summary_ms,
    nearest_rank_percentile,
)
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
    "CRITICAL_ENTITY_TYPES",
    "ENTITY_TYPES",
    "EntityMetricResult",
    "ID_TO_LABEL",
    "LABEL_TO_ID",
    "LatencySummary",
    "RateResult",
    "RecallResult",
    "SCHEMA_VERSION",
    "binary_recall",
    "canonical_json_sha256",
    "critical_exact_match",
    "entity_metrics",
    "entity_metrics_by_type",
    "extract_bio_entities",
    "false_correction_rate",
    "latency_summary_ms",
    "nearest_rank_percentile",
    "validate_bio_sequence",
]

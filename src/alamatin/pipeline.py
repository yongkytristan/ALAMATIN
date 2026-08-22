"""End-to-end single-address pipeline: PII, extraction, normalization, validation, gate.

Wires the ALM-021 through ALM-025 components into one auditable pass and emits a
document that satisfies the frozen ALM-025 contract. Every stage records an
audit event, and nothing outside the frozen sources may set a value.

The extractor is injected rather than hardcoded. The fine-tuned NER weights are
a release asset, not a repository file, so the default extractor is the
deterministic rule baseline and ``versions.model`` reports what actually ran.
Passing a model-backed extractor needs no change here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .address_normalizer import (
    NormalizationChange,
    NormalizationResult,
    ValueSource,
    normalize_address,
)
from .administrative_validator import AdministrativeValidator
from .label_schema import ENTITY_TYPES
from .output_contract import CONTRACT_VERSION, validate_contract_document
from .pii import PIIProcessingResult, process_pii
from .quality_gate import RULES_VERSION, evaluate_quality_gate
from .regex_baseline import tag_text


#: Identifier reported as ``versions.model`` for the rule baseline. It is
#: deliberately not a model name: claiming a fine-tuned model that did not run
#: would be an unsupported claim under the frozen scope.
REGEX_EXTRACTOR_VERSION = "regex-baseline-v1"
NORMALIZER_VERSION = "normalizer-v1"

#: A callable that turns PII-safe address text into raw component values.
Extractor = Callable[[str], dict[str, str]]


class PipelineError(RuntimeError):
    """Raised when a stage produces something the contract cannot express."""


def decode_bio(tokens: list[str], labels: list[str]) -> dict[str, str]:
    """Collapse BIO tags into one value per entity type.

    The first span of each type wins. A later span of an already-seen type is
    dropped rather than merged: joining two separate mentions would invent a
    value neither the model nor the user supplied.
    """

    if len(tokens) != len(labels):
        raise PipelineError("tokens and labels must have equal length")

    values: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current and current not in values:
            values[current] = " ".join(buffer)

    for token, label in zip(tokens, labels):
        if label.startswith("B-"):
            flush()
            current, buffer = label[2:], [token]
        elif label.startswith("I-") and current == label[2:]:
            buffer.append(token)
        else:
            flush()
            current, buffer = None, []
    flush()
    return {field: values[field] for field in ENTITY_TYPES if field in values}


def regex_extractor(text: str) -> dict[str, str]:
    """Extract components with the deterministic rule baseline."""

    return decode_bio(*tag_text(text))


def _basic(value: str, source: str, *, confirmed: bool = False) -> dict[str, Any]:
    return {"value": value, "source": source, "confirmed": confirmed}


def _audit_value(field: str, value: str, source: str, confirmed: bool) -> dict[str, Any]:
    return {"field": field, "value": value, "source": source, "confirmed": confirmed}


def _compose_normalized(values: Mapping[str, str]) -> str:
    """Join normalized components into one displayable line."""

    ordered = [values.get(field, "").strip() for field in ENTITY_TYPES]
    return ", ".join(part for part in ordered if part)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """The contract document plus the intermediate results that produced it."""

    document: dict[str, Any]
    pii: PIIProcessingResult
    normalization: NormalizationResult
    status: str


class AddressPipeline:
    """One auditable pass from raw address text to a contract response."""

    def __init__(
        self,
        validator: AdministrativeValidator,
        *,
        extractor: Extractor = regex_extractor,
        model_version: str = REGEX_EXTRACTOR_VERSION,
        normalizer_version: str = NORMALIZER_VERSION,
    ) -> None:
        if not isinstance(validator, AdministrativeValidator):
            raise TypeError("validator must be an AdministrativeValidator")
        if not callable(extractor):
            raise TypeError("extractor must be callable")
        for name, version in (
            ("model_version", model_version),
            ("normalizer_version", normalizer_version),
        ):
            if not isinstance(version, str) or not version.strip():
                raise PipelineError(f"{name} is required")
        self.validator = validator
        self.extractor = extractor
        self.model_version = model_version
        self.normalizer_version = normalizer_version

    # -- stages ---------------------------------------------------------------

    def _corrections(
        self, changes: tuple[NormalizationChange, ...]
    ) -> list[dict[str, Any]]:
        """Expose semantic proposals; deterministic rewrites are not decisions."""

        corrections: list[dict[str, Any]] = []
        for index, change in enumerate(changes, start=1):
            if change.decision == "deterministic":
                continue
            corrections.append(
                {
                    "correction_id": f"corr_{change.field.lower()}_{index:03d}",
                    "field": change.field,
                    "previous_value": _basic(
                        change.before.value,
                        change.before.source.value,
                        confirmed=change.before.confirmed,
                    ),
                    "proposed_value": _basic(
                        change.after.value,
                        change.after.source.value,
                        confirmed=change.after.confirmed,
                    ),
                    "rule_id": change.rule_id,
                    "decision": change.decision,
                    "applied": change.applied,
                    # A proposal is never self-confirmed. Only an explicit user
                    # action may set this, which is what keeps a substantive
                    # change from being applied silently.
                    "user_confirmation": None,
                }
            )
        return corrections

    def _audit_trail(
        self,
        pii: PIIProcessingResult,
        extracted: Mapping[str, str],
        normalization: NormalizationResult,
        validation_status: str,
        validation_reasons: tuple[str, ...],
        gate_status: str,
        gate_reasons: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        def add(stage: str, action: str, rule_id: str | None, previous, resulting) -> None:
            events.append(
                {
                    "sequence": len(events) + 1,
                    "stage": stage,
                    "action": action,
                    "actor": "system",
                    "rule_id": rule_id,
                    "previous_values": previous,
                    "resulting_values": resulting,
                }
            )

        # The PII stage records only reason codes, never the detected values.
        add("pii", ",".join(pii.reason_codes) or "no_pii_detected", None, [], [])
        add(
            "model",
            "extract_components",
            self.model_version,
            [],
            [
                _audit_value(field, value, ValueSource.RULE_EXTRACTED.value, False)
                for field, value in extracted.items()
            ],
        )
        for change in normalization.changes:
            add(
                "normalizer",
                f"{change.decision}:{'applied' if change.applied else 'proposed'}",
                change.rule_id,
                [
                    _audit_value(
                        change.field,
                        change.before.value,
                        change.before.source.value,
                        change.before.confirmed,
                    )
                ],
                [
                    _audit_value(
                        change.field,
                        change.after.value,
                        change.after.source.value,
                        change.after.confirmed,
                    )
                ],
            )
        add(
            "validator",
            f"{validation_status}:{','.join(validation_reasons)}",
            self.validator.reference_version,
            [],
            [],
        )
        add(
            "quality_gate",
            f"{gate_status}:{','.join(gate_reasons) or 'no_issue'}",
            RULES_VERSION,
            [],
            [],
        )
        return events

    # -- entry point ----------------------------------------------------------

    def process(
        self,
        address_text: str,
        *,
        request_id: str,
        geocoding_consent: bool = False,
    ) -> PipelineResult:
        """Run every stage and return a validated contract document."""

        if not isinstance(address_text, str) or not address_text.strip():
            raise PipelineError("address_text is required")

        pii = process_pii(address_text)
        # Everything downstream reads the PII-safe text, never the raw input.
        extracted = self.extractor(pii.address_text)
        unknown = sorted(set(extracted) - set(ENTITY_TYPES))
        if unknown:
            raise PipelineError(f"extractor returned unknown fields: {unknown}")

        normalization = normalize_address(
            extracted, default_source=ValueSource.RULE_EXTRACTED
        )
        values = normalization.values()
        validation = self.validator.validate(values)
        quality = evaluate_quality_gate(
            validation, normalization_changes=normalization.changes
        )

        components = [
            {
                "field": component.field,
                "result": {
                    "value": component.value.value,
                    "source": component.value.source.value,
                    "confirmed": component.value.confirmed,
                    # Left null on purpose: the rule baseline produces no score,
                    # and the contract allows model_score only for values a
                    # model derived.
                    "model_score": None,
                    "previous_value": None,
                },
            }
            for component in normalization.components
        ]

        document: dict[str, Any] = {
            "document_type": "address_parse_response",
            "schema_version": CONTRACT_VERSION,
            "request_id": request_id,
            "versions": {
                "contract": CONTRACT_VERSION,
                "model": self.model_version,
                "normalizer": self.normalizer_version,
                "validator": self.validator.reference_version,
                "reference_data": self.validator.reference_version,
                "quality_gate": RULES_VERSION,
            },
            "pii": {
                "address_text": _basic(
                    pii.address_text, ValueSource.RULE_EXTRACTED.value
                ),
                "redacted_text": _basic(
                    pii.redacted_text, ValueSource.RULE_EXTRACTED.value
                ),
                "entities": [entity.to_dict() for entity in pii.entities],
                "reason_codes": list(pii.reason_codes),
                "warnings": list(pii.warnings),
            },
            "components": components,
            "normalized_address": {
                "value": _compose_normalized(values),
                "source": ValueSource.NORMALIZED_BY_DICTIONARY.value,
                "confirmed": False,
                "model_score": None,
                "previous_value": None,
            },
            "quality_gate": quality.to_response_dict(),
            "corrections": self._corrections(normalization.changes),
            # The parse path never geocodes, so the result is explicitly
            # NOT_REQUESTED rather than a silent external call. "consent" reports
            # whether consent was *exercised* for a geocoding result, so it stays
            # false here even when the request granted it: nothing was looked up.
            # The contract enforces that pairing.
            "geocoding": {
                "status": "NOT_REQUESTED",
                "consent": False,
                "provider": None,
                "precision": None,
                "latitude": None,
                "longitude": None,
                "components": [],
                "error_code": None,
            },
            "audit_trail": self._audit_trail(
                pii,
                extracted,
                normalization,
                validation.status,
                validation.reason_codes,
                quality.status,
                quality.reason_codes,
            ),
        }

        validate_contract_document(document)
        return PipelineResult(
            document=document,
            pii=pii,
            normalization=normalization,
            status=quality.status,
        )


__all__ = [
    "AddressPipeline",
    "Extractor",
    "NORMALIZER_VERSION",
    "PipelineError",
    "PipelineResult",
    "REGEX_EXTRACTOR_VERSION",
    "decode_bio",
    "regex_extractor",
]

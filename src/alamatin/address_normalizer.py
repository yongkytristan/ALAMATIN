"""Auditable, deterministic normalization for structured address components."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

from .label_schema import ENTITY_TYPES


class ValueSource(str, Enum):
    """Allowed provenance sources across the ALAMATIN address pipeline."""

    USER_INPUT = "user_input"
    RULE_EXTRACTED = "rule_extracted"
    EXTRACTED_BY_MODEL = "extracted_by_model"
    NORMALIZED_BY_DICTIONARY = "normalized_by_dictionary"
    INFERRED_FROM_HIERARCHY = "inferred_from_hierarchy"
    RETURNED_BY_GEOCODER = "returned_by_geocoder"
    CONFIRMED_BY_USER = "confirmed_by_user"


ALLOWED_SOURCES: tuple[str, ...] = tuple(source.value for source in ValueSource)


class NormalizationError(ValueError):
    """Raised when a normalization request violates the provenance contract."""


@dataclass(frozen=True)
class ProvenancedValue:
    """One value plus its immediate provenance and confirmation state."""

    value: str
    source: ValueSource
    confirmed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("value must be a string")
        if not isinstance(self.source, ValueSource):
            try:
                object.__setattr__(self, "source", ValueSource(self.source))
            except (TypeError, ValueError) as exc:
                raise NormalizationError(f"unsupported source: {self.source!r}") from exc
        if self.confirmed != (self.source is ValueSource.CONFIRMED_BY_USER):
            raise NormalizationError(
                "confirmed values must have source confirmed_by_user, and vice versa"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "source": self.source.value,
            "confirmed": self.confirmed,
        }


@dataclass(frozen=True)
class NormalizationChange:
    """An immutable before/after audit record for an applied rule or proposal."""

    field: str
    before: ProvenancedValue
    after: ProvenancedValue
    rule_id: str
    decision: str
    applied: bool

    def __post_init__(self) -> None:
        if self.decision not in {"deterministic", "requires_confirmation", "confirmed"}:
            raise NormalizationError(f"unsupported decision: {self.decision!r}")
        if self.decision == "requires_confirmation" and self.applied:
            raise NormalizationError("a suggestion cannot be applied before confirmation")
        if self.decision == "confirmed" and not self.after.confirmed:
            raise NormalizationError("a confirmed change requires confirmed_by_user provenance")

    def to_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "rule_id": self.rule_id,
            "decision": self.decision,
            "applied": self.applied,
        }


@dataclass(frozen=True)
class NormalizedComponent:
    field: str
    value: ProvenancedValue

    def to_dict(self) -> dict[str, object]:
        return {"field": self.field, **self.value.to_dict()}


@dataclass(frozen=True)
class NormalizationResult:
    """Normalized values and the complete ordered audit trail."""

    components: tuple[NormalizedComponent, ...]
    changes: tuple[NormalizationChange, ...]

    def values(self) -> dict[str, str]:
        return {component.field: component.value.value for component in self.components}

    def to_response_dict(self) -> dict[str, object]:
        return {
            "components": [component.to_dict() for component in self.components],
            "changes": [change.to_dict() for change in self.changes],
        }


_DESIGNATOR_PATTERNS: dict[str, tuple[tuple[re.Pattern[str], str], ...]] = {
    "JALAN": (
        (re.compile(r"(?i)^(?:jalan|jln|jl)\.?(?:\s+|$)"), "Jalan "),
        (re.compile(r"(?i)^(?:gang|gg)\.?(?:\s+|$)"), "Gang "),
        (re.compile(r"(?i)^(?:kampung|kp)\.?(?:\s+|$)"), "Kampung "),
    ),
    "NOMOR": ((re.compile(r"(?i)^(?:nomor|no)\.?(?:\s+|$)"), "No. "),),
    "KELURAHAN": (
        (re.compile(r"(?i)^(?:kelurahan|kel)\.?(?:\s+|$)"), "Kelurahan "),
        (re.compile(r"(?i)^(?:desa|ds)\.?(?:\s+|$)"), "Desa "),
    ),
    "KECAMATAN": ((re.compile(r"(?i)^(?:kecamatan|kec)\.?(?:\s+|$)"), "Kecamatan "),),
    "KOTA_KABUPATEN": (
        (re.compile(r"(?i)^(?:kabupaten|kab)\.?(?:\s+|$)"), "Kabupaten "),
        (re.compile(r"(?i)^kota\.?(?:\s+|$)"), "Kota "),
    ),
    "PROVINSI": ((re.compile(r"(?i)^(?:provinsi|prov)\.?(?:\s+|$)"), "Provinsi "),),
}

_TITLE_FIELDS = {
    "JALAN",
    "KELURAHAN",
    "KECAMATAN",
    "KOTA_KABUPATEN",
    "PROVINSI",
    "DETAIL_LOKASI",
}
_LOWERCASE_CONNECTORS = {"dan", "di", "ke", "dari"}
_ROMAN_NUMERAL_RE = re.compile(r"(?i)^[ivxlcdm]+$")


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _normalize_designator(field: str, value: str) -> str:
    for pattern, replacement in _DESIGNATOR_PATTERNS.get(field, ()):
        if pattern.search(value):
            return pattern.sub(replacement, value, count=1).rstrip()
    return value


def _normalize_rt_rw(field: str, value: str) -> str:
    if field not in {"RT", "RW"}:
        return value
    match = re.fullmatch(rf"(?i)(?:{field})?\.?\s*0*(\d{{1,3}})", value)
    if not match:
        return value
    return f"{field} {int(match.group(1)):03d}"


def _normalize_postcode(field: str, value: str) -> str:
    if field != "KODEPOS":
        return value
    match = re.fullmatch(r"(\d{2})\s+(\d{3})", value)
    return "".join(match.groups()) if match else value


def _smart_title(value: str) -> str:
    words: list[str] = []
    for index, word in enumerate(value.split()):
        core = word.strip(".,")
        if _ROMAN_NUMERAL_RE.fullmatch(core):
            replacement = core.upper()
        elif index > 0 and core.casefold() in _LOWERCASE_CONNECTORS:
            replacement = core.casefold()
        elif any(character.isalpha() for character in core):
            replacement = core.title()
        else:
            replacement = core
        words.append(word.replace(core, replacement, 1))
    return " ".join(words)


def _normalize_capitalization(field: str, value: str) -> str:
    return _smart_title(value) if field in _TITLE_FIELDS else value


def _coerce_value(value: str | ProvenancedValue, default_source: ValueSource) -> ProvenancedValue:
    if isinstance(value, ProvenancedValue):
        return value
    if isinstance(value, str):
        return ProvenancedValue(value=value, source=default_source)
    raise TypeError("component values must be strings or ProvenancedValue objects")


def _record_rule(
    field: str,
    current: ProvenancedValue,
    rule_id: str,
    output_source: ValueSource,
    transformed: str,
) -> tuple[ProvenancedValue, NormalizationChange | None]:
    if transformed == current.value:
        return current, None
    after = ProvenancedValue(value=transformed, source=output_source)
    return after, NormalizationChange(
        field=field,
        before=current,
        after=after,
        rule_id=rule_id,
        decision="deterministic",
        applied=True,
    )


def normalize_address(
    components: Mapping[str, str | ProvenancedValue],
    *,
    default_source: ValueSource | str = ValueSource.USER_INPUT,
) -> NormalizationResult:
    """Normalize structured NER components with a complete provenance trail.

    Only representation-preserving rules run here. Semantic corrections belong
    in :func:`propose_correction` and require explicit user confirmation.
    """

    try:
        source = ValueSource(default_source)
    except (TypeError, ValueError) as exc:
        raise NormalizationError(f"unsupported source: {default_source!r}") from exc

    unknown_fields = sorted(set(components) - set(ENTITY_TYPES))
    if unknown_fields:
        raise NormalizationError(f"unknown address fields: {', '.join(unknown_fields)}")

    normalized: list[NormalizedComponent] = []
    changes: list[NormalizationChange] = []
    for field in ENTITY_TYPES:
        if field not in components:
            continue
        current = _coerce_value(components[field], source)
        rules = (
            ("unicode_whitespace_v1", ValueSource.RULE_EXTRACTED, _collapse_whitespace),
            (
                "designator_dictionary_v1",
                ValueSource.NORMALIZED_BY_DICTIONARY,
                lambda value, current_field=field: _normalize_designator(current_field, value),
            ),
            (
                "rt_rw_three_digit_v1",
                ValueSource.RULE_EXTRACTED,
                lambda value, current_field=field: _normalize_rt_rw(current_field, value),
            ),
            (
                "postcode_spacing_v1",
                ValueSource.RULE_EXTRACTED,
                lambda value, current_field=field: _normalize_postcode(current_field, value),
            ),
            (
                "component_capitalization_v1",
                ValueSource.NORMALIZED_BY_DICTIONARY,
                lambda value, current_field=field: _normalize_capitalization(current_field, value),
            ),
        )
        for rule_id, output_source, transform in rules:
            current, change = _record_rule(
                field,
                current,
                rule_id,
                output_source,
                transform(current.value),
            )
            if change:
                changes.append(change)
        normalized.append(NormalizedComponent(field=field, value=current))

    return NormalizationResult(components=tuple(normalized), changes=tuple(changes))


def propose_correction(
    field: str,
    current: ProvenancedValue,
    proposed_value: str,
    *,
    evidence_source: ValueSource | str,
    rule_id: str,
) -> NormalizationChange:
    """Create a non-applied semantic suggestion that requires confirmation."""

    if field not in ENTITY_TYPES:
        raise NormalizationError(f"unknown address field: {field}")
    try:
        source = ValueSource(evidence_source)
    except (TypeError, ValueError) as exc:
        raise NormalizationError(f"unsupported source: {evidence_source!r}") from exc
    if source in {ValueSource.USER_INPUT, ValueSource.CONFIRMED_BY_USER}:
        raise NormalizationError("suggestion evidence must come from a pipeline source")
    if not proposed_value or proposed_value == current.value:
        raise NormalizationError("a suggestion must contain a different non-empty value")

    return NormalizationChange(
        field=field,
        before=current,
        after=ProvenancedValue(value=proposed_value, source=source),
        rule_id=rule_id,
        decision="requires_confirmation",
        applied=False,
    )


def confirm_correction(
    suggestion: NormalizationChange,
    *,
    user_confirmed: bool,
) -> NormalizationChange:
    """Apply a suggestion only after the caller records explicit user action."""

    if suggestion.decision != "requires_confirmation" or suggestion.applied:
        raise NormalizationError("only an unapplied suggestion can be confirmed")
    if not user_confirmed:
        raise NormalizationError("explicit user confirmation is required")
    return NormalizationChange(
        field=suggestion.field,
        before=suggestion.before,
        after=ProvenancedValue(
            value=suggestion.after.value,
            source=ValueSource.CONFIRMED_BY_USER,
            confirmed=True,
        ),
        rule_id=f"confirm:{suggestion.rule_id}",
        decision="confirmed",
        applied=True,
    )


__all__ = [
    "ALLOWED_SOURCES",
    "NormalizationChange",
    "NormalizationError",
    "NormalizationResult",
    "NormalizedComponent",
    "ProvenancedValue",
    "ValueSource",
    "confirm_correction",
    "normalize_address",
    "propose_correction",
]

"""Deterministic operational status, reason codes, and clarification prompts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .address_normalizer import NormalizationChange
from .administrative_validator import (
    ADMINISTRATIVE_CONFLICT as VALIDATOR_ADMINISTRATIVE_CONFLICT,
    ADMINISTRATIVE_FIELDS,
    AMBIGUOUS_CANDIDATES as VALIDATOR_AMBIGUOUS_CANDIDATES,
    MISSING_FIELDS as VALIDATOR_MISSING_FIELDS,
    REFERENCE_COVERAGE_GAP as VALIDATOR_REFERENCE_COVERAGE_GAP,
    VALID_CHAIN,
    AdministrativeValidationResult,
)
from .label_schema import ENTITY_TYPES


SIAP_DIPROSES = "SIAP_DIPROSES"
PERLU_KONFIRMASI = "PERLU_KONFIRMASI"
TIDAK_VALID = "TIDAK_VALID"

QUALITY_STATUSES: tuple[str, ...] = (
    SIAP_DIPROSES,
    PERLU_KONFIRMASI,
    TIDAK_VALID,
)
SEVERITIES: tuple[str, ...] = ("high", "medium")
RULES_VERSION = "quality-gate-v1"

KODEPOS_TIDAK_COCOK = "KODEPOS_TIDAK_COCOK"
KELURAHAN_TIDAK_DITEMUKAN = "KELURAHAN_TIDAK_DITEMUKAN"
ADMINISTRATIVE_CONFLICT = VALIDATOR_ADMINISTRATIVE_CONFLICT
MISSING_ADMINISTRATIVE_FIELDS = VALIDATOR_MISSING_FIELDS
AMBIGUOUS_ADMINISTRATIVE_CANDIDATES = VALIDATOR_AMBIGUOUS_CANDIDATES
CORRECTION_REQUIRES_CONFIRMATION = "CORRECTION_REQUIRES_CONFIRMATION"

QUALITY_REASON_CODES: tuple[str, ...] = (
    KODEPOS_TIDAK_COCOK,
    KELURAHAN_TIDAK_DITEMUKAN,
    ADMINISTRATIVE_CONFLICT,
    MISSING_ADMINISTRATIVE_FIELDS,
    AMBIGUOUS_ADMINISTRATIVE_CANDIDATES,
    CORRECTION_REQUIRES_CONFIRMATION,
)

STATUS_PRECEDENCE: tuple[tuple[str, str], ...] = (
    (TIDAK_VALID, "at least one high-severity issue exists"),
    (PERLU_KONFIRMASI, "at least one medium-severity issue exists"),
    (SIAP_DIPROSES, "no quality issue exists"),
)


class QualityGateError(ValueError):
    """Raised when quality-gate inputs or results violate the frozen rules."""


def _ordered_fields(fields: Iterable[str]) -> tuple[str, ...]:
    unique = set(fields)
    return tuple(field for field in ENTITY_TYPES if field in unique)


def _field_list(fields: tuple[str, ...]) -> str:
    return ", ".join(fields)


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """One unresolved, user-actionable reason for an operational status."""

    reason_code: str
    severity: str
    message: str
    affected_fields: tuple[str, ...]
    clarification_question: str
    source_reason_code: str

    def __post_init__(self) -> None:
        if self.reason_code not in QUALITY_REASON_CODES:
            raise QualityGateError(f"unsupported reason code: {self.reason_code!r}")
        if self.severity not in SEVERITIES:
            raise QualityGateError(f"unsupported severity: {self.severity!r}")
        if not self.message.strip():
            raise QualityGateError("quality issues require a message")
        if not self.affected_fields:
            raise QualityGateError("quality issues require affected fields")
        if set(self.affected_fields) - set(ENTITY_TYPES):
            raise QualityGateError("quality issues contain unknown affected fields")
        if not self.clarification_question.strip().endswith("?"):
            raise QualityGateError(
                "quality issues require a clarification question ending in '?'"
            )
        if not self.source_reason_code.strip():
            raise QualityGateError("quality issues require a source reason code")

    def to_dict(self) -> dict[str, object]:
        return {
            "reason_code": self.reason_code,
            "severity": self.severity,
            "message": self.message,
            "affected_fields": list(self.affected_fields),
            "clarification_question": self.clarification_question,
            "source_reason_code": self.source_reason_code,
        }


def _status_from_issues(issues: tuple[QualityIssue, ...]) -> str:
    if any(issue.severity == "high" for issue in issues):
        return TIDAK_VALID
    if issues:
        return PERLU_KONFIRMASI
    return SIAP_DIPROSES


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    """Operational status whose decision is reconstructible from issues and rules."""

    status: str
    issues: tuple[QualityIssue, ...]
    rules_version: str = RULES_VERSION

    def __post_init__(self) -> None:
        if self.status not in QUALITY_STATUSES:
            raise QualityGateError(f"unsupported quality status: {self.status!r}")
        expected = _status_from_issues(self.issues)
        if self.status != expected:
            raise QualityGateError(
                f"status {self.status!r} is inconsistent with issues; expected {expected!r}"
            )
        if self.rules_version != RULES_VERSION:
            raise QualityGateError(f"unsupported rules version: {self.rules_version!r}")

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(issue.reason_code for issue in self.issues)

    def to_response_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
            "rules": {
                "version": self.rules_version,
                "precedence": [
                    {"status": status, "when": condition}
                    for status, condition in STATUS_PRECEDENCE
                ],
            },
        }


def _administrative_conflict_issues(
    validation: AdministrativeValidationResult,
) -> tuple[QualityIssue, ...]:
    affected = validation.affected_fields
    # Only ADMINISTRATIVE_FIELDS can be contradicted by the governed reference,
    # so only they are reference-supported evidence for TIDAK_VALID. The frozen
    # scope (docs/product-scope.md) keeps JALAN, NOMOR, RT, RW, and
    # DETAIL_LOKASI useful for clarification while forbidding any claim that
    # their absence or form proves an address invalid. Note this is a narrower
    # set than evaluation's CRITICAL_ENTITY_TYPES, which also scores JALAN and
    # NOMOR for extraction quality.
    non_critical = tuple(
        field for field in affected if field not in ADMINISTRATIVE_FIELDS
    )
    if non_critical:
        raise QualityGateError(
            "administrative conflicts cannot affect non-critical fields: "
            f"{_field_list(non_critical)}; the governed reference cannot prove "
            "these fields wrong, so they must not reach TIDAK_VALID"
        )
    issues: list[QualityIssue] = []
    if "KODEPOS" in affected:
        issues.append(
            QualityIssue(
                reason_code=KODEPOS_TIDAK_COCOK,
                severity="high",
                message=(
                    "Kode pos bertentangan dengan rantai wilayah pada referensi "
                    "administratif yang digunakan."
                ),
                affected_fields=("KODEPOS",),
                clarification_question=(
                    "Kode pos mana yang benar untuk kelurahan dan kecamatan tujuan?"
                ),
                source_reason_code=VALIDATOR_ADMINISTRATIVE_CONFLICT,
            )
        )
    other_fields = tuple(field for field in affected if field != "KODEPOS")
    if other_fields:
        fields = _field_list(other_fields)
        issues.append(
            QualityIssue(
                reason_code=ADMINISTRATIVE_CONFLICT,
                severity="high",
                message=f"Komponen administratif berikut saling bertentangan: {fields}.",
                affected_fields=other_fields,
                clarification_question=(
                    f"Mohon periksa {fields}; nilai mana yang sesuai dengan alamat tujuan?"
                ),
                source_reason_code=VALIDATOR_ADMINISTRATIVE_CONFLICT,
            )
        )
    return tuple(issues)


def _issues_from_validation(
    validation: AdministrativeValidationResult,
) -> tuple[QualityIssue, ...]:
    reason_codes = validation.reason_codes
    if reason_codes == (VALID_CHAIN,):
        return ()
    if reason_codes == (VALIDATOR_ADMINISTRATIVE_CONFLICT,):
        return _administrative_conflict_issues(validation)
    if reason_codes == (VALIDATOR_MISSING_FIELDS,):
        affected = _ordered_fields(validation.missing_fields)
        fields = _field_list(affected)
        return (
            QualityIssue(
                reason_code=MISSING_ADMINISTRATIVE_FIELDS,
                severity="medium",
                message=f"Komponen administratif wajib belum lengkap: {fields}.",
                affected_fields=affected,
                clarification_question=(
                    f"Mohon lengkapi {fields} agar rantai wilayah dapat diperiksa?"
                ),
                source_reason_code=VALIDATOR_MISSING_FIELDS,
            ),
        )
    if reason_codes == (VALIDATOR_AMBIGUOUS_CANDIDATES,):
        return (
            QualityIssue(
                reason_code=AMBIGUOUS_ADMINISTRATIVE_CANDIDATES,
                severity="medium",
                message=(
                    "Nama kelurahan cocok dengan lebih dari satu rantai wilayah "
                    "pada referensi."
                ),
                affected_fields=("KELURAHAN", "KECAMATAN", "KOTA_KABUPATEN"),
                clarification_question=(
                    "Kecamatan dan kota/kabupaten mana yang benar untuk kelurahan tujuan?"
                ),
                source_reason_code=VALIDATOR_AMBIGUOUS_CANDIDATES,
            ),
        )
    if reason_codes == (VALIDATOR_REFERENCE_COVERAGE_GAP,):
        return (
            QualityIssue(
                reason_code=KELURAHAN_TIDAK_DITEMUKAN,
                severity="medium",
                message=(
                    "Kelurahan belum ditemukan pada versi referensi saat ini; "
                    "hasil ini tidak membuktikan alamat salah."
                ),
                affected_fields=("KELURAHAN",),
                clarification_question=(
                    "Apakah ejaan kelurahan serta kecamatan dan kota/kabupatennya sudah benar?"
                ),
                source_reason_code=VALIDATOR_REFERENCE_COVERAGE_GAP,
            ),
        )
    raise QualityGateError(
        f"unsupported validator reason-code combination: {reason_codes!r}"
    )


def _issues_from_changes(
    changes: Iterable[NormalizationChange],
) -> tuple[QualityIssue, ...]:
    pending: list[str] = []
    for change in changes:
        if not isinstance(change, NormalizationChange):
            raise TypeError("normalization changes must be NormalizationChange values")
        if change.decision == "requires_confirmation" and not change.applied:
            pending.append(change.field)
    affected = _ordered_fields(pending)
    if not affected:
        return ()
    fields = _field_list(affected)
    return (
        QualityIssue(
            reason_code=CORRECTION_REQUIRES_CONFIRMATION,
            severity="medium",
            message=f"Koreksi semantik belum diterapkan untuk: {fields}.",
            affected_fields=affected,
            clarification_question=(
                f"Apakah koreksi yang disarankan untuk {fields} boleh diterapkan?"
            ),
            source_reason_code=CORRECTION_REQUIRES_CONFIRMATION,
        ),
    )


def evaluate_quality_gate(
    validation: AdministrativeValidationResult,
    *,
    normalization_changes: Iterable[NormalizationChange] = (),
) -> QualityGateResult:
    """Evaluate the frozen precedence without scores or probabilistic thresholds."""

    if not isinstance(validation, AdministrativeValidationResult):
        raise TypeError("validation must be an AdministrativeValidationResult")
    issues = _issues_from_validation(validation) + _issues_from_changes(
        normalization_changes
    )
    return QualityGateResult(status=_status_from_issues(issues), issues=issues)


__all__ = [
    "ADMINISTRATIVE_CONFLICT",
    "AMBIGUOUS_ADMINISTRATIVE_CANDIDATES",
    "CORRECTION_REQUIRES_CONFIRMATION",
    "KELURAHAN_TIDAK_DITEMUKAN",
    "KODEPOS_TIDAK_COCOK",
    "MISSING_ADMINISTRATIVE_FIELDS",
    "PERLU_KONFIRMASI",
    "QUALITY_REASON_CODES",
    "QUALITY_STATUSES",
    "QualityGateError",
    "QualityGateResult",
    "QualityIssue",
    "RULES_VERSION",
    "SEVERITIES",
    "SIAP_DIPROSES",
    "STATUS_PRECEDENCE",
    "TIDAK_VALID",
    "evaluate_quality_gate",
]

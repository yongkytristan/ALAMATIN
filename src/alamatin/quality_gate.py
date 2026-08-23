"""Deterministic operational status, reason codes, and clarification prompts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
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
    within_reference_coverage,
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
MISSING_STREET_LOCATOR = "MISSING_STREET_LOCATOR"
MISSING_HOUSE_LOCATOR = "MISSING_HOUSE_LOCATOR"
OUTSIDE_REFERENCE_COVERAGE = "OUTSIDE_REFERENCE_COVERAGE"

QUALITY_REASON_CODES: tuple[str, ...] = (
    KODEPOS_TIDAK_COCOK,
    KELURAHAN_TIDAK_DITEMUKAN,
    ADMINISTRATIVE_CONFLICT,
    MISSING_ADMINISTRATIVE_FIELDS,
    AMBIGUOUS_ADMINISTRATIVE_CANDIDATES,
    CORRECTION_REQUIRES_CONFIRMATION,
    MISSING_STREET_LOCATOR,
    MISSING_HOUSE_LOCATOR,
    OUTSIDE_REFERENCE_COVERAGE,
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


#: Human field names for messages a seller reads. The machine-readable field
#: identifiers still travel in ``affected_fields``; only the prose changes.
FIELD_LABEL: dict[str, str] = {
    "KELURAHAN": "kelurahan/desa",
    "KECAMATAN": "kecamatan",
    "KOTA_KABUPATEN": "kota/kabupaten",
    "PROVINSI": "provinsi",
    "KODEPOS": "kode pos",
}

#: Which candidate attribute holds the reference's own value for a field, so a
#: message can name what the reference says instead of only which field
#: disagreed. Naming the field alone left a reader with no way to act.
_CANDIDATE_ATTRIBUTE: dict[str, str] = {
    "KELURAHAN": "village_name",
    "KECAMATAN": "district_name",
    "KOTA_KABUPATEN": "city_name",
    "PROVINSI": "province_name",
}

#: Named so a message can cite the reference it speaks for rather than an
#: anonymous "our data".
REFERENCE_SCOPE = "data wilayah Jawa Barat"


def _label(field: str) -> str:
    return FIELD_LABEL.get(field, field)


def _titlecase(value: str) -> str:
    """Present a reference value in running prose, not as a shouted CSV cell."""

    cleaned = " ".join(str(value).split())
    return " ".join(
        part if any(character.islower() for character in part) else part.title()
        for part in cleaned.split(" ")
    )


def _reference_value(
    validation: AdministrativeValidationResult, field: str
) -> str | None:
    """Return what the reference says for one field, when it says anything."""

    attribute = _CANDIDATE_ATTRIBUTE.get(field)
    if attribute is None or len(validation.candidates) != 1:
        return None
    value = getattr(validation.candidates[0], attribute, None)
    return _titlecase(value) if value else None


#: Designators the normalizer prepends. Stripped for display only: a message
#: that said "kecamatan yang tertulis (Kecamatan Coblong)" repeated the field
#: name back at the reader instead of naming the place.
_DISPLAY_PREFIXES: tuple[str, ...] = (
    "kelurahan ", "desa ", "kecamatan ", "kota ", "kabupaten ", "provinsi ",
)


def _submitted_value(submitted: Mapping[str, str] | None, field: str) -> str | None:
    if not submitted:
        return None
    value = submitted.get(field)
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = " ".join(value.split())
    # KOTA_KABUPATEN keeps its prefix: "Bandung" alone is ambiguous between the
    # city and the regency, and dropping it would lose real information.
    if field != "KOTA_KABUPATEN":
        for prefix in _DISPLAY_PREFIXES:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip() or cleaned
                break
    return _titlecase(cleaned)


def _chain_anchor(
    validation: AdministrativeValidationResult, field: str
) -> str | None:
    """Name the village the reference resolved, unless that is the field itself."""

    if field == "KELURAHAN":
        return None
    village = _reference_value(validation, "KELURAHAN")
    return f"Kelurahan/desa {village}" if village else None


def _chain_prefix(validation: AdministrativeValidationResult) -> str | None:
    """Name the anchor the reference resolved, so the claim is checkable."""

    village = _reference_value(validation, "KELURAHAN")
    district = _reference_value(validation, "KECAMATAN")
    if village and district:
        return f"Kelurahan {village}, Kecamatan {district}"
    return f"Kelurahan {village}" if village else None


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


def _conflict_sentence(
    validation: AdministrativeValidationResult,
    submitted: Mapping[str, str] | None,
    field: str,
) -> str:
    """Describe one field's disagreement in terms a seller can act on."""

    expected = _reference_value(validation, field)
    written = _submitted_value(submitted, field)
    label = _label(field)
    anchor = _chain_anchor(validation, field)
    if expected and written and anchor:
        # "kota/kabupaten Kota Bandung" repeats itself, so the label is dropped
        # when the value already carries its own.
        place = (
            expected
            if expected.lower().startswith(("kota ", "kabupaten ", "provinsi "))
            else f"{label.capitalize()} {expected}"
        )
        return (
            f"{anchor} tercatat berada di {place}, "
            f"sedangkan alamat ini menulis {written}"
        )
    if expected and written:
        return (
            f"{label} pada {REFERENCE_SCOPE} adalah {expected}, "
            f"sedangkan alamat ini menulis {written}"
        )
    if expected:
        return f"{label} pada {REFERENCE_SCOPE} tercatat sebagai {expected}"
    if written:
        return (
            f"{label} yang tertulis ({written}) tidak sesuai dengan "
            f"{REFERENCE_SCOPE} untuk rantai wilayah ini"
        )
    return f"{label} tidak sesuai dengan {REFERENCE_SCOPE} untuk rantai wilayah ini"


def _kodepos_message(
    validation: AdministrativeValidationResult,
    submitted: Mapping[str, str] | None,
) -> str:
    written = _submitted_value(submitted, "KODEPOS")
    anchor = _chain_prefix(validation)
    expected = (
        validation.candidates[0].postal_codes
        if len(validation.candidates) == 1
        else ()
    )
    if anchor and expected:
        listed = " atau ".join(expected)
        tail = f" Kode pos yang tertulis: {written}." if written else ""
        return (
            f"Menurut {REFERENCE_SCOPE}, kode pos untuk {anchor} adalah "
            f"{listed}.{tail}"
        )
    if written:
        return (
            f"Kode pos yang tertulis ({written}) tidak sesuai dengan "
            f"{REFERENCE_SCOPE} untuk rantai wilayah pada alamat ini."
        )
    return (
        f"Kode pos tidak sesuai dengan {REFERENCE_SCOPE} untuk rantai wilayah "
        "pada alamat ini."
    )


def _kodepos_question(
    validation: AdministrativeValidationResult,
    submitted: Mapping[str, str] | None,
) -> str:
    written = _submitted_value(submitted, "KODEPOS")
    expected = (
        validation.candidates[0].postal_codes
        if len(validation.candidates) == 1
        else ()
    )
    if written and expected:
        listed = " atau ".join(expected)
        return f"Kode pos mana yang benar untuk alamat tujuan: {listed} atau {written}?"
    return "Kode pos mana yang benar untuk kelurahan dan kecamatan tujuan?"


def _conflict_question(
    validation: AdministrativeValidationResult,
    submitted: Mapping[str, str] | None,
    fields: tuple[str, ...],
) -> str:
    if len(fields) == 1:
        field = fields[0]
        expected = _reference_value(validation, field)
        written = _submitted_value(submitted, field)
        label = _label(field)
        if expected and written:
            return (
                f"{label.capitalize()} mana yang benar untuk alamat tujuan: "
                f"{expected} atau {written}?"
            )
        return f"{label.capitalize()} mana yang benar untuk alamat tujuan?"
    labels = ", ".join(_label(field) for field in fields)
    return f"Mohon periksa {labels}; nilai mana yang sesuai dengan alamat tujuan?"


def _administrative_conflict_issues(
    validation: AdministrativeValidationResult,
    submitted: Mapping[str, str] | None = None,
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
                message=_kodepos_message(validation, submitted),
                affected_fields=("KODEPOS",),
                clarification_question=_kodepos_question(validation, submitted),
                source_reason_code=VALIDATOR_ADMINISTRATIVE_CONFLICT,
            )
        )
    other_fields = tuple(field for field in affected if field != "KODEPOS")
    if other_fields:
        sentences = [
            _conflict_sentence(validation, submitted, field) for field in other_fields
        ]
        issues.append(
            QualityIssue(
                reason_code=ADMINISTRATIVE_CONFLICT,
                severity="high",
                message=(
                    f"Menurut {REFERENCE_SCOPE}, " + "; ".join(sentences) + "."
                ),
                affected_fields=other_fields,
                clarification_question=_conflict_question(
                    validation, submitted, other_fields
                ),
                source_reason_code=VALIDATOR_ADMINISTRATIVE_CONFLICT,
            )
        )
    return tuple(issues)


def _coverage_gap_message(submitted: Mapping[str, str] | None) -> str:
    """State the fact about the reference, not a verdict on the address.

    Naming the value is what makes this actionable: a seller can compare the
    spelling. Calling it unrecognised would say nothing they can use, and
    calling it wrong would be a claim the reference cannot support -- a village
    absent from a 5,957-row Jawa Barat reference is a gap in that reference.
    """

    written = _submitted_value(submitted, "KELURAHAN")
    named = f" ({written})" if written else ""
    return (
        f"Kelurahan/desa yang tertulis{named} tidak sesuai dengan "
        f"{REFERENCE_SCOPE} pada referensi yang digunakan, sehingga rantai "
        "wilayahnya belum dapat diverifikasi. Status ini menandakan alamat "
        "belum terverifikasi, bukan bahwa alamat salah."
    )


def _coverage_gap_question(submitted: Mapping[str, str] | None) -> str:
    written = _submitted_value(submitted, "KELURAHAN")
    if written:
        return (
            f"Apakah {written} sudah tepat ejaannya, dan sudah sesuai dengan "
            "kecamatan serta kota/kabupaten tujuan?"
        )
    return "Apakah ejaan kelurahan serta kecamatan dan kota/kabupatennya sudah benar?"


def _ambiguous_message(validation: AdministrativeValidationResult) -> str:
    chains = [
        f"{_titlecase(candidate.district_name)}, "
        f"{_titlecase(candidate.city_name)}"
        for candidate in validation.candidates[:4]
    ]
    if not chains:
        return (
            f"Nama kelurahan/desa ini cocok dengan lebih dari satu wilayah pada "
            f"{REFERENCE_SCOPE}."
        )
    listed = "; ".join(chains)
    more = (
        f" dan {len(validation.candidates) - 4} wilayah lain"
        if len(validation.candidates) > 4
        else ""
    )
    return (
        f"Nama kelurahan/desa ini ada di lebih dari satu wilayah pada "
        f"{REFERENCE_SCOPE}: {listed}{more}."
    )


def _issues_from_validation(
    validation: AdministrativeValidationResult,
    submitted: Mapping[str, str] | None = None,
) -> tuple[QualityIssue, ...]:
    reason_codes = validation.reason_codes
    if reason_codes == (VALID_CHAIN,):
        return ()
    if reason_codes == (VALIDATOR_ADMINISTRATIVE_CONFLICT,):
        return _administrative_conflict_issues(validation, submitted)
    if reason_codes == (VALIDATOR_MISSING_FIELDS,):
        affected = _ordered_fields(validation.missing_fields)
        labels = ", ".join(_label(field) for field in affected)
        return (
            QualityIssue(
                reason_code=MISSING_ADMINISTRATIVE_FIELDS,
                severity="medium",
                message=(
                    f"Alamat ini belum menyebutkan {labels}, sehingga rantai "
                    f"wilayahnya belum dapat dicocokkan dengan {REFERENCE_SCOPE}."
                ),
                affected_fields=affected,
                clarification_question=(
                    f"Mohon lengkapi {labels} agar rantai wilayah dapat diperiksa?"
                ),
                source_reason_code=VALIDATOR_MISSING_FIELDS,
            ),
        )
    if reason_codes == (VALIDATOR_AMBIGUOUS_CANDIDATES,):
        return (
            QualityIssue(
                reason_code=AMBIGUOUS_ADMINISTRATIVE_CANDIDATES,
                severity="medium",
                message=_ambiguous_message(validation),
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
                message=_coverage_gap_message(submitted),
                affected_fields=("KELURAHAN",),
                clarification_question=_coverage_gap_question(submitted),
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


#: A courier needs a street or a landmark to find a door inside a village. An
#: address that names only the administrative chain is not deliverable, however
#: perfectly that chain validates.
STREET_LOCATOR_FIELDS: tuple[str, ...] = ("JALAN", "DETAIL_LOKASI")

#: A street alone still does not name a door. Any one of these pins the address
#: down within the street: a house number, an RT/RW pair, or a block/landmark
#: detail. RT/RW counts because it is how a kampung address is normally written.
HOUSE_LOCATOR_FIELDS: tuple[str, ...] = ("NOMOR", "RT", "RW", "DETAIL_LOKASI")

#: A block or unit reference pins a door as well as a house number does, and it
#: frequently arrives inside the street value rather than as its own field:
#: docs/label_schema.md assigns "Blok C2" to DETAIL_LOKASI, but the real gold
#: labels fold it into JALAN, and the extractor emits no DETAIL_LOKASI at all.
#: Rather than resolve that annotation disagreement here -- following the schema
#: measurably lowered real_dev entity F1, from 0.9149 to 0.9040 -- the rule reads
#: the block wherever it lands. Recorded in DEC-012 for a later annotation
#: decision.
_BLOCK_PATTERN = re.compile(r"(?i)\b(?:blok|blk|kav|kavling|unit)\.?\s*[a-z0-9]")


def _street_locator_issues(
    submitted: Mapping[str, str] | None,
) -> tuple[QualityIssue, ...]:
    """Flag an address that validates administratively but cannot be delivered.

    Medium, never high. The frozen scope (docs/product-scope.md) forbids
    treating the absence of JALAN as proof an address is invalid, because the
    governed reference cannot check a street name. Asking is allowed; declaring
    is not.

    A house-level locator is checked separately by _house_locator_issues, so a
    street with no door still raises its own issue.
    """

    if submitted is None:
        return ()
    for field in STREET_LOCATOR_FIELDS:
        value = submitted.get(field)
        if isinstance(value, str) and value.strip():
            return ()
    return (
        QualityIssue(
            reason_code=MISSING_STREET_LOCATOR,
            severity="medium",
            message=(
                "Alamat ini belum menyebutkan nama jalan, kampung, atau patokan "
                "lokasi, sehingga kurir tidak memiliki titik antar di dalam "
                "kelurahan/desa tujuan."
            ),
            affected_fields=("JALAN",),
            clarification_question=(
                "Apa nama jalan, kampung, atau patokan lokasi alamat tujuan?"
            ),
            source_reason_code=MISSING_STREET_LOCATOR,
        ),
    )


def _house_locator_issues(
    submitted: Mapping[str, str] | None,
) -> tuple[QualityIssue, ...]:
    """Flag a street with no way to pick a door inside it.

    Named directly by the target user (R01, fulfillment): a package failed
    after three days because the address was "hanya nama perumahan tanpa nomor
    rumah", and the warning they asked for was one line naming the missing part
    -- "misalnya nomor rumah tidak ada".

    RT, RW, and DETAIL_LOKASI satisfy the requirement alongside NOMOR, because
    a kampung address is normally written that way and a courier can work with
    it. Requiring NOMOR alone would flag those.

    Medium, never high, for the same reason as the street rule: the governed
    reference cannot check a house number, so this asks rather than declares.
    """

    if submitted is None:
        return ()
    for field in HOUSE_LOCATOR_FIELDS:
        value = submitted.get(field)
        if isinstance(value, str) and value.strip():
            return ()
    for field in ("JALAN", "DETAIL_LOKASI"):
        value = submitted.get(field)
        if isinstance(value, str) and _BLOCK_PATTERN.search(value):
            return ()
    return (
        QualityIssue(
            reason_code=MISSING_HOUSE_LOCATOR,
            severity="medium",
            message=(
                "Alamat ini menyebut jalan atau kampung, tetapi belum "
                "menyebutkan nomor rumah, RT/RW, atau blok, sehingga kurir "
                "tidak dapat memilih satu rumah di sepanjang jalan tersebut."
            ),
            affected_fields=("NOMOR",),
            clarification_question=(
                "Berapa nomor rumah, RT/RW, atau blok alamat tujuan?"
            ),
            source_reason_code=MISSING_HOUSE_LOCATOR,
        ),
    )


def _outside_coverage_issue(
    submitted: Mapping[str, str] | None,
) -> tuple[QualityIssue, ...]:
    """Replace a conflict verdict when the reference cannot speak at all.

    `jabar-reference-v1` holds Jawa Barat rows only. A Jakarta address was being
    declared TIDAK_VALID because a village called Menteng exists in Bogor: the
    reference "contradicted" an address it has no rows for. That is precisely
    what limitations.md forbids -- a coverage gap presented as proof the address
    is wrong -- and it is the worst version of it, at high severity.

    Medium, and no claim about correctness in either direction.
    """

    if submitted is None:
        return ()
    province = submitted.get("PROVINSI")
    if within_reference_coverage(province if isinstance(province, str) else None):
        return ()
    named = _titlecase(str(province))
    return (
        QualityIssue(
            reason_code=OUTSIDE_REFERENCE_COVERAGE,
            severity="medium",
            message=(
                f"Alamat ini berada di {named}, di luar cakupan data wilayah "
                "Jawa Barat yang digunakan, sehingga rantai wilayahnya belum "
                "dapat diverifikasi. Status ini menandakan alamat belum "
                "terverifikasi, bukan bahwa alamat salah."
            ),
            affected_fields=("PROVINSI",),
            clarification_question=(
                f"Apakah alamat tujuan memang berada di {named}?"
            ),
            source_reason_code=OUTSIDE_REFERENCE_COVERAGE,
        ),
    )


def evaluate_quality_gate(
    validation: AdministrativeValidationResult,
    *,
    normalization_changes: Iterable[NormalizationChange] = (),
    submitted: Mapping[str, str] | None = None,
) -> QualityGateResult:
    """Evaluate the frozen precedence without scores or probabilistic thresholds."""

    if not isinstance(validation, AdministrativeValidationResult):
        raise TypeError("validation must be an AdministrativeValidationResult")
    if submitted is not None and not isinstance(submitted, Mapping):
        raise TypeError("submitted must be a mapping of field to value")
    # `submitted` only enriches prose. It never participates in the status,
    # which stays a function of reason codes and severities alone.
    # Checked first: outside the reference's provinces, its verdict carries no
    # evidence, so the conflict issues it produced are replaced rather than
    # reported alongside a coverage note that would contradict them.
    outside = _outside_coverage_issue(submitted)
    reference_issues = (
        outside if outside else _issues_from_validation(validation, submitted)
    )
    issues = (
        reference_issues
        + _street_locator_issues(submitted)
        + _house_locator_issues(submitted)
        + _issues_from_changes(normalization_changes)
    )
    return QualityGateResult(status=_status_from_issues(issues), issues=issues)


__all__ = [
    "ADMINISTRATIVE_CONFLICT",
    "AMBIGUOUS_ADMINISTRATIVE_CANDIDATES",
    "CORRECTION_REQUIRES_CONFIRMATION",
    "KELURAHAN_TIDAK_DITEMUKAN",
    "KODEPOS_TIDAK_COCOK",
    "MISSING_ADMINISTRATIVE_FIELDS",
    "MISSING_HOUSE_LOCATOR",
    "MISSING_STREET_LOCATOR",
    "OUTSIDE_REFERENCE_COVERAGE",
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
    "HOUSE_LOCATOR_FIELDS",
    "STREET_LOCATOR_FIELDS",
    "TIDAK_VALID",
    "evaluate_quality_gate",
]

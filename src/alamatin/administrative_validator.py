"""Deterministic administrative-chain validation against a governed reference."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .address_normalizer import ProvenancedValue
from .label_schema import ENTITY_TYPES
from .reference_hierarchy import (
    REFERENCE_SCHEMA_VERSION,
    ReferenceHierarchy,
    ReferenceRow,
    normalize_name,
)


ADMINISTRATIVE_FIELDS: tuple[str, ...] = (
    "KELURAHAN",
    "KECAMATAN",
    "KOTA_KABUPATEN",
    "PROVINSI",
    "KODEPOS",
)

VALID_CHAIN = "VALID_ADMINISTRATIVE_CHAIN"
MISSING_FIELDS = "MISSING_ADMINISTRATIVE_FIELDS"
ADMINISTRATIVE_CONFLICT = "ADMINISTRATIVE_CONFLICT"
AMBIGUOUS_CANDIDATES = "AMBIGUOUS_ADMINISTRATIVE_CANDIDATES"
REFERENCE_COVERAGE_GAP = "REFERENCE_COVERAGE_GAP"

VALIDATION_STATUSES: tuple[str, ...] = (
    "valid",
    "incomplete",
    "invalid",
    "ambiguous",
    "not_found",
)


class AdministrativeValidationError(ValueError):
    """Raised for invalid validator inputs or configuration."""


@dataclass(frozen=True, slots=True)
class ValidationCandidate:
    """Stable, safe projection of a matching reference row."""

    record_id: str
    village_code: str
    village_name: str
    district_name: str
    city_name: str
    province_name: str
    postal_codes: tuple[str, ...]

    @classmethod
    def from_row(cls, row: ReferenceRow) -> ValidationCandidate:
        return cls(
            record_id=row.record_id,
            village_code=row.village_code,
            village_name=row.village_name,
            district_name=row.district_name,
            city_name=row.city_name,
            province_name=row.province_name,
            postal_codes=row.postal_codes,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "village_code": self.village_code,
            "village_name": self.village_name,
            "district_name": self.district_name,
            "city_name": self.city_name,
            "province_name": self.province_name,
            "postal_codes": list(self.postal_codes),
        }


@dataclass(frozen=True, slots=True)
class AdministrativeValidationResult:
    """One deterministic validation outcome with evidence needed by the UI."""

    status: str
    reason_codes: tuple[str, ...]
    affected_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    candidates: tuple[ValidationCandidate, ...]
    reference_version: str

    def __post_init__(self) -> None:
        if self.status not in VALIDATION_STATUSES:
            raise AdministrativeValidationError(f"unsupported status: {self.status!r}")
        if self.status == "invalid" and not self.affected_fields:
            raise AdministrativeValidationError("invalid results require affected fields")
        if self.status == "ambiguous" and len(self.candidates) < 2:
            raise AdministrativeValidationError("ambiguous results require multiple candidates")

    @property
    def match(self) -> ValidationCandidate | None:
        """Return a candidate only for a complete valid chain."""

        return self.candidates[0] if self.status == "valid" else None

    @property
    def is_invalid(self) -> bool:
        return self.status == "invalid"

    def to_response_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "affected_fields": list(self.affected_fields),
            "missing_fields": list(self.missing_fields),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "reference_version": self.reference_version,
        }


_PREFIXES: dict[str, dict[str, str]] = {
    "KELURAHAN": {
        "kelurahan": "village",
        "kel": "village",
        "desa": "village",
        "ds": "village",
    },
    "KECAMATAN": {"kecamatan": "district", "kec": "district"},
    "KOTA_KABUPATEN": {
        "kabupaten": "kabupaten",
        "kab": "kabupaten",
        "kota": "kota",
    },
    "PROVINSI": {"provinsi": "province", "prov": "province"},
}


def _surface(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, ProvenancedValue):
        return value.value.strip()
    if isinstance(value, str):
        return value.strip()
    raise TypeError("administrative values must be strings, ProvenancedValue, or None")


def _name_parts(field: str, value: str) -> tuple[str | None, str]:
    tokens = normalize_name(value).split()
    if not tokens:
        return None, ""
    kind = _PREFIXES.get(field, {}).get(tokens[0])
    if kind:
        tokens = tokens[1:]
    return kind, " ".join(tokens)


def _name_matches(field: str, wanted: str, names: tuple[str, ...]) -> bool:
    wanted_kind, wanted_base = _name_parts(field, wanted)
    if not wanted_base:
        return False
    for name in names:
        candidate_kind, candidate_base = _name_parts(field, name)
        if wanted_base != candidate_base:
            continue
        if wanted_kind and candidate_kind and wanted_kind != candidate_kind:
            continue
        return True
    return False


def _row_matches(row: ReferenceRow, field: str, wanted: str) -> bool:
    if field == "KODEPOS":
        return wanted in row.postal_codes
    level = {
        "KELURAHAN": "village",
        "KECAMATAN": "district",
        "KOTA_KABUPATEN": "city",
        "PROVINSI": "province",
    }[field]
    names = (getattr(row, f"{level}_name"),) + getattr(row, f"{level}_aliases")
    return _name_matches(field, wanted, names)


def _candidate_projection(
    rows: tuple[ReferenceRow, ...] | list[ReferenceRow],
) -> tuple[ValidationCandidate, ...]:
    return tuple(
        ValidationCandidate.from_row(row)
        for row in sorted(rows, key=lambda item: item.village_code)
    )


class AdministrativeValidator:
    """Validate normalized components without fuzzy guessing or silent selection."""

    def __init__(
        self,
        reference: ReferenceHierarchy,
        *,
        reference_version: str = REFERENCE_SCHEMA_VERSION,
    ) -> None:
        if not isinstance(reference, ReferenceHierarchy):
            raise TypeError("reference must be a ReferenceHierarchy")
        if not reference_version.strip():
            raise AdministrativeValidationError("reference_version is required")
        self.reference = reference
        self.reference_version = reference_version

    def validate(
        self,
        components: Mapping[str, str | ProvenancedValue | None],
    ) -> AdministrativeValidationResult:
        unknown_fields = sorted(set(components) - set(ENTITY_TYPES))
        if unknown_fields:
            raise AdministrativeValidationError(
                f"unknown address fields: {', '.join(unknown_fields)}"
            )

        values = {
            field: _surface(components.get(field)) for field in ADMINISTRATIVE_FIELDS
        }
        missing = tuple(field for field in ADMINISTRATIVE_FIELDS if not values[field])
        village = values["KELURAHAN"]
        if not village:
            return self._result(
                status="incomplete",
                reason=MISSING_FIELDS,
                missing=missing,
            )

        base_rows = tuple(
            row
            for row in self.reference.rows
            if _row_matches(row, "KELURAHAN", village)
        )
        if not base_rows:
            return self._result(
                status="not_found",
                reason=REFERENCE_COVERAGE_GAP,
                missing=missing,
            )

        supplied_constraints = tuple(
            field for field in ADMINISTRATIVE_FIELDS[1:] if values[field]
        )
        compatible = tuple(
            row
            for row in base_rows
            if all(
                _row_matches(row, field, values[field])
                for field in supplied_constraints
            )
        )

        if not compatible:
            affected = self._affected_fields(base_rows, supplied_constraints, values)
            return self._result(
                status="invalid",
                reason=ADMINISTRATIVE_CONFLICT,
                affected=affected,
                missing=missing,
                candidates=base_rows,
            )
        if len(compatible) > 1:
            return self._result(
                status="ambiguous",
                reason=AMBIGUOUS_CANDIDATES,
                missing=missing,
                candidates=compatible,
            )
        if missing:
            return self._result(
                status="incomplete",
                reason=MISSING_FIELDS,
                missing=missing,
                candidates=compatible,
            )
        return self._result(
            status="valid",
            reason=VALID_CHAIN,
            candidates=compatible,
        )

    @staticmethod
    def _affected_fields(
        base_rows: tuple[ReferenceRow, ...],
        supplied: tuple[str, ...],
        values: Mapping[str, str],
    ) -> tuple[str, ...]:
        affected: set[str] = set()
        for field in supplied:
            if not any(_row_matches(row, field, values[field]) for row in base_rows):
                affected.add(field)
                continue
            remaining = tuple(other for other in supplied if other != field)
            if any(
                all(_row_matches(row, other, values[other]) for other in remaining)
                for row in base_rows
            ):
                affected.add(field)
        if not affected:
            affected.update(supplied)
        return tuple(field for field in ADMINISTRATIVE_FIELDS if field in affected)

    def _result(
        self,
        *,
        status: str,
        reason: str,
        affected: tuple[str, ...] = (),
        missing: tuple[str, ...] = (),
        candidates: tuple[ReferenceRow, ...] = (),
    ) -> AdministrativeValidationResult:
        return AdministrativeValidationResult(
            status=status,
            reason_codes=(reason,),
            affected_fields=affected,
            missing_fields=missing,
            candidates=_candidate_projection(candidates),
            reference_version=self.reference_version,
        )


__all__ = [
    "ADMINISTRATIVE_CONFLICT",
    "ADMINISTRATIVE_FIELDS",
    "AMBIGUOUS_CANDIDATES",
    "AdministrativeValidationError",
    "AdministrativeValidationResult",
    "AdministrativeValidator",
    "MISSING_FIELDS",
    "REFERENCE_COVERAGE_GAP",
    "VALIDATION_STATUSES",
    "VALID_CHAIN",
    "ValidationCandidate",
]

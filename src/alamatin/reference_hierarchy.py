"""Stable administrative-hierarchy and postal-code lookup for ALAMATIN."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


REFERENCE_SCHEMA_VERSION = "1.0.0"
_LEVEL_DIGITS = {
    "province": 2,
    "city": 4,
    "district": 6,
    "village": 10,
}
_POSTAL_CODE = re.compile(r"^\d{5}$")


class ReferenceValidationError(ValueError):
    """Raised when reference data violates the hierarchy contract."""


def normalize_name(value: str) -> str:
    """Normalize an Indonesian place name for exact, non-fuzzy matching."""

    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^0-9A-Za-z]+", " ", without_marks).casefold().split())


def normalize_region_code(value: str, level: str) -> str:
    """Return a dotted Kemendagri-style code and validate its level length."""

    if level not in _LEVEL_DIGITS:
        raise ReferenceValidationError(f"unknown hierarchy level: {level}")
    raw = str(value)
    if not re.fullmatch(r"\s*\d+(?:\.\d+)*\s*", raw):
        raise ReferenceValidationError(f"{level} code has invalid syntax: {value!r}")
    digits = raw.strip().replace(".", "")
    expected = _LEVEL_DIGITS[level]
    if len(digits) != expected:
        raise ReferenceValidationError(
            f"{level} code must contain {expected} digits, got {value!r}"
        )
    if level == "province":
        return digits
    if level == "city":
        return f"{digits[:2]}.{digits[2:]}"
    if level == "district":
        return f"{digits[:2]}.{digits[2:4]}.{digits[4:]}"
    return f"{digits[:2]}.{digits[2:4]}.{digits[4:6]}.{digits[6:]}"


def _code_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _clean_values(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Trace one canonical row back to a catalog source and snapshot."""

    source_id: str
    snapshot: str
    artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.snapshot.strip():
            raise ReferenceValidationError("source_id and snapshot are required")
        if self.artifact_sha256 and not re.fullmatch(
            r"[0-9a-f]{64}", self.artifact_sha256
        ):
            raise ReferenceValidationError("artifact_sha256 must be 64 lowercase hex chars")

    def to_dict(self) -> dict[str, str]:
        result = {"source_id": self.source_id, "snapshot": self.snapshot}
        if self.artifact_sha256:
            result["artifact_sha256"] = self.artifact_sha256
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SourceReference:
        return cls(
            source_id=str(value["source_id"]),
            snapshot=str(value["snapshot"]),
            artifact_sha256=value.get("artifact_sha256"),
        )


@dataclass(frozen=True, slots=True)
class ReferenceRow:
    """One complete province-to-village chain with one or more postal codes."""

    province_code: str
    province_name: str
    city_code: str
    city_name: str
    district_code: str
    district_name: str
    village_code: str
    village_name: str
    postal_codes: tuple[str, ...]
    province_aliases: tuple[str, ...] = ()
    city_aliases: tuple[str, ...] = ()
    district_aliases: tuple[str, ...] = ()
    village_aliases: tuple[str, ...] = ()
    sources: tuple[SourceReference, ...] = ()

    def __post_init__(self) -> None:
        for level in ("province", "city", "district", "village"):
            code_field = f"{level}_code"
            name_field = f"{level}_name"
            code = normalize_region_code(getattr(self, code_field), level)
            if code != getattr(self, code_field):
                raise ReferenceValidationError(
                    f"{code_field} is not canonical: {getattr(self, code_field)!r}"
                )
            if not getattr(self, name_field).strip():
                raise ReferenceValidationError(f"{name_field} is required")

        province = _code_digits(self.province_code)
        city = _code_digits(self.city_code)
        district = _code_digits(self.district_code)
        village = _code_digits(self.village_code)
        if not city.startswith(province):
            raise ReferenceValidationError("city code does not belong to province")
        if not district.startswith(city):
            raise ReferenceValidationError("district code does not belong to city")
        if not village.startswith(district):
            raise ReferenceValidationError("village code does not belong to district")

        cleaned_postal_codes = _clean_values(self.postal_codes)
        if not cleaned_postal_codes:
            raise ReferenceValidationError("at least one postal code is required")
        if any(not _POSTAL_CODE.fullmatch(code) for code in cleaned_postal_codes):
            raise ReferenceValidationError("postal codes must contain exactly five digits")
        if cleaned_postal_codes != self.postal_codes:
            raise ReferenceValidationError("postal_codes must be unique and sorted")
        if not self.sources:
            raise ReferenceValidationError("each row requires at least one source reference")
        source_keys = [(item.source_id, item.snapshot) for item in self.sources]
        if source_keys != sorted(set(source_keys)):
            raise ReferenceValidationError("sources must be unique and sorted")

        for level in ("province", "city", "district", "village"):
            aliases = getattr(self, f"{level}_aliases")
            if aliases != _clean_values(aliases):
                raise ReferenceValidationError(f"{level}_aliases must be unique and sorted")

    @property
    def record_id(self) -> str:
        return f"ID-{_code_digits(self.village_code)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "province": {
                "code": self.province_code,
                "name": self.province_name,
                "aliases": list(self.province_aliases),
            },
            "city": {
                "code": self.city_code,
                "name": self.city_name,
                "aliases": list(self.city_aliases),
            },
            "district": {
                "code": self.district_code,
                "name": self.district_name,
                "aliases": list(self.district_aliases),
            },
            "village": {
                "code": self.village_code,
                "name": self.village_name,
                "aliases": list(self.village_aliases),
            },
            "postal_codes": list(self.postal_codes),
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReferenceRow:
        return cls(
            province_code=str(value["province"]["code"]),
            province_name=str(value["province"]["name"]),
            province_aliases=tuple(value["province"].get("aliases", ())),
            city_code=str(value["city"]["code"]),
            city_name=str(value["city"]["name"]),
            city_aliases=tuple(value["city"].get("aliases", ())),
            district_code=str(value["district"]["code"]),
            district_name=str(value["district"]["name"]),
            district_aliases=tuple(value["district"].get("aliases", ())),
            village_code=str(value["village"]["code"]),
            village_name=str(value["village"]["name"]),
            village_aliases=tuple(value["village"].get("aliases", ())),
            postal_codes=tuple(value["postal_codes"]),
            sources=tuple(SourceReference.from_dict(item) for item in value["sources"]),
        )


@dataclass(frozen=True, slots=True)
class LookupResult:
    """A lookup result that makes ambiguity explicit."""

    status: str
    candidates: tuple[ReferenceRow, ...]

    @property
    def match(self) -> ReferenceRow | None:
        return self.candidates[0] if self.status == "exact" else None


class ReferenceHierarchy:
    """Validated, deterministic exact lookup over canonical hierarchy rows."""

    def __init__(self, rows: Iterable[ReferenceRow]) -> None:
        self.rows = tuple(sorted(rows, key=lambda row: row.village_code))
        if not self.rows:
            raise ReferenceValidationError("reference hierarchy cannot be empty")
        self._validate_integrity()
        village_index: dict[str, list[ReferenceRow]] = {}
        for row in self.rows:
            for name in (row.village_name,) + row.village_aliases:
                village_index.setdefault(normalize_name(name), []).append(row)
        self._village_index = {
            name: tuple(sorted(matches, key=lambda row: row.village_code))
            for name, matches in village_index.items()
        }
        self._code_index = {row.village_code: row for row in self.rows}

    def _validate_integrity(self) -> None:
        seen_villages: set[str] = set()
        parent_contracts: dict[tuple[str, str], tuple[str, str]] = {}
        for row in self.rows:
            if row.village_code in seen_villages:
                raise ReferenceValidationError(
                    f"duplicate canonical village code: {row.village_code}"
                )
            seen_villages.add(row.village_code)
            contracts = (
                (("city", row.city_code), (row.province_code, row.city_name)),
                (("district", row.district_code), (row.city_code, row.district_name)),
                (("village", row.village_code), (row.district_code, row.village_name)),
            )
            for key, contract in contracts:
                previous = parent_contracts.setdefault(key, contract)
                if previous != contract:
                    raise ReferenceValidationError(
                        f"inconsistent parent/name contract for {key[0]} {key[1]}"
                    )

    def lookup(
        self,
        *,
        village: str,
        district: str | None = None,
        city: str | None = None,
        province: str | None = None,
        postal_code: str | None = None,
    ) -> LookupResult:
        """Match canonical names or aliases exactly after normalization."""

        criteria = {
            "village": village,
            "district": district,
            "city": city,
            "province": province,
        }
        candidates = []
        for row in self._village_index.get(normalize_name(village), ()):
            matches = True
            for level, wanted in criteria.items():
                if wanted is None:
                    continue
                names = (getattr(row, f"{level}_name"),) + getattr(
                    row, f"{level}_aliases"
                )
                if normalize_name(wanted) not in {normalize_name(name) for name in names}:
                    matches = False
                    break
            if matches and postal_code is not None and postal_code not in row.postal_codes:
                matches = False
            if matches:
                candidates.append(row)
        if not candidates:
            status = "not_found"
        elif len(candidates) == 1:
            status = "exact"
        else:
            status = "ambiguous"
        return LookupResult(status=status, candidates=tuple(candidates))

    def by_village_code(self, village_code: str) -> ReferenceRow | None:
        canonical = normalize_region_code(village_code, "village")
        return self._code_index.get(canonical)

    def to_document(
        self,
        *,
        build: Mapping[str, Any],
        exceptions: Iterable[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        return {
            "schema_version": REFERENCE_SCHEMA_VERSION,
            "build": dict(build),
            "rows": [row.to_dict() for row in self.rows],
            "exceptions": list(exceptions),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ReferenceHierarchy:
        if document.get("schema_version") != REFERENCE_SCHEMA_VERSION:
            raise ReferenceValidationError(
                f"unsupported reference schema: {document.get('schema_version')!r}"
            )
        return cls(ReferenceRow.from_dict(row) for row in document.get("rows", ()))

    @classmethod
    def from_json(cls, path: Path) -> ReferenceHierarchy:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ReferenceValidationError(f"invalid reference JSON: {error}") from error
        return cls.from_document(document)

"""Shared ALM-025 JSON contract loading and dependency-free validation."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .administrative_validator import ADMINISTRATIVE_FIELDS
from .quality_gate import PERLU_KONFIRMASI, SIAP_DIPROSES, TIDAK_VALID


CONTRACT_VERSION = "1.0.0"
CONTRACT_RELATIVE_PATH = "contracts/address-api.v1.schema.json"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = ROOT / CONTRACT_RELATIVE_PATH


class ContractValidationError(ValueError):
    """Raised when a schema or contract document violates the frozen contract."""


def load_contract_schema(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    validate_schema_document(document)
    return document


def _resolve_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ContractValidationError(f"only local schema references are allowed: {reference}")
    value: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or part not in value:
            raise ContractValidationError(f"unresolved schema reference: {reference}")
        value = value[part]
    if not isinstance(value, dict):
        raise ContractValidationError(f"schema reference is not an object: {reference}")
    return value


def validate_schema_document(schema: dict[str, Any]) -> None:
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractValidationError("contract must use JSON Schema draft 2020-12")
    if schema.get("$id") != "https://alamatin.local/contracts/address-api.v1.schema.json":
        raise ContractValidationError("unexpected contract $id")
    if not isinstance(schema.get("$defs"), dict):
        raise ContractValidationError("contract requires $defs")

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if reference is not None:
                _resolve_ref(schema, reference)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(schema)


def _is_type(value: Any, expected: str) -> bool:
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "boolean": lambda: isinstance(value, bool),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "null": lambda: value is None,
    }.get(expected, lambda: False)()


def _validate_node(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str,
) -> None:
    if "$ref" in schema:
        _validate_node(value, _resolve_ref(root, schema["$ref"]), root, path)
        return
    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            try:
                _validate_node(value, option, root, path)
            except ContractValidationError:
                continue
            matches += 1
        if matches != 1:
            raise ContractValidationError(f"{path}: expected exactly one schema match")
        return
    if "const" in schema and value != schema["const"]:
        raise ContractValidationError(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"{path}: unsupported value {value!r}")

    expected_types = schema.get("type")
    if expected_types is not None:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if not any(_is_type(value, item) for item in expected_types):
            raise ContractValidationError(
                f"{path}: expected type {' or '.join(expected_types)}"
            )

    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise ContractValidationError(f"{path}: missing required keys {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ContractValidationError(f"{path}: unknown keys {unknown}")
        for key, nested in value.items():
            if key in properties:
                _validate_node(nested, properties[key], root, f"{path}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ContractValidationError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ContractValidationError(f"{path}: too many items")
        if "items" in schema:
            for index, nested in enumerate(value):
                _validate_node(nested, schema["items"], root, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ContractValidationError(f"{path}: string is too short")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            raise ContractValidationError(f"{path}: string does not match {pattern!r}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractValidationError(f"{path}: value is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ContractValidationError(f"{path}: value is above maximum")


def _walk_values(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, nested in value.items():
            yield from _walk_values(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _walk_values(nested, f"{path}[{index}]")


def _validate_provenance(document: dict[str, Any]) -> None:
    for path, value in _walk_values(document):
        if not isinstance(value, dict):
            continue
        if {"value", "source", "confirmed"}.issubset(value):
            confirmed = value["confirmed"]
            source = value["source"]
            if confirmed != (source == "confirmed_by_user"):
                raise ContractValidationError(
                    f"{path}: confirmed must match confirmed_by_user provenance"
                )
        if {"model_score", "source"}.issubset(value):
            score = value["model_score"]
            if (score is not None) != (value["source"] == "extracted_by_model"):
                raise ContractValidationError(
                    f"{path}: model_score is allowed exactly for model-derived values"
                )


def _validate_response_semantics(document: dict[str, Any]) -> None:
    issues = document["quality_gate"]["issues"]
    status = document["quality_gate"]["status"]
    expected_status = (
        TIDAK_VALID
        if any(issue["severity"] == "high" for issue in issues)
        else PERLU_KONFIRMASI
        if issues
        else SIAP_DIPROSES
    )
    if status != expected_status:
        raise ContractValidationError("$.quality_gate.status disagrees with issues")

    # Mirror the ALM-024 boundary: only ADMINISTRATIVE_FIELDS can be
    # contradicted by the governed reference, so only they are evidence strong
    # enough to reach TIDAK_VALID. Without this the contract would advertise a
    # high-severity issue on JALAN that the quality gate refuses to produce.
    for index, issue in enumerate(issues):
        if issue["severity"] != "high":
            continue
        non_critical = [
            field
            for field in issue["affected_fields"]
            if field not in ADMINISTRATIVE_FIELDS
        ]
        if non_critical:
            raise ContractValidationError(
                f"$.quality_gate.issues[{index}]: high severity cannot affect "
                f"non-critical fields {non_critical}"
            )

    for index, correction in enumerate(document["corrections"]):
        decision = correction["decision"]
        confirmation = correction["user_confirmation"]
        applied = correction["applied"]
        if decision == "confirmed":
            if confirmation is None or not applied:
                raise ContractValidationError(
                    f"$.corrections[{index}]: confirmed correction requires user action"
                )
            if correction["proposed_value"]["source"] != "confirmed_by_user":
                raise ContractValidationError(
                    f"$.corrections[{index}]: applied value requires user provenance"
                )
        elif confirmation is not None or applied:
            raise ContractValidationError(
                f"$.corrections[{index}]: unapplied correction cannot have confirmation"
            )

    trail = document["audit_trail"]
    sequences = [event["sequence"] for event in trail]
    if sequences != list(range(1, len(sequences) + 1)):
        raise ContractValidationError("$.audit_trail: sequence must be contiguous")

    geocoding = document["geocoding"]
    geo_status = geocoding["status"]
    if geo_status == "NOT_REQUESTED":
        if geocoding["consent"] or any(
            geocoding[key] is not None
            for key in ("provider", "precision", "latitude", "longitude", "error_code")
        ) or geocoding["components"]:
            raise ContractValidationError("$.geocoding: NOT_REQUESTED must be empty")
    elif geo_status == "EXTERNAL_FAILURE":
        if (
            not geocoding["consent"]
            or not geocoding["provider"]
            or not geocoding["error_code"]
            or geocoding["latitude"] is not None
            or geocoding["longitude"] is not None
            or geocoding["components"]
        ):
            raise ContractValidationError("$.geocoding: invalid EXTERNAL_FAILURE")
    elif geo_status == "SUCCESS":
        if (
            not geocoding["consent"]
            or not geocoding["provider"]
            or geocoding["latitude"] is None
            or geocoding["longitude"] is None
            or geocoding["error_code"] is not None
        ):
            raise ContractValidationError("$.geocoding: invalid SUCCESS")
    elif not geocoding["consent"] or geocoding["error_code"] is not None:
        raise ContractValidationError("$.geocoding: invalid AMBIGUOUS result")


def validate_contract_document(
    document: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> None:
    """Validate JSON shape plus provenance, confirmation, and status invariants."""

    if schema is None:
        schema = load_contract_schema()
    _validate_node(document, schema, schema, "$")
    for path, value in _walk_values(document):
        if isinstance(value, dict) and "confidence" in value:
            raise ContractValidationError(f"{path}: use model_score, not confidence")
    _validate_provenance(document)
    if document.get("document_type") == "address_parse_response":
        _validate_response_semantics(document)


__all__ = [
    "CONTRACT_RELATIVE_PATH",
    "CONTRACT_VERSION",
    "ContractValidationError",
    "DEFAULT_CONTRACT_PATH",
    "load_contract_schema",
    "validate_contract_document",
    "validate_schema_document",
]

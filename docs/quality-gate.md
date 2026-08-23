# Quality gate, reason codes, and clarification

ALM-024 converts the deterministic ALM-023 validator result and any unapplied
ALM-022 semantic correction into one operational status. The implementation is
`alamatin.quality_gate.evaluate_quality_gate`; it does not use a risk score,
model confidence, fuzzy threshold, or geocoder result.

## Status and precedence

The first matching rule wins:

1. `TIDAK_VALID` when at least one issue has severity `high`.
2. `PERLU_KONFIRMASI` when there is no `high` issue and at least one issue has
   severity `medium`.
3. `SIAP_DIPROSES` when there are no issues.

This precedence is exported as `STATUS_PRECEDENCE` and returned with
`rules.version = quality-gate-v1` in every JSON response. A
`QualityGateResult` rejects a manually supplied status that disagrees with its
issues, so the status can be reconstructed using only the issues and these
rules. In particular, an unresolved high-severity administrative or postcode
conflict can never produce `SIAP_DIPROSES`.

## Critical-field boundary

High severity is reserved for fields the governed administrative reference can
actually contradict. Those are exactly `ADMINISTRATIVE_FIELDS`: `KELURAHAN`,
`KECAMATAN`, `KOTA_KABUPATEN`, `PROVINSI`, and `KODEPOS`. `evaluate_quality_gate`
raises `QualityGateError` when a validator conflict names any other field, so a
caller cannot route `JALAN`, `NOMOR`, `RT`, `RW`, or `DETAIL_LOKASI` into
`TIDAK_VALID`. This enforces the critical-field policy frozen in
[`docs/product-scope.md`](product-scope.md), which keeps those components
visible and useful for clarification while forbidding any claim that their
absence or form proves an address invalid.

Non-critical fields can still produce a medium issue. A pending semantic
suggestion on `JALAN`, for example, yields `CORRECTION_REQUIRES_CONFIRMATION`
and `PERLU_KONFIRMASI`; an address naming no street-level locator yields
`MISSING_STREET_LOCATOR`, and one naming no house-level locator yields
`MISSING_HOUSE_LOCATOR`, both with the same status.

This set is deliberately narrower than `CRITICAL_ENTITY_TYPES` in
`alamatin.evaluation_metrics`, which also scores `JALAN` and `NOMOR`. The two
answer different questions: which components matter for measuring extraction
quality, versus which components the reference can prove wrong.

Confirmation does not mutate an issue inside the quality gate. The caller
records a confirmed correction through ALM-022, reruns administrative
validation, and evaluates the new result. This keeps the audit trail and the
status decision deterministic.

## Reason-code contract

| Reason code | Severity | Affected fields | Operational meaning |
|---|---|---|---|
| `KODEPOS_TIDAK_COCOK` | high | `KODEPOS` | The supplied postcode conflicts with the governed administrative chain. |
| `ADMINISTRATIVE_CONFLICT` | high | Conflicting non-postcode fields, restricted to `ADMINISTRATIVE_FIELDS` | One or more supplied fields contradict the candidate chain. |
| `MISSING_ADMINISTRATIVE_FIELDS` | medium | Every missing administrative field | Required context is incomplete. |
| `AMBIGUOUS_ADMINISTRATIVE_CANDIDATES` | medium | `KELURAHAN`, `KECAMATAN`, `KOTA_KABUPATEN` | More than one reference chain remains possible. |
| `KELURAHAN_TIDAK_DITEMUKAN` | medium | `KELURAHAN` | The village is absent from the current reference version; this is a coverage gap, not proof that the address is wrong. |
| `CORRECTION_REQUIRES_CONFIRMATION` | medium | Fields with unapplied semantic suggestions | A non-deterministic correction still requires explicit user action. |
| `MISSING_STREET_LOCATOR` | medium | `JALAN` | Neither `JALAN` nor `DETAIL_LOKASI` names a street, kampung, or landmark, so a valid administrative chain still has no delivery point. |
| `MISSING_HOUSE_LOCATOR` | medium | `NOMOR` | None of `NOMOR`, `RT`, `RW`, or `DETAIL_LOKASI` pins a door within the street. `RT`/`RW` satisfy it, because that is how a kampung address is written (DEC-010 amendment). A block, kavling, or unit reference also satisfies it, read from wherever the label puts it (DEC-012). |
| `OUTSIDE_REFERENCE_COVERAGE` | medium | `PROVINSI` | The address names a province the reference holds no rows for, so its verdict is not evidence. Replaces a conflict rather than accompanying it (DEC-012). |

The first and fifth codes preserve the minimum user-facing codes in the main
execution plan. `source_reason_code` retains the upstream validator reason so
the apparent `KELURAHAN_TIDAK_DITEMUKAN` result remains traceable to
`REFERENCE_COVERAGE_GAP` rather than being misrepresented as a definite user
error.

Each issue always contains:

- `reason_code`
- `severity`
- `message`
- `affected_fields`
- `clarification_question`
- `source_reason_code`

Questions are generated from fixed, field-specific templates. They never
contain recipient names, phone numbers, or raw input text. `PII_DETECTED`
remains part of the separate ALM-021 privacy/audit result: already-redacted PII
is not itself evidence that an address is invalid.

## Example

```python
from alamatin.quality_gate import evaluate_quality_gate

quality = evaluate_quality_gate(
    validation_result,
    normalization_changes=pending_suggestions,
)
payload = quality.to_response_dict()
```

When a postcode conflict and a pending correction appear together, both issues
are retained, but the high-severity conflict wins and the status is
`TIDAK_VALID`. This preserves all user actions needed without hiding lower
precedence issues.

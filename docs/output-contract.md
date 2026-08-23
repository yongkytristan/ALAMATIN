# Output contract and audit trail

ALM-025 freezes the shared request/response contract at
`contracts/address-api.v1.schema.json`. It is a JSON Schema draft 2020-12
document with contract version `1.2.0`. Backend code loads that exact file via
`alamatin.output_contract`; the browser uses the same repository-relative path
from `web/address-contract.js`. There is no generated or separately maintained
frontend copy.

## Frozen response sections

Every response contains:

- `versions`: contract, model, normalizer, validator, reference-data, and
  quality-gate versions;
- `pii`: downstream-safe and redacted text, safe entity metadata, reason codes,
  and warnings;
- `components`: canonical fields whose result contains value, immediate source,
  confirmation state, `model_score`, and previous value;
- `normalized_address`: the rendered value with the same provenance contract;
- `quality_gate`: operational status, complete issues, and versioned precedence;
- `corrections`: previous/proposed values, rule, decision, applied state, and
  explicit user-confirmation record;
- `geocoding`: consent and one of `NOT_REQUESTED`, `SUCCESS`, `AMBIGUOUS`, or
  `EXTERNAL_FAILURE`;
- `audit_trail`: ordered stage events with actor, rule, and before/after values.

`model_score` is an uncalibrated model output and must not be presented as
probability or confidence. The key `confidence` is forbidden. A non-null
`model_score` is valid only for `source=extracted_by_model`; rule, hierarchy,
geocoder, and user-confirmed values use `null`.

## Quality-gate agreement

`alamatin.quality_gate` owns the operational status rules; the contract only
re-states them for the frontend. Every restatement is tied back to that module
by a test, so the two cannot drift:

- `qualityIssue.reason_code` is an enum of the six frozen reason codes, not a
  free-form string, so a client can switch on it safely;
- `qualityIssue.severity`, `qualityGate.status`, and `rules.version` mirror
  `SEVERITIES`, `QUALITY_STATUSES`, and `RULES_VERSION`;
- `field` mirrors the ten canonical `ENTITY_TYPES`.

A high-severity issue may only affect `ADMINISTRATIVE_FIELDS`: `KELURAHAN`,
`KECAMATAN`, `KOTA_KABUPATEN`, `PROVINSI`, and `KODEPOS`. Those are the only
components the governed reference can contradict, so they are the only evidence
that can reach `TIDAK_VALID`. `JALAN`, `NOMOR`, `RT`, `RW`, and `DETAIL_LOKASI`
can still carry a medium issue such as `CORRECTION_REQUIRES_CONFIRMATION`,
`MISSING_STREET_LOCATOR`, or `MISSING_HOUSE_LOCATOR`. This
matches the boundary enforced by the quality gate and frozen in
[`docs/product-scope.md`](product-scope.md), which forbids claiming that a
non-critical component's absence or form proves an address invalid.

## Versions 1.1.0 and 1.2.0

Both additive. `1.1.0` (DEC-010) adds `MISSING_STREET_LOCATOR`; `1.2.0`
(DEC-010's amendment) adds `MISSING_HOUSE_LOCATOR`. `versions.contract` and the
response `schema_version` are now `1.2.0`.

**Requests still accept `1.0.0`.** The request examples in
[`../contracts/examples/`](../contracts/examples/) deliberately stay at `1.0.0`
as the standing proof of that, so a client written against the previous version
keeps working. The existing six reason codes keep their meaning and order.

## Provenance and confirmation invariants

Result values use the ALM-022 source allowlist. `confirmed=true` is valid only
with `source=confirmed_by_user`, and every confirmed correction retains its
`previous_value`. A `requires_confirmation` or `rejected` correction cannot be
marked applied and cannot contain a user-confirmation record.

The response never stores raw PII inside a PII entity. Geocoding coordinates
are separately wrapped with `source=returned_by_geocoder`. An external service
failure is recorded explicitly but cannot by itself change a valid local
quality-gate decision into `TIDAK_VALID`.

## Automatic validation

`validate_contract_document(...)` validates the JSON Schema subset used by the
contract and then enforces cross-field invariants for provenance, corrections,
quality status, audit ordering, and geocoding. It uses only the Python standard
library so the repository's clean CI environment can run it without adding an
unpinned dependency.

```python
import json
from alamatin.output_contract import validate_contract_document

validate_contract_document(json.loads(payload))
```

The test suite validates all four request/response pairs in
`contracts/examples`: success, ambiguity, invalid administrative data, and an
external geocoding failure. Tests also mutate valid examples to prove that
missing versions/provenance, `confidence`, forged confirmation, inconsistent
quality status, raw PII fields, and broken audit ordering are rejected.

ALM-026 extends this backward-compatibly with `api_error` and the P1
`address_batch_request` definition. Both remain in the same canonical schema;
the batch contract is bounded to 100 items and is not enabled operationally in
the P0 release.

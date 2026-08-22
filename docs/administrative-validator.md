# Administrative validator

ALM-023 validates normalized Jawa Barat administrative components against the
governed `ReferenceHierarchy` produced by ALM-008. It performs exact normalized
comparison only: there is no fuzzy lookup, probabilistic choice, or mutation of
the submitted address.

## Input and reference boundary

`AdministrativeValidator.validate(components)` accepts the five administrative
fields `KELURAHAN`, `KECAMATAN`, `KOTA_KABUPATEN`, `PROVINSI`, and `KODEPOS`.
Canonical non-administrative NER fields may coexist in the mapping and are
ignored. Values may be strings or the `ProvenancedValue` output of ALM-022.

Comparison is insensitive to case, punctuation, whitespace, aliases, and known
designator surface forms (`Kel.`, `Kecamatan`, `Kab.`, `Kota`, `Prov.`). City
type remains semantic: `Kota Bandung` does not match `Kabupaten Bandung`.

The caller supplies a stable `reference_version`; it is echoed in every result.
Rows and candidates are sorted by canonical village code, making output stable
for the same input and reference version.

## Status contract

| Status | Meaning | Primary reason code |
|---|---|---|
| `valid` | all five fields match one reference chain | `VALID_ADMINISTRATIVE_CHAIN` |
| `incomplete` | one or more required fields are missing | `MISSING_ADMINISTRATIVE_FIELDS` |
| `invalid` | supplied fields conflict with known candidate chains | `ADMINISTRATIVE_CONFLICT` |
| `ambiguous` | multiple chains remain compatible | `AMBIGUOUS_ADMINISTRATIVE_CANDIDATES` |
| `not_found` | village/alias is absent from reference coverage | `REFERENCE_COVERAGE_GAP` |

Only `invalid` means the supplied address is contradicted by governed reference
evidence. `not_found` is explicitly a coverage gap and must not be shown as a
definite user error. A missing village is `incomplete`, not `not_found`, because
no lookup was possible.

## Conflicts and ambiguity

An invalid result contains `affected_fields` and every plausible village
candidate available before the conflicting constraints were applied. Candidate
records expose the canonical hierarchy and postal codes required to explain the
conflict or construct a suggestion in ALM-024; the validator itself never
applies a correction.

An ambiguous result returns all compatible candidates in deterministic order.
Its `match` property is `None`, so callers cannot silently take the first row.
Providing parent/postcode context may narrow ambiguity, but the result remains
`incomplete` until all required fields are present.

Recommended pipeline order is PII redaction, NER, deterministic normalization,
administrative validation, then user-confirmed correction. Tests cover valid
chains, aliases/designators, postcode and city-type conflicts, missing values,
ambiguous names, cross-candidate conflicts, reference coverage gaps,
provenance-bearing inputs, canonical candidate ordering, and JSON determinism.

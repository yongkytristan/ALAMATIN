# Address normalizer and provenance

ALM-022 normalizes structured address components after PII removal and NER. It
does not infer missing components, resolve administrative conflicts, or silently
apply a likely spelling/postcode correction.

## Source contract

Every value has exactly one immediate source from this allowlist:

- `user_input`
- `rule_extracted`
- `extracted_by_model`
- `normalized_by_dictionary`
- `inferred_from_hierarchy`
- `returned_by_geocoder`
- `confirmed_by_user`

`confirmed=true` is valid only together with `confirmed_by_user`. This invariant
is enforced when the value is constructed, so a hierarchy/model/geocoder result
cannot accidentally appear as a user-confirmed correction.

## Deterministic normalization

Call `normalize_address(components)` with keys from the canonical NER entity
schema. A value may be a string (default source `user_input`) or a
`ProvenancedValue` supplied by the preceding pipeline stage. The normalizer
applies only representation-preserving operations:

- Unicode/whitespace cleanup;
- documented designator expansion such as `Jl.` to `Jalan`, `Kec.` to
  `Kecamatan`, and `Kab.` to `Kabupaten`;
- component-aware capitalization;
- RT/RW formatting to three digits;
- spacing normalization for a five-digit postcode;
- `No`/`Nomor` presentation as `No.` without changing the identifier.

It keeps `Desa` and `Kelurahan`, `Gang` and `Jalan`, and `Kota` and `Kabupaten`
semantically distinct. Unknown or ambiguous formats are preserved. Running the
normalizer again over its output makes no further changes.

Each actual operation appends a `NormalizationChange` with field, before value
and source, after value and source, stable rule ID, decision, and applied state.
Unchanged fields retain their original source. `NormalizationResult` exposes
both canonical component order and a JSON-ready full audit trail.

## Suggestions and confirmation

Typo repair, hierarchy conflict resolution, postcode replacement, and geocoder
results are semantic changes. Create them with `propose_correction(...)`. The
returned record has `decision=requires_confirmation`, `applied=false`, and
`confirmed=false`; it is deliberately not part of deterministic output.

Only `confirm_correction(..., user_confirmed=True)` applies that proposal. The
new audit record then uses `source=confirmed_by_user`. A false or missing user
action raises an error instead of marking the correction confirmed.

Recommended pipeline order:

1. remove/redact PII with `process_pii`;
2. run NER over its `address_text`;
3. pass extracted components and `extracted_by_model` provenance to the
   deterministic normalizer;
4. validate normalized values against the hierarchy;
5. expose conflicts as suggestions and wait for explicit confirmation.

Tests cover primary abbreviations, capitalization, RT/RW, number and postcode
formatting, ambiguous-value preservation, exact source allowlisting, complete
audit serialization, idempotency, non-applied suggestions, and confirmation
invariants.

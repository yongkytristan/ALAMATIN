# PII extraction and redaction

Issue ALM-021 introduces a conservative boundary between raw user input and
address parsing. The PII module handles only confirmed recipient fields and
Indonesian phone formats. Email, account, and order identifiers remain outside
the current scope and must not be added to NER labels.

## Integration contract

Call `process_pii(raw_input)` before tokenization, NER, normalization, or
external lookup. The result exposes two safe views:

- `address_text` removes confirmed PII fields and is the only input intended
  for downstream address modules;
- `redacted_text` preserves the original sentence shape but replaces detected
  values with `[NAME_REDACTED]` or `[PHONE_REDACTED]`, for UI/debug display.

`entities` contains only type, character offsets, and the fixed replacement.
It deliberately has no raw-value field. `to_response_dict()` is the safe API
shape. Use `redact_for_logging(value)` at a logging boundary; never log raw
request input, exceptions containing input, or a custom object that retains it.

When at least one entity is confirmed, `reason_codes` contains
`PII_DETECTED`. Phone digits do not appear in the fixed replacement, so the
complete number cannot leak through the redacted response, object
representation, or documented logging path.

## Detection policy

Mobile detection accepts common local and international Indonesian forms:
numbers beginning with `08`, `+62 8`, or `62 8`, with spaces, dots,
parentheses, or hyphens. A mobile-shaped value following an explicit identifier
label such as `NPSN`, `order`, `resi`, `invoice`, `rekening`, or `kode` is not
treated as a phone. Postal codes, RT/RW, house numbers, years, and administrative
codes are too short or structurally different.

Landlines have a higher false-positive risk and are detected only after a
telephone label such as `Tel` or `Telepon`. Recipient names likewise require an
explicit `Penerima:`, `Nama Penerima:`, `a.n.:`, or `Atas Nama:` marker. The
module does not infer PII from an unmarked capitalized phrase because it may be
a shop, building, road, or landmark.

## Failure behavior

Extraction is fail-open for ambiguous or malformed name fields: unconfirmed
text stays in `address_text`, preventing silent address loss. Name-rule failure
is isolated from phone redaction and reports
`RECIPIENT_NAME_EXTRACTION_FAILED`; a confirmed phone remains removed and
redacted. Callers may continue address parsing with `address_text` and record
only the warning code, never the raw input.

Unit tests use constructed synthetic numbers and cover mobile/landline forms,
multiple phones, identifier collisions, common address-number false positives,
recipient extraction, safe serialization/logging, and failure isolation.

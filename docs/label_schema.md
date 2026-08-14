# ALAMATIN NER label schema

- Schema version: `1.0.0`
- Annotation scheme: BIO, flat and non-overlapping
- Entity types: 10
- Model labels: 21 (`O` plus `B-` and `I-` for every entity)
- Canonical implementation: `src/alamatin/label_schema.py`
- Review fixture: `tests/fixtures/ner_gold_examples.json`

This document is the annotation contract for address-component extraction. It
does not define PII extraction, normalization, administrative validation, or
whether an address is operationally ready to ship.

## 1. Annotation unit and BIO rules

Annotate the smallest complete address component that preserves its operational
meaning. Annotation is performed over tokens produced by the future canonical
tokenizer; the examples in this document use whitespace and punctuation-aware
tokens for readability.

- `B-X` starts an entity of type `X`.
- `I-X` continues the same entity.
- `O` marks a token outside the address-component schema.
- An `I-X` may only follow `B-X` or `I-X` of the same type.
- Entities cannot overlap or nest.
- A new occurrence of the same type starts with `B-X`.
- Exclude separators such as commas, slashes, and semicolons unless punctuation
  is lexical content inside a token such as `Jl.` or `No.`.
- Preserve the observed text, including typos and abbreviations. Normalization
  happens in a separate module and must not silently alter gold spans.

Example:

```text
Tokens: Jl. | Asia | Afrika | No. | 12 | , | Kota | Bandung | 40111
Labels: B-JALAN | I-JALAN | I-JALAN | B-NOMOR | I-NOMOR | O |
        B-KOTA_KABUPATEN | I-KOTA_KABUPATEN | B-KODEPOS
```

## 2. Entity definitions

### `JALAN`

Named road or named access route used to reach the destination.

Include:

- road designators when present: `Jalan`, `Jl.`, `Jln.`, `Jaln`;
- named alleys or access routes: `Gang Melati`, `Gg. Kelinci`;
- a named kampung or dusun (hamlet) used in place of a formal road name, for
  example `Kp. Cihaurseah` or `Dusun Karanganyar`, when no `Jalan`/`Gang` name
  is present. It plays the same navigational role as a road name in these
  addresses -- see the rule clarification log at the end of this section;
- the complete proper name and ordinal attached to the road.

Exclude:

- building number, RT/RW, postal code, and administrative regions;
- an unnamed directional instruction such as `masuk 50 meter`;
- building, tower, floor, unit, block, or landmark descriptions.

Boundary examples:

- `Jl. Asia Afrika` → all three tokens are `JALAN`.
- `Jl. Mawar No. 7` → `Jl. Mawar` is `JALAN`; `No. 7` is `NOMOR`.
- `Gang Melati Blok C2` → `Gang Melati` is `JALAN`; `Blok C2` is
  `DETAIL_LOKASI`.
- `Kp. Cihaurseah` (no road name present) → `JALAN`.
- `Jl. Mawar, Kp. Cihaurseah` (both present) → `Jl. Mawar` is `JALAN`;
  `Kp. Cihaurseah` is `DETAIL_LOKASI`, since the road name already resolves
  the navigational role and the kampung becomes a supporting locality detail.

#### Rule clarification log

- 2026-08-14 (ALM-013): the rural school-address benchmark (ALM-012)
  surfaced many addresses that name only a kampung or dusun, with no formal
  road at all (for example `KP. CIHAURSEAH`, `Dusun Karanganyar Rt.03
  Rw.20`). Decision (project owner): label a kampung/dusun name as `JALAN`
  when it is the only navigational identifier present, and as
  `DETAIL_LOKASI` when a formal `Jalan`/`Gang` name is also present. This
  does not change `ENTITY_TYPES`, `BIO_LABELS`, or any existing labeled
  example; it fills a gap the original schema draft did not anticipate.

### `NOMOR`

Explicit building, house, or street number identifying a destination on a road.

Include the number marker and value when adjacent: `No. 12`, `Nomor 8B`,
`Nomer 10`. A compact token such as `No.12A` is one `B-NOMOR` token.

Exclude order numbers, invoice numbers, phone numbers, RT/RW values, floor and
unit identifiers, kilometers, and postal codes. A bare number is `NOMOR` only
when address context or structured provenance resolves its role.

### `RT`

Neighborhood association identifier. Include marker and value when adjacent,
for example `RT 04` or the compact token `RT04`.

Do not include a separator between RT and RW. In `RT 04 / RW 09`, `/` is `O`.

### `RW`

Community association identifier. Include marker and value when adjacent, for
example `RW 09` or `RW09`. Apply the same separator rule as `RT`.

### `KELURAHAN`

Village-level administrative unit, including kelurahan or desa.

Include an adjacent designator and the complete name: `Kel. Braga`,
`Kelurahan Pasar Baru`, `Desa Cibiru Wetan`, or `Ds. Citarum`.

Without a designator, annotate a name only when structured source data or the
administrative chain resolves it as village-level. Otherwise mark the example
for adjudication.

### `KECAMATAN`

Subdistrict administrative unit. Include an adjacent designator and full name:
`Kec. Sumur Bandung`, `Kecamatan Sawah Besar`, or typo variants such as
`Kecmatan Coblong`.

Without a designator, require structured evidence or an unambiguous hierarchy.

### `KOTA_KABUPATEN`

Regency or city administrative unit. Include `Kota` or `Kabupaten` when present
and the complete name, such as `Kota Bandung`, `Kabupaten Bandung`, or
`Jakarta Pusat`.

The label describes the administrative role, not whether the surface contains
the word `Kota` or `Kabupaten`. A bare `Bandung` requires context or structured
provenance because it may refer to multiple administrative levels.

### `PROVINSI`

Province name and adjacent province designator when present. Accepted surface
forms include official names, documented abbreviations, and observed typos:
`Jawa Barat`, `Provinsi Jawa Barat`, `Jabar`, `DKI Jakarta`, `Jawa Brat`.

Normalization to the canonical province name is outside NER.

### `KODEPOS`

Five-digit Indonesian postal code used in address context. Annotate only the
numeric value; introductory words such as `Kode Pos` are `O`.

A five-digit token outside address context, such as an order or voucher number,
is `O`. NER identifies its textual role; the administrative validator later
checks whether the code matches the stated regions.

### `DETAIL_LOKASI`

Destination detail that helps a person locate the precise building or access
point but is not one of the structured entities above.

Include:

- building, complex, tower, block, floor, room, and unit identifiers;
- public facility or destination venue names when used as the delivery point;
- landmarks and spatial instructions: `seberang kantor pos`;
- kilometer markers or access instructions tied to the destination.

Use the longest contiguous meaningful span. Start a new span after another
entity or a separator. Exclude delivery-time or handling requests that do not
describe location, such as `kirim sore hari`.

## 3. PII boundary

Recipient names, personal phone numbers, email addresses, account identifiers,
and order identifiers are not NER entities in this MVP. They must be detected
and redacted by the PII module before downstream processing when safe.

- `[NAME]` and `[PHONE]` placeholders receive `O` in address NER.
- Do not label a phone number as `NOMOR` or `KODEPOS`.
- Do not copy raw personal values into annotation examples, fixtures, logs, or
  issue comments.
- A public facility name used as the destination may be `DETAIL_LOKASI`; a
  recipient or staff name remains PII.

## 4. Boundary precedence

When a token could match multiple types, use this order of evidence:

1. explicit adjacent designator (`RT`, `Kec.`, `Kabupaten`, and similar);
2. structured source field with documented provenance;
3. valid parent-child administrative chain;
4. local textual context;
5. adjudication when evidence remains insufficient.

Do not use a plausible guess as gold. Lexical form alone is not enough for names
shared across roads and administrative levels.

Rules for common collisions:

| Collision | Rule |
|---|---|
| Road number vs order number | `NOMOR` only inside an address and with address evidence |
| Postal code vs arbitrary five digits | `KODEPOS` only in address context |
| Kelurahan vs kecamatan vs city | Prefer designator or structured hierarchy; otherwise adjudicate |
| Road vs landmark | Named traversable route is `JALAN`; reference point is `DETAIL_LOKASI` |
| Building number vs unit/floor | Road-facing number is `NOMOR`; unit/floor/block is `DETAIL_LOKASI` |
| Recipient/company vs destination venue | Recipient identity is PII; venue used to locate delivery is `DETAIL_LOKASI` |

## 5. Ambiguity and adjudication

Set an example to `needs_adjudication` when two reasonable labels remain after
applying the evidence order. Record:

- the ambiguous token span;
- candidate labels;
- available context and structured provenance;
- annotator choices and rationales;
- final adjudicated label or a decision to exclude the example;
- schema version used for the decision.

Annotators must not consult model predictions or sealed-test results during
adjudication. If a recurring ambiguity lacks a rule, update this document with a
new schema version before resuming annotation.

Examples:

- `Sukamaju, Cilodong, Depok` may be labeled using a trusted structured hierarchy.
- `Melati Indah, Bandung` without designators or provenance remains
  `needs_adjudication`; do not infer road, complex, or administrative level.
- A postal code conflicting with the named kelurahan is still labeled
  `KODEPOS`; record a hierarchy-conflict flag for the validator.

#### Rule clarification log

- 2026-08-14 (ALM-013 double annotation): a kecamatan or kabupaten/kota name
  sometimes appears twice in the same address -- once bare, with no
  designator, and again later with its proper designator (for example
  `...CIMERAK, PANGANDARAN, KEC CIMERAK, KAB. PANGANDARAN`). Decision
  (project owner, based on the human double-annotation review): label only
  the properly designated occurrence; leave the earlier bare, redundant
  repeat as `O` rather than double-labeling the same administrative unit
  twice. This also covers the case where the kecamatan and kabupaten/kota
  share the same base name (for example `Kecamatan Banjar` inside `Kota
  Banjar`) -- use the designator word to disambiguate which occurrence is
  which, never lexical similarity alone.

## 6. Positive, negative, and noisy examples

### Positive

```text
Jl. Merdeka No. 3, Kel. Padasuka, Kec. Cibeunying Kidul, Kota Bandung
```

This contains `JALAN`, `NOMOR`, `KELURAHAN`, `KECAMATAN`, and
`KOTA_KABUPATEN` spans.

### Abbreviation and typo

```text
Jln. Diponegoro No 5, Ds. Citarum, Kec. Bandung Wetan, Jabar 40115
Jaln Sudirman Nomer 10, Kelurahn Dago, Kecmatan Coblong, Jawa Brat 40135
```

Keep observed text and annotate its intended role when evidence is sufficient.
Do not correct it inside the gold input.

### Negative

```text
Nomor pesanan 40111 harap diproses
Kirim setelah pukul lima sore
```

All tokens are `O`: the first number is an order identifier, and the second
sentence contains a delivery-time instruction rather than location detail.

### PII-separated

```text
[NAME] [PHONE] Jl. Kebon Jeruk No. 9 Jakarta Barat DKI Jakarta 11530
```

The placeholders are `O`; address components retain their normal labels.

## 7. Canonical label order

Training and evaluation must import the canonical constants rather than
recreating label IDs:

| ID | Label |
|---:|---|
| 0 | `O` |
| 1 | `B-JALAN` |
| 2 | `I-JALAN` |
| 3 | `B-NOMOR` |
| 4 | `I-NOMOR` |
| 5 | `B-RT` |
| 6 | `I-RT` |
| 7 | `B-RW` |
| 8 | `I-RW` |
| 9 | `B-KELURAHAN` |
| 10 | `I-KELURAHAN` |
| 11 | `B-KECAMATAN` |
| 12 | `I-KECAMATAN` |
| 13 | `B-KOTA_KABUPATEN` |
| 14 | `I-KOTA_KABUPATEN` |
| 15 | `B-PROVINSI` |
| 16 | `I-PROVINSI` |
| 17 | `B-KODEPOS` |
| 18 | `I-KODEPOS` |
| 19 | `B-DETAIL_LOKASI` |
| 20 | `I-DETAIL_LOKASI` |

Changing entity order or semantics is a schema change. Update
`SCHEMA_VERSION`, this document, fixtures, dataset manifests, training config,
and model metadata together.

## 8. Annotator review procedure

1. Review 10–20 examples from `tests/fixtures/ner_gold_examples.json`.
2. The review may be performed jointly by the team or independently by multiple
   annotators. Record which method was used.
3. Compare entity type and exact boundaries against the written rules.
4. Record disagreements and rationale without consulting a model prediction.
5. Adjudicate every disagreement or mark it unresolved.
6. Update unclear rules, increment schema version if semantics change, and rerun
   automated tests.
7. Record reviewer group or pseudonymous IDs, date, result, and schema version.

The fixture contains automated candidate gold labels, but automated validation
does not replace documented human review.

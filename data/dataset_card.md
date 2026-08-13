# ALAMATIN base address benchmark — dataset card

- Dataset ID: `alamatin-base-address-benchmark-v0`
- Status: development smoke benchmark
- Card version: `1.0.0`
- NER schema: `1.0.0`
- Source catalog: `data/sources.json` version `1.5.0`

## Intended use

This artifact is a deterministic smoke benchmark for schema validation, parser
integration, and evaluator tests. It must not be used for model selection,
claims about Indonesian address quality, production thresholds, or the sealed
real-test result.

## Source composition

| `source_id` | Role | Included now? |
|---|---|---|
| `alamatin_synthetic_ner_review_v1` | Synthetic labeled base examples | Yes, as `tests/fixtures/ner_gold_examples.json` |
| `kemendagri_wilayah_2025` | Hierarchy validation and conflict construction | No benchmark rows; two Cirebon code resolutions are recorded for the local reference build |
| `open_data_jabar_postal_2023` | Jawa Barat hierarchy/postal reference | No benchmark rows; a locally supplied extract is used only in ignored reference artifacts |
| `kemendagri_master_village_2024` | Village hierarchy cross-check | No; API host access was unavailable during review |
| `bps_sig_code_relationship_2020` | BPS/Kemendagri/postal relationship cross-check | No; source remains `hold` |
| `kodepos_dev_rest_api` | Targeted or explicit province-wide internal postal validation | No; generated observations are ignored local evidence and are not part of this benchmark |
| `osm_geofabrik_indonesia_2026_07_01` | Future road/landmark candidates and corroboration | No; acquisition/transformation is a later governed step |
| `pos_indonesia_postcode_search` | Candidate postal-code authority | No; explicitly excluded while its catalog decision is `hold` |
| `alamatin_synthetic_train_v1` | Bulk NER train/validation/test corpus (ALM-010) | No; a separate corpus, not part of this 20-example smoke benchmark -- see [`docs/synthetic_generator.md`](../docs/synthetic_generator.md) |

The source IDs are stable join keys. Future manifests must use these exact IDs,
not publisher names or mutable URLs.

## Current data

The current fixture has 20 contributor-authored synthetic examples with tokens,
BIO labels or explicit adjudication candidates, review categories, and short
rationales. It contains no customer data, recipients, phone numbers, precise
household coordinates, or scraped marketplace records.

The examples exercise the label contract, including abbreviations, typos,
RT/RW, landmarks, ambiguity, conflicts, and PII-like tokens. Their locations
may resemble public place names so the examples read naturally; they are not
evidence that a delivery address or recipient exists.

## Collection and processing

Examples were authored synthetically for the NER schema review and stored as
UTF-8 JSON. Tests validate schema version, label ordering, unique IDs, BIO
transitions, and required review categories. No external source acquisition is
needed for the current fixture.

Before adding a derived public-data example:

1. acquire only a source whose catalog decision is `use`;
2. record its acquisition manifest and checksum outside Git;
3. apply the catalog's field allowlist, license, PII, attribution, and geographic
   controls;
4. have a reviewer establish that the resulting example is safe to commit; and
5. retain `source_id` and transformation provenance in the dataset manifest.

## Known limitations

- Twenty curated examples are small and intentionally non-representative.
- Synthetic text cannot estimate natural typo, omission, ambiguity, or regional
  distributions.
- The benchmark currently has no independently annotated real-address split.
- Kemendagri does not establish postal codes, and OSM coverage is uneven.
- No source currently approves a bulk national postal-code reference.

## Privacy, license, and access

The current synthetic fixture follows repository terms and is safe to track.
Downloaded public-source artifacts and generated datasets remain local under
ignored `data/raw/`, `data/interim/`, or `data/processed/` paths. The source
catalog, artifact policy, and sealed-test information boundary remain
authoritative if this card conflicts with a later approved decision.

## Maintenance

Data & Research owns source reviews. Any source update requires a new immutable
snapshot, checksums, an updated catalog review date, and a new derived dataset
version. Never silently replace a source or reuse an existing dataset ID for
changed content.

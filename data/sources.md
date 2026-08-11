# Public data source decisions

- Catalog version: `1.0.0`
- Review date: 2026-08-11
- Machine-readable catalog: [`sources.json`](sources.json)
- Acquisition command: `python scripts/acquire_sources.py list`

This register is the approval boundary for public data. A source with decision
`use` may be acquired only for its listed purposes and with its documented
controls. `hold` means no bulk acquisition, scraping, transformation, or use.
Approval of a source does not approve every field in that source.

## Coverage decision

| Required use | Approved `source_id` | Boundary |
|---|---|---|
| Administrative hierarchy | `kemendagri_wilayah_2025` | Authority for region codes/names after applying the 2025 amendment; not a postal-code authority |
| Roads and landmarks | `osm_geofabrik_indonesia_2026_07_01` | Gazetteer/corroborating data only; coverage varies and ODbL applies |
| Base address benchmark | `alamatin_synthetic_ner_review_v1` | Deterministic smoke benchmark only; no real-world or model-quality claim |

There is deliberately no approved bulk postal-code source yet. Pos Indonesia's
official search is recorded as `hold`; ALAMATIN must return unresolved when the
available approved evidence cannot establish a postal code.

## `kemendagri_wilayah_2025` — use

Purpose: canonical administrative hierarchy.

The base source is Kepmendagri 300.2.2-2138/2025 and its annex. The source must
be read together with Kepmendagri 300.2.2-2430/2025, which changes the placement
of four islands. The acquisition command downloads both documents and records a
SHA-256 for each; derived data is invalid unless the amendment step is recorded.

- Provenance: Kementerian Dalam Negeri, served through the BPK/JDIH regulation
  database.
- Version: base decision dated 25 April 2025 plus amendment dated 23 June 2025.
- Licensing decision: internal extraction is allowed from the public legal
  documents. Only metadata and acquisition instructions may be committed;
  redistribution of an extracted database needs a separate legal decision.
- PII decision: no person-level records are expected. Retain only code, name,
  level, and parent; discard population and unrelated fields.
- Quality checks: validate ten-digit hierarchy rules, unique codes, valid
  parents, amendment application, row counts, and a rendered-PDF spot sample.

## `osm_geofabrik_indonesia_2026_07_01` — use with obligations

Purpose: road names, place/landmark candidates, and corroborating address tags.

- Provenance: OpenStreetMap contributors; timestamped Geofabrik Indonesia
  extract produced 1 July 2026.
- License: ODbL 1.0. Attribution and share-alike/database obligations must be
  preserved for any distributed derived database.
- PII decision: use the public extract without contributor identity metadata.
  Allowlist only task-relevant tags; never use history extracts or unrelated
  contact/free-text fields.
- Geographic control: the extract includes East Timor, so every transformation
  must explicitly clip to Indonesia.
- Quality checks: verify the upstream MD5, record SHA-256, measure missing-name
  rates by region, detect conflicting tags, and sample every supported island
  group. OSM cannot silently override the Kemendagri hierarchy.

Required attribution in products using the data:

> Copyright OpenStreetMap contributors; data available under ODbL 1.0.

Link both "OpenStreetMap contributors" and ODbL disclosure to
<https://www.openstreetmap.org/copyright> where the medium permits.

## `alamatin_synthetic_ner_review_v1` — use

Purpose: base address smoke benchmark.

The current source is the 20-example synthetic fixture created for NER schema
review. It is safe for deterministic parser/evaluator smoke checks. It is not a
training corpus, representative sample, release benchmark, or sealed test.

- Version: schema `1.0.0`, introduced at commit `f045d2d`.
- Licensing decision: contributor-authored repository material.
- PII decision: synthetic only; additions must not copy customer or household
  addresses.
- Quality checks: schema version, stable IDs, BIO validity, label coverage, and
  explicit adjudication state.

## `pos_indonesia_postcode_search` — hold

The official service is useful for individual lookup, but no immutable bulk
snapshot or explicit bulk reuse/redistribution terms were identified during
this review. Do not scrape it or use it to generate a dataset. Move this source
to `use` only after Data & Research records terms/API permission, snapshotting,
PII review, and a reproducible acquisition path.

## Required provenance flow

1. Select only a `use` source from `sources.json`.
2. Acquire it with `scripts/acquire_sources.py` or verify its recorded local
   path. Downloads go to ignored `data/raw/<source_id>/` by default.
3. Keep the generated `acquisition-manifest.json` beside the raw artifacts; do
   not commit either one.
4. Every interim/processed dataset manifest must copy `source_id`, source
   snapshot, artifact SHA-256, transformation version, and applicable
   attribution.
5. Stop the pipeline when an amendment, license decision, PII review, checksum,
   or required parent record is missing.

## Rejected shortcuts

- Search-engine results, map screenshots, geocoder responses, and copied
  marketplace addresses are not datasets.
- Repository or Kaggle mirrors do not inherit a trustworthy license merely
  because their code has an open-source license.
- A plausible postal code is not a verified postal code.
- No raw PDF, PBF, transformed gazetteer, or address corpus belongs in Git.

# Public data source decisions

- Catalog version: `1.3.0`
- Review date: 2026-08-13
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
| Jawa Barat hierarchy and postal MVP | `open_data_jabar_postal_2023` | Internal non-commercial use; Kemendagri fields canonical, BPS spellings retained as aliases |
| Village master cross-check | `kemendagri_master_village_2024` | Administrative evidence only; resource access currently blocked by DNS resolution |
| BPS/postal relationship cross-check | `bps_sig_code_relationship_2020` | On hold pending stable artifact and reuse terms |
| Bounded postal conflict validation | `kodepos_dev_rest_api` | Internal validation only; selected village-code detail calls, local ignored output, no redistribution |
| Roads and landmarks | `osm_geofabrik_indonesia_2026_07_01` | Gazetteer/corroborating data only; coverage varies and ODbL applies |
| Base address benchmark | `alamatin_synthetic_ner_review_v1` | Deterministic smoke benchmark only; no real-world or model-quality claim |

The Open Data Jabar 2023 snapshot is approved as the restricted Jawa Barat MVP
postal source. It is not a national postal authority. Pos Indonesia's official
search remains `hold` for any new or general bulk use; ALAMATIN must return
unresolved when the approved evidence cannot establish a unique postal code.
A single dated, bounded, project-owner-approved exception was used to close
two already-open internal review passes on the existing Jawa Barat postal
rows — see `pos_indonesia_postcode_search` below and
`docs/postal-data-status-and-review-guide.md`. That exception does not reopen
this source for further bulk use.

## `open_data_jabar_postal_2023` — restricted use

Purpose: primary Jawa Barat hierarchy/postal mapping. The portal records dataset
ID `95037db4-04d0-4b5f-8799-4c0ca9abb460`, data year 2023, and modification on
16 December 2024. Current approval is internal and non-commercial; derived or
raw data must not be redistributed. The published CSV endpoint returned an HTTP
403 Cloudflare challenge on the review date, so no bypass or alternate mirror
was used.

Kemendagri province/district/village columns become canonical; the city parent
is derived from the Kemendagri district prefix because the portal defines its
city code as BPS. Different BPS spellings/codes become aliases or documented
exceptions. Every output row carries this source ID, snapshot, and artifact
SHA-256.

## `kemendagri_master_village_2024` — use as cross-check

Purpose: compare village code/name/parent relationships. Satu Data Indonesia
records dataset ID `90249796-6f43-41b1-8167-1877b92b5c89`, modified 16 August
2024, and warns that SDI principle fulfillment is still in progress. The API
host did not resolve on the review date. It cannot establish or override a
postal code.

## `bps_sig_code_relationship_2020` — hold

The BPS SIG page records relationship tables between BPS Wilkerstat,
Kemendagri, and older postal codes. No stable direct artifact and reuse terms
were recorded, so only metadata and synthetic contract tests are allowed. Any
future approved extract must be normalized and used as cross-check evidence,
never as a silent override.

## `kodepos_dev_rest_api` — internal validation

The credentialed REST API has separate targeted and explicit province-audit
modes. The targeted client accepts explicit conflict/gap codes, defaults to 25
requests, and enforces a hard 100-request ceiling. Both modes write only the
normalized hierarchy/postal fields to ignored `data/interim/` output. The API
key is read from `KODEPOS_API_KEY`; it is never a CLI argument, output field, or
committed configuration value.

The service is live and mutable, so each observation records the access date and
detail endpoint. Results are corroborating evidence: they may emit a documented
exception but never silently replace the canonical government-source value.
Kodepos.dev terms prohibit data resale or redistribution without written
permission, so generated observations remain local and cannot become a bulk
repository dataset.

An explicit full-Jawa-Barat audit may use the documented search pagination at
100 rows per page. It requires `--confirm-full-jabar`, checkpoints every page,
compares only administrative/postal fields, consumes service credits, and keeps
all API-derived output ignored and local.

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

### Documented exception — Section 2 and Section 3 spot-check (2026-08-11/12)

The standing decision above stays `hold`; `scripts/acquire_sources.py` still
refuses this `source_id` (see `tests/test_data_sources.py`). Separately, the
project owner approved a bounded, dated exception to close rows that were
already open in the Jawa Barat postal review, not a general bulk-acquisition
approval:

- Scope: two-source candidate corroboration ("Section 2") and remaining
  unresolved rows ("Section 3") of the existing postal review only.
- Method: a dedicated script, `scripts/fetch_pos_indonesia_candidates.py`,
  outside the generic `acquire_sources.py` path; 2-second delay between
  requests, 100-query batches, batch pauses, and a response cache to avoid
  repeat queries.
- Volume: 917 unique village-name queries across both passes.
- Output handling: only search-result observations (queried name, returned
  candidates, exact/no-match/multiple-match status) were kept, in
  `data/interim/postal-review/`, which is excluded from the public
  repository. A postal code is promoted into governed reference output only
  after human adjudication with recorded evidence — never a silent
  auto-accept of the raw search response.
- Full record: `data/sources.json` → `pos_indonesia_postcode_search` →
  `documented_exceptions`, and
  `docs/postal-data-status-and-review-guide.md`.

This exception does not change the standing `hold` decision. Any further or
different bulk use of this source needs its own new, separately dated and
scoped exception recorded here first.

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

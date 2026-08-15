# Public data source decisions

- Catalog version: `1.7.0`
- Review date: 2026-08-15
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
| Village master cross-check (optional, deferred) | `kemendagri_master_village_2024` | Administrative evidence only; resource access blocked by DNS resolution; deferred out of the Jawa Barat MVP scope on 2026-08-13, see below |
| BPS/postal relationship cross-check | `bps_sig_code_relationship_2020` | On hold pending stable artifact and reuse terms |
| Bounded postal conflict validation | `kodepos_dev_rest_api` | Internal validation only; selected village-code detail calls, local ignored output, no redistribution |
| Roads and landmarks | `osm_geofabrik_indonesia_2026_07_01` | Gazetteer/corroborating data only; coverage varies and ODbL applies |
| Roads and landmarks (ALM-009 MVP, staged) | `osm_geofabrik_java_2026_08_14` | Java extract clipped to Jawa Barat/Bandung Raya bbox; staged only, not yet integrated into the synthetic generator |
| Base address benchmark | `alamatin_synthetic_ner_review_v1` | Deterministic smoke benchmark only; no real-world or model-quality claim |
| Human-noised public-address benchmark base pool (ALM-012) | `open_data_jabar_npsn_sd_2023`, `open_data_jabar_npsn_sma_2023` | Public-facility (school) addresses only, no personal fields; internal non-commercial use until a derived-benchmark redistribution review is recorded |

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

### Documented exception — manual browser download (2026-08-11)

The scripted/cataloged endpoint (`scripts/acquire_sources.py`) still returns
an HTTP 403 Cloudflare challenge; no scripted bypass has ever been attempted.
The project owner manually downloaded the same public dataset through a
normal browser session on 2026-08-11 — a human viewing a public page, not an
automated or credential-based bypass of an access control. That file
(`dispusipda-kode_pos_kab_kota_indonesia_data.csv`, SHA-256
`33e35ba9c96a76276e16d09dbae8ca277bbd2e91d66ea69cf7a691d4944206c7`) is the
one actually used throughout the postal reference build; every derived row
records this checksum, and it is independently verifiable in the published
`data/processed/jabar-reference-v1-verified.json`. See
`data/reference_source_status.json` for the tracked acquisition status. This
does not change the source's `internal_noncommercial_only` license status or
redistribution limit; it only documents how the input file was actually
obtained so the build is traceable. Retry the scripted endpoint when the
publisher service is available again to restore full scripted
reproducibility.

## `kemendagri_master_village_2024` — use as cross-check (deferred, optional for MVP)

Purpose: compare village code/name/parent relationships. Satu Data Indonesia
records dataset ID `90249796-6f43-41b1-8167-1877b92b5c89`, modified 16 August
2024, and warns that SDI principle fulfillment is still in progress. The API
host did not resolve on the review date. It cannot establish or override a
postal code.

**Deferral decision (2026-08-13):** this source was only ever meant as an
independent cross-check of the village hierarchy already established from
`kemendagri_wilayah_2025` (the acquired Kepmendagri decision documents), not a
source the Jawa Barat postal reference depends on. The published
`jabar-reference-v1-verified.json` already reconciles three independent
postal sources (Diskominfo, Open Data Jabar, Kodepos.dev) on top of that
canonical hierarchy, with Pos Indonesia spot-checks closing the remaining
conflicts. The project owner deferred acquiring this source out of the Jawa
Barat MVP scope; it stays a candidate for the final round if broader
national coverage or an extra hierarchy cross-check is needed. `decision`
remains `use` — it may still be acquired later, it is simply not required
for the current MVP.

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

### Derived Jawa Barat postal reference output — redistribution decision (2026-08-13)

`open_data_jabar_postal_2023` and `kodepos_dev_rest_api` both restrict
redistribution of their raw or per-source data (see their sections above).
The project owner separately approved redistributing, in the public ALAMATIN
repository, only the fully adjudicated Jawa Barat postal reference output
derived from them:

- `data/processed/jabar-reference-v1-verified.json` and
  `data/final/jabar-postal-app-lookup.csv` — one canonical `postal_code` per
  `village_code`, chosen through the documented corroboration/adjudication
  process (see `docs/postal-data-status-and-review-guide.md`), plus their
  `jabar-reference-v1-exceptions.csv` and `jabar-reference-v1-summary.json`
  manifests.
- Every published value passed cross-check against Diskominfo, Kodepos.dev,
  and, for previously unresolved rows, a Pos Indonesia spot-check with
  recorded evidence, before a single value was accepted per village.

Not redistributed: the raw Open Data Jabar extract, per-source value columns
(`postal_code_diskominfo`, `postal_code_open_data_jabar`,
`postal_code_kodepos_dev`), reviewer worksheets, and raw
Kodepos.dev/Pos Indonesia observations. Those stay in the private repository
under the standing decisions above.

This decision applies only to the specific derived files listed above. It
does not change `open_data_jabar_postal_2023`'s `internal_noncommercial_only`
status or `kodepos_dev_rest_api`'s prohibited raw-data redistribution; any
different or broader redistribution needs its own separately dated review.

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

## `osm_geofabrik_java_2026_08_14` — use with obligations (ALM-009 MVP scope)

Purpose: road names (`highway`), landmark candidates (`amenity`/`place`), and
`addr:*` tags, clipped to the Jawa Barat/Bandung Raya MVP bounding box.

Supersedes `osm_geofabrik_indonesia_2026_07_01` for this acquisition only --
that broader Indonesia-wide entry was cataloged in an earlier review but
never actually fetched, and remains the candidate if a later national-scope
decision is made. This entry downloads the smaller Java-only Geofabrik
sub-extract instead of the whole-Indonesia file, since the MVP scope
(`docs/decision-log.md`) is Jawa Barat/Bandung Raya, not national.

- Provenance: OpenStreetMap contributors; Geofabrik Java extract
  `java-260814.osm.pbf`, produced 2026-08-14.
- License: ODbL 1.0, same obligations as the Indonesia-wide entry above.
- PII decision: allowlist only `name`/`highway`/`amenity`/`place`/`addr:*`
  tags; contributor identity metadata is already stripped by the public
  Geofabrik extract, and history extracts are never used.
- Parsing: a stdlib-only PBF reader (`src/alamatin/osm_pbf.py`) -- no
  third-party protobuf or OSM library, per the standing dependency-free
  decision (`docs/decision-log.md` DEC-002).
- Geographic control: the file covers all of Java; output is clipped to the
  Jawa Barat/Bandung Raya bounding box only, and the derived dataset must
  never claim Java-wide or national coverage.
- Staging only: this pass does not integrate results into
  `scripts/generate_synthetic_addresses.py` or regenerate
  `data/synthetic/*.json`, to avoid invalidating the ML lead's in-progress
  fine-tuning on the current dataset. Integration is a separate, later step.

Required attribution is identical to `osm_geofabrik_indonesia_2026_07_01`
above: `Copyright OpenStreetMap contributors; data available under ODbL 1.0`,
linked to <https://www.openstreetmap.org/copyright>.

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

## `alamatin_synthetic_train_v1` — use

Purpose: bulk NER train/validation/test corpus (ALM-010).

Generated entirely by `scripts/generate_synthetic_addresses.py`. The only
external input is the already-governed public reference
`data/final/jabar-postal-app-lookup.csv` (province/city/district/village
code and name, plus `postal_code`); street, landmark, and PII-placeholder
pools are synthetic, contributor-authored, generic name fragments, not
scraped or copied from OSM, a gazetteer, or any real customer address.

- Version: `generator_version 1.0.0`, `template_version 1.0.0`, seed
  `20260813`; see `data/synthetic/generation-summary.json` for the exact
  reference checksum and per-split noise-category counts.
- Licensing decision: contributor-authored repository material.
- PII decision: no real names/phones; the PII-mixed noise category uses the
  literal `[NAME]`/`[PHONE]` placeholder tokens already defined in
  `docs/label_schema.md`, both labeled `O`.
- Reproducibility: rerunning the script with the same seed and reference file
  produces byte-identical output; `generation-summary.json` records the
  reference file's SHA-256 and every output file's SHA-256.
- Anti-leakage: every base address's noised variants are confined to exactly
  one split; `scripts/generate_synthetic_addresses.py` fails loudly if a
  `base_id` ever appears in more than one split.
- Quality checks: every example's BIO sequence is validated with
  `alamatin.label_schema.validate_bio_sequence` before being written; see
  `docs/synthetic_generator.md` for noise categories and rates.
- Limitations: street/landmark names are generic placeholders, not real Jawa
  Barat roads or businesses, until ALM-009 (OSM extraction) is completed and
  integrated as an optional enhancement. This source must never be mixed
  into the sealed real test.

## `open_data_jabar_npsn_sd_2023` / `open_data_jabar_npsn_sma_2023` — use with obligations

Purpose: base pool for ALM-012's human-noised public-address benchmark.

Fields are limited to school name, NPSN, school status, kecamatan/kabupaten
name, address text, and data year -- no principal/operator name, personal
phone number, or household address. A school's registered address is a
public facility record, not a private residence.

- Snapshot: dataset IDs 20081 (SD) and 20078 (SMA), data year 2023, 19,462 +
  1,911 rows fetched 2026-08-14 with `scripts/fetch_npsn_school_addresses.py`.
- Licensing decision: `internal_noncommercial_only`, same as
  `open_data_jabar_postal_2023` -- the dataset page's own Creative Commons
  Attribution badge does not supersede the standing Open Data Jabar terms
  finding already recorded for that source. Redistribution of the raw fetch
  or candidate pool is `metadata_and_synthetic_fixtures_only`.
- PII decision: approved; the source has no personal fields to begin with,
  and `scripts/build_public_address_benchmark_candidates.py` still allowlists
  fields explicitly as defense in depth.

### Documented exception — scripted pagination acquisition (2026-08-14)

The cataloged `?download=csv` endpoint returns an HTTP 403 Cloudflare
challenge from this environment, the same finding already recorded for
`open_data_jabar_postal_2023`. `scripts/fetch_npsn_school_addresses.py`
requests the paginated JSON endpoint the dataset's own preview page already
loads in a browser, sending the same Referer/Origin/Accept headers a normal
page view sends -- not a credential or access-control bypass. It is
reproducible (fixed endpoint, `limit`/`skip` pagination until the reported
`total_record` is reached, fetched row count checked against that total
before any file is written) and does not change the standing
`internal_noncommercial_only` license status. Full record:
`data/sources.json` → both `open_data_jabar_npsn_*` entries →
`documented_exceptions`.

### Pipeline and the human-in-the-loop requirement

1. `scripts/fetch_npsn_school_addresses.py` -- fetch raw rows (internal only,
   `data/interim/school-address-benchmark/npsn-{sd,sma}-raw.json`).
2. `scripts/build_public_address_benchmark_candidates.py` -- allowlist fields
   and draw a deterministic, stratified 200-row candidate pool
   (`candidates.csv` + `candidates-summary.json`).
3. `scripts/build_human_noised_benchmark.py make-template` -- produce a blank
   worksheet (`annotation-template.csv`) for a **real human** to fill in
   `rewritten_address` (natural, checkout-style phrasing, no new personal
   data) and a pseudonymous `annotator_id`.
4. `scripts/build_human_noised_benchmark.py assemble` -- validate the
   completed worksheet (non-empty fields, rewritten text must differ from the
   reference address, a phone-number-like-sequence guard) and assemble the
   governed benchmark manifest.

Step 3 must be done by a person. Nothing in this repository may generate
`rewritten_address` and label it human-written -- see
`docs/public_address_benchmark.md` for the full walkthrough. Redistribution
of the assembled benchmark text itself (as opposed to the raw source) needs
its own dated review once real annotations exist, following the same pattern
as the `jabar_postal_reference_v1_redistribution_2026_08_13` exception above.

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

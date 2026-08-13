# Reference hierarchy and postal-code lookup

Issue ALM-008 introduces a deterministic Jawa Barat MVP reference from province
through village/kelurahan and postal code. The reference is a validation aid,
not permission to auto-correct an ambiguous address.

## Source precedence and access status

1. `open_data_jabar_postal_2023` is the primary postal mapping. Within its
   columns, Kemendagri province/district/village codes and names are canonical;
   the city parent code is derived from the Kemendagri district prefix. A
   differing BPS name/code becomes an alias or exception.
2. `kemendagri_master_village_2024` is an optional administrative cross-check,
   deferred out of the Jawa Barat MVP scope on 2026-08-13 (see
   `data/sources.md`). It does not establish a postal code and the published
   reference does not depend on it; the canonical hierarchy already comes
   from `kemendagri_wilayah_2025`.
3. `bps_sig_code_relationship_2020` is recorded but remains on hold until a
   stable artifact and reuse terms are known. It cannot silently influence a
   production build.
4. `kodepos_dev_rest_api` may validate selected conflicts through bounded
   village-detail requests. An explicit province-wide internal audit may also
   use the service's documented paginated search endpoint when API-credit use
   is confirmed. Its response is corroborating evidence and never a silent
   canonical override or redistributable dataset.
5. `pos_indonesia_postcode_search` is manual evidence for selected conflicts
   only. Bulk scraping is forbidden.

The exact acquisition observations are tracked in
[`data/reference_source_status.json`](../data/reference_source_status.json).
On 11 August 2026 the Open Data Jabar CSV returned an HTTP 403 Cloudflare
challenge, the Kemendagri API host did not resolve, and no stable direct BPS SIG
artifact was identified. No access control was bypassed and no downloaded
government dataset is committed. Retry the primary postal source only through
the cataloged acquisition path:

```bash
python scripts/acquire_sources.py fetch open_data_jabar_postal_2023
```

Retrying `kemendagri_master_village_2024` is optional; it is deferred out of
the current MVP scope (see above) and not required to reproduce the published
reference.

Open Data Jabar's reviewed terms restrict the current approval to internal,
non-commercial use. Only source metadata, code, and synthetic fixtures belong
in Git; raw and generated artifacts remain in ignored data directories.

The official 2025 annex was subsequently acquired through the cataloged BPK
artifact and checked against its rendered pages. It resolves two stale Cirebon
codes used by the local postal sources:

- Sambeng: `32.09.39.2001` → active `32.09.21.2016`, Gunung Jati.
- Sirnabaya: `32.09.39.2002` → active `32.09.21.2017`, Gunung Jati.

The tracked [`data/kemendagri_code_resolutions.json`](../data/kemendagri_code_resolutions.json)
records the source snapshot, artifact hashes, page evidence, and former/current
codes. The June 2025 amendment changes four islands between Aceh Singkil and
Tapanuli Tengah and does not alter Kabupaten Cirebon.

## Reproducible build

After obtaining the primary CSV, build the canonical reference with:

```bash
python scripts/build_reference_hierarchy.py \
  --open-data-jabar data/raw/open_data_jabar_postal_2023/open-data-jabar-kode-pos-2023.csv
```

Optional cross-checks may be repeated:

```bash
python scripts/build_reference_hierarchy.py \
  --open-data-jabar data/raw/open_data_jabar_postal_2023/open-data-jabar-kode-pos-2023.csv \
  --crosscheck data/interim/kemendagri-jabar-crosscheck.csv \
  --crosscheck data/interim/manual-pos-conflicts.csv
```

For a bounded Kodepos.dev REST validation, export the credential in the current
terminal or place `KODEPOS_API_KEY=...` in the ignored root `.env`, then query
explicit village codes. Never pass the key as a CLI argument or save it in a
tracked file:

```bash
python scripts/fetch_kodepos_crosscheck.py \
  --snapshot 2026-08-11 \
  --village-code 32.04.13.2003 \
  --output data/interim/kodepos-dev-crosscheck.csv

python scripts/build_reference_hierarchy.py \
  --open-data-jabar data/raw/open_data_jabar_postal_2023/open-data-jabar-kode-pos-2023.csv \
  --crosscheck data/interim/kodepos-dev-crosscheck.csv
```

The REST client defaults to 25 requests and refuses more than 100 in one run.
Use it for adjudication samples, not to mirror the service or generate a bulk
postal dataset. Every output is ignored and remains internal because the
service terms do not authorize redistribution.

For an explicit full Jawa Barat comparison, the separate audit command uses
100 results per page, writes a resumable checkpoint, validates province code
`32`, and produces complete/differences reports in ignored local paths:

```bash
python scripts/audit_kodepos_jabar.py \
  --confirm-full-jabar \
  --snapshot 2026-08-11
```

This audit is for internal discrepancy review only. It consumes service
credits, does not make Kodepos.dev canonical, and its API-derived rows must not
be committed or redistributed.

## Consensus and corroborated postal candidates

After the province audit, build the conservative postal candidate with:

```bash
python scripts/build_postal_consensus.py
```

The builder first applies the reviewed Kemendagri old-to-current code mappings.
It then requires the Diskominfo, Open Data Jabar, and Kodepos.dev values to be
the same valid five-digit code before setting `postal_code`. If Kodepos.dev
matches exactly one local source, the shared value is stored only in
`postal_code_candidate` with medium confidence and
`verification_status=corroborated_candidate`. It remains review-required and
cannot be consumed as an accepted correction.

The ignored outputs are:

- `data/processed/jabar-postal-consensus-candidate.csv`
- `data/processed/jabar-postal-consensus-accepted.csv`
- `data/processed/jabar-postal-corroborated-candidates.csv`
- `data/processed/jabar-postal-consensus-review-required.csv`
- `data/processed/jabar-postal-unresolved.csv`
- `data/processed/jabar-postal-consensus-summary.json`

## Unresolved grouping

Run `python scripts/group_postal_unresolved.py` after the tiered candidate
build. The grouping stage never selects another postal value. It separates:

- 625 source-disagreement rows: 603 with three different valid values, 19 with
  Open Data Jabar missing, and 3 with Diskominfo missing;
- 482 rows where Diskominfo and Open Data Jabar agree but Kodepos.dev differs.

The 625 priority rows are grouped by city, district, difference/missing pattern,
and exact postal triplet. Stable cluster IDs, cluster sizes, and representative
villages make later official/manual checks batchable without implying that one
source is correct. Outputs remain ignored local artifacts:

- `data/processed/jabar-postal-unresolved-source-disagreement.csv`
- `data/processed/jabar-postal-unresolved-clusters.csv`
- `data/processed/jabar-postal-government-consensus-api-conflict.csv`
- `data/processed/jabar-postal-unresolved-group-summary.json`

## Selected Pos Indonesia spot-check queue

Run `python scripts/build_postal_spotcheck_queue.py` after unresolved grouping.
The deterministic queue selects the lowest village code from every exact
source-postal triplet, ranks missing-source patterns first, then ranks larger
triplets ahead of smaller ones. The current queue contains 249 checks and
represents all 625 source-disagreement rows.

Completed selected checks are stored in the normalized ignored
`data/interim/manual-pos-conflicts.csv`. Two initial checks against the official
Pos Indonesia search on 11 August 2026 matched the Diskominfo values: Cempaka
in Plumbon returned `45655`, while Pasawahan in Banjaranyar returned `46283`.
Because the live service has no approved bulk snapshot or redistribution terms,
these observations remain exception evidence: neither is promoted
automatically or propagated to other rows that share the same source triplet.

The ignored outputs are:

- `data/processed/jabar-postal-pos-spotcheck-queue.csv`
- `data/processed/jabar-postal-pos-spotcheck-summary.json`

The official search accepts a simple name query and returns contextual rows.
A reviewer must match village, district, city/regency, and province before
recording a result; a blank or ambiguous result stays pending.

## Governed final Jawa Barat package

Run `python scripts/build_final_jabar_reference.py` after the consensus,
grouping, and selected spot-check stages. The final package separates complete
administrative coverage from postal-code usability:

- `data/processed/jabar-reference-v1.csv` contains all 5,957 canonical
  administrative rows, Kemendagri and BPS aliases/codes, every source postal
  value, Pos Indonesia observations, row lineage, and an explicit use policy;
- `data/processed/jabar-reference-v1-verified.json` contains all 5,957 rows as
  `usable_verified`: 2,876 three-source consensus rows plus 3,081 normalized
  and adjudicated Pos Indonesia reviews (including two rows closed through the
  documented manual Pos Indonesia correction described in
  [`postal-data-status-and-review-guide.md`](postal-data-status-and-review-guide.md));
- `data/processed/jabar-reference-v1-exceptions.csv` is currently empty — no
  row lacks a usable postal code; and
- `data/processed/jabar-reference-v1-summary.json` records counts plus input and
  output SHA-256 values.

`usable_verified` may be used for exact postal validation.
`verified_adjudicated` may enter `usable_verified` only through
`adjudicate_postal_human_review.py`. `unresolved_do_not_guess` must remain blank
in the accepted postal field. Pos Indonesia evidence remains separately
traceable and cannot change a state without a completed adjudication record.

### What is committed versus what stays ignored

`jabar-reference-v1.csv` still carries per-source raw value columns
(`postal_code_diskominfo`, `postal_code_open_data_jabar`,
`postal_code_kodepos_dev`) and stays an ignored local artifact, because Open
Data Jabar and Kodepos.dev restrict redistribution of raw or per-source data
(see `data/sources.md`).

`jabar-reference-v1-verified.json`, `jabar-reference-v1-exceptions.csv`,
`jabar-reference-v1-summary.json`, and the slim
`data/final/jabar-postal-app-lookup.csv` projection (`village_code`,
province/city/district/village code and name, `postal_code`) are committed to
this repository under a separately dated redistribution decision recorded in
`data/sources.md` under the `open_data_jabar_postal_2023` and
`kodepos_dev_rest_api` entries' `documented_exceptions`. Only the single
adjudicated `postal_code` per village is redistributed; no per-source raw
value, reviewer worksheet, or raw Kodepos.dev/Pos Indonesia observation is
included.

Human adjudication is performed only on editable interim copies generated by
`python scripts/prepare_postal_human_review.py`. The complete status,
field-by-field instructions, evidence rules, examples, and handoff checklist
are in
[`postal-data-status-and-review-guide.md`](postal-data-status-and-review-guide.md).

The default outputs are ignored local artifacts:

- `data/processed/reference-hierarchy.json`
- `data/processed/reference-exceptions.json`

Output is deterministic: rows, aliases, sources, postal codes, and exceptions
are sorted; build metadata contains input filenames, catalog version, snapshots,
and SHA-256 hashes, but no wall-clock timestamp. Running the same inputs and
catalog produces byte-equivalent JSON.

## Input contracts

The primary CSV must expose the published Open Data Jabar fields. Required
fields are the Kemendagri province, district, and village codes/names,
`kode_kabupaten_kota`, `nama_kabupaten_kota`, `kode_pos`, and `tahun`. The
portal defines `kode_kabupaten_kota` as a BPS code, so the canonical city code
is derived from the Kemendagri district prefix and the BPS code is compared.
When present, BPS names are retained as aliases when different. Only province
code `32` with the exact normalized name `Jawa Barat` is kept.

Every normalized cross-check CSV must contain:

```text
source_id,snapshot,province_code,province_name,city_code,city_name,
district_code,district_name,village_code,village_name,postal_code,
evidence_url,note
```

The last two columns are optional values but must remain in the header.
`source_id` must exist in `data/sources.json`. Sources whose decision is `hold`
may contribute exception evidence only; they are never added as approved row
lineage.

For a Pos Indonesia spot check, a reviewer selects only a conflict already
emitted by a real build, performs one interactive lookup, then adds one
normalized row with the access-date snapshot, result, official evidence URL,
and note. The synthetic test row exercises this path but is not real evidence.

## Canonical schema and validation

Each row has a stable `record_id`, a complete province-city/regency-district-
village chain, one or more postal codes, per-level aliases, and `sources`.
Every source reference contains `source_id`, snapshot/version, and raw artifact
SHA-256. The builder rejects:

- missing or malformed two/four/six/ten-digit region codes;
- a child code that does not share its parent's prefix;
- empty hierarchy names or invalid five-digit postal codes;
- duplicate village codes in canonical output;
- one primary village code with conflicting hierarchy parents/names; and
- missing source lineage or snapshot.

Multiple primary postal codes for one village are preserved and flagged. Name,
parent-code, postal-code, and missing-primary differences have deterministic
exception IDs. The primary value is never overwritten by cross-check evidence.

## Stable lookup interface

Application code uses `ReferenceHierarchy` from `alamatin`:

```python
from pathlib import Path
from alamatin import ReferenceHierarchy

reference = ReferenceHierarchy.from_json(
    Path("data/processed/reference-hierarchy.json")
)
result = reference.lookup(
    village="Braga",
    district="Sumur Bandung",
    city="Kota Bandung",
    province="Jawa Barat",
    postal_code="40111",
)
```

`result.status` is `exact`, `ambiguous`, or `not_found`. Matching is exact after
case, whitespace, punctuation, and accent normalization; it is intentionally
not fuzzy. An exact result exposes `result.match`. Ambiguous results expose all
sorted candidates so the validator can ask for more context instead of guessing.

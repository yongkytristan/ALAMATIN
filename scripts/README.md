# Scripts

Keep reproducible, non-interactive commands here. Scripts should accept explicit
inputs, record versions and seeds where relevant, avoid raw-PII logging, and fail
with actionable messages.

Run the repository policy check with:

```bash
python scripts/check_repository.py
```

Inspect the reviewed public-source catalog without downloading anything:

```bash
python scripts/acquire_sources.py list
python scripts/acquire_sources.py show kemendagri_wilayah_2025
python scripts/acquire_sources.py verify-local alamatin_synthetic_ner_review_v1
```

Acquisition is intentionally source-by-source. The following writes the source
and an `acquisition-manifest.json` to ignored `data/raw/<source_id>/`:

```bash
python scripts/acquire_sources.py fetch osm_geofabrik_indonesia_2026_07_01
```

There is no "fetch all" command: downloads may be large and each source has
different license, PII, checksum, and transformation controls. A `hold` or
`reject` source cannot be fetched by the script.

Build the Jawa Barat hierarchy/postal reference after acquiring the approved
Open Data Jabar CSV:

```bash
python scripts/build_reference_hierarchy.py \
  --open-data-jabar data/raw/open_data_jabar_postal_2023/open-data-jabar-kode-pos-2023.csv
```

Pass `--crosscheck PATH` repeatedly for normalized Kemendagri, BPS, or manual
Pos observations. See `docs/reference_hierarchy.md` for the CSV contract and
exception rules. Generated reference and exception JSON files go to ignored
`data/processed/` paths by default.

Use Kodepos.dev only for bounded validation of explicit village codes. The key
may be exported as `KODEPOS_API_KEY` or placed in the ignored root `.env` as
`KODEPOS_API_KEY=...`; the command never accepts or prints it:

```bash
python scripts/fetch_kodepos_crosscheck.py \
  --snapshot 2026-08-11 \
  --village-code 32.04.13.2003
```

The default output is the ignored
`data/interim/kodepos-dev-crosscheck.csv`. The command defaults to 25 requests
and has a hard ceiling of 100 to avoid accidental bulk acquisition or credit
usage.

An explicit province-wide internal audit uses the documented paginated search
endpoint (100 rows per page), saves a checkpoint after every page, and compares
the API result to both local Jawa Barat source views:

```bash
python scripts/audit_kodepos_jabar.py \
  --confirm-full-jabar \
  --snapshot 2026-08-11
```

The ignored outputs include the normalized API rows, a full comparison, an
all-differences CSV, a smaller priority-review CSV for unresolved/coverage
cases, and a deterministic JSON summary. This mode consumes API credits and
must not be used to commit or redistribute the third-party data.

After the full API audit, apply the reviewed Kemendagri 2025 code resolutions
and accept only postal values that are identical in all three source views:

```bash
python scripts/build_postal_consensus.py
```

The ignored `data/processed/` outputs contain all 5,957 canonicalized rows, the
accepted consensus subset, the medium-confidence corroborated-candidate subset,
the unresolved/review subsets, and a deterministic summary with source
checksums. A non-consensus row always has a blank accepted `postal_code`; a
two-source candidate is stored separately in `postal_code_candidate`.

Group the remaining unresolved rows by district, missing/difference pattern,
and exact three-source postal triplet with:

```bash
python scripts/group_postal_unresolved.py
```

The command writes a 625-row prioritized detail file, a district-cluster
summary, and a separate report for the 482 rows where both local government
sources agree but Kodepos.dev differs.

Build the bounded Pos Indonesia manual-review queue with:

```bash
python scripts/build_postal_spotcheck_queue.py
```

The queue selects one deterministic representative for each exact source-postal
triplet (249 checks representing 625 disagreement rows). Missing-source cases
rank first, followed by larger-impact triplets. Completed selected checks use
the normalized `data/interim/manual-pos-conflicts.csv` contract. Pos Indonesia
results remain exception evidence and are never automatically propagated to
the rest of a cluster.

Build the governed final Jawa Barat reference package with:

```bash
python scripts/build_final_jabar_reference.py
```

The full CSV keeps all 5,957 administrative rows, aliases, BPS relationship
codes, source values, manual Pos observations, provenance, and explicit use
policy. Only the 2,876 three-source consensus rows enter the verified lookup
JSON. The 1,974 review-only candidates and 1,107 unresolved rows remain in the
full table and a separate exception report; neither group is auto-correctable.

Prepare separate human-review worksheets without modifying reproducible build
outputs:

```bash
python scripts/prepare_postal_human_review.py
```

The command writes one editable interim CSV for the 1,974 two-source candidates
and another for the 1,107 unresolved rows. It attaches cluster context, safe
suggestions where available, existing selected Pos observations, and empty
reviewer/evidence fields. Follow
`docs/postal-data-status-and-review-guide.md` before assigning or completing
rows.

Build the local 10-sheet Excel source-review workbook with the full API audit:

```bash
python scripts/build_source_review_workbook.py \
  --kodepos data/interim/kodepos-dev-jabar.csv
```

The ignored output is `data/interim/jabar-source-review.xlsx`. It contains the
raw sources, normalized views, a non-canonical merged candidate, explicit
conflicts, and a quality summary. All cells are stored as Excel text so region
codes, BPS codes, and postal codes retain leading zeroes. When the processed
consensus artifact exists, tab `07_merged_candidate` uses that canonicalized,
consensus-only view.

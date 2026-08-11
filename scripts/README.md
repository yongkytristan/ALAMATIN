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

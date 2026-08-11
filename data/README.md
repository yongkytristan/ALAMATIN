# Data directory

Only metadata, schemas, tiny synthetic fixtures, and reproducible acquisition
instructions may be tracked here. Raw customer addresses, personal contact
details, restricted data, and downloaded source archives must not be committed.

Expected local-only stages are `raw/`, `private/`, `interim/`, and `processed/`;
their contents are ignored by Git. Every permitted source must have a stable
`source_id`, URL, access date, version or snapshot, license/terms decision,
redistribution decision, PII review, and transformation history.

The approval register is [`sources.json`](sources.json), with review rationale
in [`sources.md`](sources.md) and the current benchmark scope in
[`dataset_card.md`](dataset_card.md). List approved sources with:

```bash
python scripts/acquire_sources.py list
```

Downloading is always explicit and writes to ignored `data/raw/` by default.

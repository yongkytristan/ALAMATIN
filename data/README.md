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
The Jawa Barat reference hierarchy build, lookup contract, source-access status,
and exception policy are documented in
[`docs/reference_hierarchy.md`](../docs/reference_hierarchy.md).

For local human review, `python scripts/build_source_review_workbook.py`
combines the available source artifacts into the ignored
`interim/jabar-source-review.xlsx`. The workbook has sheets `00_manifest`
through `09_quality_summary`; it is an audit aid and is not the canonical final
dataset.

`python scripts/build_postal_consensus.py` applies the tracked Kemendagri code
resolutions and writes ignored `processed/jabar-postal-consensus-*.csv`
artifacts. Only a postal value shared by Diskominfo, Open Data Jabar, and the
Kodepos.dev audit is accepted. When Kodepos.dev matches exactly one local
source, the medium-confidence value is retained only in
`postal_code_candidate`; `postal_code` remains blank and review-required.

`python scripts/group_postal_unresolved.py` splits unresolved rows into the
625 source-disagreement cases that need priority verification and 482 cases
where the two local government-source views agree against Kodepos.dev. The
priority rows receive stable district/triplet cluster IDs in ignored
`processed/` reports.

`python scripts/build_postal_spotcheck_queue.py` selects one representative per
exact postal triplet for bounded manual review at Pos Indonesia. The ignored
queue covers all 249 triplets/625 priority rows, while completed observations
are recorded in the normalized ignored `interim/manual-pos-conflicts.csv`.
Manual observations are evidence only and are not automatically promoted or
propagated.

`python scripts/build_final_jabar_reference.py` produces the governed local
release package. `processed/jabar-reference-v1.csv` contains all administrative
rows and decision states; `jabar-reference-v1-verified.json` is the safe lookup
artifact containing only accepted three-source consensus rows; and
`jabar-reference-v1-exceptions.csv` preserves every non-verified row for later
review. All artifacts remain ignored because their source reuse boundaries do
not permit repository redistribution.

The current status, reviewer field definitions, decision matrix, evidence
requirements, examples, and handoff checklist are documented in
[`docs/postal-data-status-and-review-guide.md`](../docs/postal-data-status-and-review-guide.md).
Run `python scripts/prepare_postal_human_review.py` to create editable interim
copies; never edit generated `processed/` source artifacts directly.

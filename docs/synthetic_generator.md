# Synthetic address generator (ALM-010)

- Dataset ID: `alamatin-synthetic-train-v1`
- Generator version: `1.0.0`
- Template version: `1.0.0`
- NER schema: `1.0.0`
- Source catalog: `data/sources.json` version `1.5.0`, `source_id`
  `alamatin_synthetic_train_v1`
- Canonical implementation: `scripts/generate_synthetic_addresses.py`

## What this is

A reproducible generator that builds labeled Indonesian addresses for NER
train, validation, and synthetic-test splits. Every address is assembled from a
valid Jawa Barat administrative chain in the governed public reference
(`data/final/jabar-postal-app-lookup.csv`) plus synthetic street, landmark,
and PII-placeholder pools that are contributor-authored, not scraped or
copied from OSM, a gazetteer, or any real customer address. Labels are
produced directly from the pieces used to build each example, so annotation
is exact by construction -- there is no separate labeling step to get wrong.

This is not a training corpus that has been fine-tuned against yet, and it
does not replace the human-noised real-address benchmark (ALM-012), which
remains the credibility check for real-world generalization.

## Why no OSM data yet

ALM-009 (OSM road/landmark extraction) is an optional enhancement for this
issue, not a hard dependency -- see ALM-010's own `Depends on` list. Street
and landmark names in `v1` are generic, reusable placeholders (for example
`Jl. Mawar`, `depan Minimarket Indomaret`) rather than real Jawa Barat roads
or businesses. Once ALM-009 lands, the generator can swap in a real
street/landmark pool without changing the label contract, tokenization
rules, or output schema.

## Reproducing the dataset

```bash
python scripts/generate_synthetic_addresses.py \
  --seed 20260813 \
  --train-bases 1500 --val-bases 250 --test-bases 250 --variants-per-base 3 \
  --output-dir data/synthetic
```

The same seed, reference file, generator version, and template version always
produce byte-identical output; `data/synthetic/generation-summary.json`
records the reference file's SHA-256, every output file's SHA-256, the split
base/example counts, and the noise-category distribution per split. Increase
`--train-bases`/`--val-bases`/`--test-bases`/`--variants-per-base` to scale
volume for a real training run; nothing about the label contract changes.

## Output format

`data/synthetic/{train,val,test}.json`:

```json
{
  "schema_version": "1.0.0",
  "generator_version": "1.0.0",
  "template_version": "1.0.0",
  "label_order": ["O", "B-JALAN", "I-JALAN", "..."],
  "examples": [
    {"id": "SYN-0000042-01", "categories": ["abbreviation", "typo"], "tokens": ["..."], "labels": ["..."]}
  ]
}
```

`tokens`/`labels` follow `docs/label_schema.md` exactly (import
`alamatin.label_schema` rather than hand-writing label IDs). `categories`
lists which noise types were applied to that specific rendering -- it is the
per-example record backing the noise-distribution counts in
`generation-summary.json`.

## Noise categories

| Category | What it does |
|---|---|
| `abbreviation` | Non-canonical designator form (`Jl.`/`Jln`/`JL`, `Kel.`/`Desa`, `Kab`/`Kabupaten`, ...) |
| `case_upper` / `case_lower` / `case_title` | Whole-example casing transform, applied after tokenization so labels never shift |
| `typo` | One single-character swap/drop/double inside one word per example (never inside a postal code or RT/RW digit) |
| `separator` | A literal `,` inserted as a standalone `O` token between some components |
| `gang` | Access-route designator (`Gang`/`Gg.`) instead of a road designator |
| `missing_provinsi` / `missing_kodepos` / `missing_rt_rw` | The optional field was omitted entirely for this base address |
| `prefix_junk` | A leading `Alamat:`/`Kirim ke:`-style prefix token, labeled `O` |
| `instruksi` | A trailing delivery instruction (for example `kirim setelah jam 5 sore`), labeled `O` |
| `pii_mixed` | Literal `[NAME]`/`[PHONE]` placeholder tokens per `docs/label_schema.md` §3, both labeled `O` -- never a generated fake real-looking name |
| `admin_conflict` | The rendered postal code is deliberately perturbed from the chain's real value, while still being labeled `B-KODEPOS`; exercises the administrative validator's conflict detection downstream, per `docs/label_schema.md`'s note that a conflicting postal code is still `KODEPOS` |

Approximate base-level rates (see `generation-summary.json` for exact counts
per run): missing postal code ~40%, missing RT/RW ~30%, missing province
~50%, landmark included ~25%, block/complex detail ~20%, PII-mixed ~30%,
administrative conflict ~8% of addresses that include a postal code.

## Anti-leakage

Every generated address starts from a *base* (one administrative chain, one
street, one house number, one set of optional-field decisions). Several
noisy *variants* are rendered from the same base by re-applying independent
noise choices (abbreviation, casing, typo, order template, junk/instruction
text) -- so a model sees paraphrases of the same underlying address, not
identical duplicates. `build_dataset` assigns every variant of one `base_id`
to exactly one split; `scripts/generate_synthetic_addresses.py` raises a
`GeneratorError` and refuses to write output if a `base_id` is ever found in
more than one split. `tests/test_generate_synthetic_addresses.py` exercises
this check directly, including a deliberately leaking case that must fail.

## No raw private address

The generator never reads a raw or private address file. Its only external
input is `data/final/jabar-postal-app-lookup.csv` -- itself already reviewed
and published for public redistribution (see `data/sources.md`'s
`open_data_jabar_postal_2023`/`kodepos_dev_rest_api` documented exceptions).
Street, landmark, and name/phone placeholder pools live directly in
`scripts/generate_synthetic_addresses.py` as generic, reusable fragments.

## Known limitations

- Street and landmark names are generic placeholders until ALM-009 lands; they
  do not represent real Jawa Barat road/business density or naming patterns.
- Noise rates are hand-set approximations of the original execution plan's
  noise table, not measured from a real address corpus.
- This corpus must never be mixed into the sealed real test (ALM-014/ALM-035).

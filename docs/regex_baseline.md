# Regex/rule NER baseline (ALM-015)

- Baseline ID: `regex_rule_v1`
- Canonical implementation: `src/alamatin/regex_baseline.py`
- Runner: `scripts/run_regex_baseline.py`

## What this is

A deterministic, zero-learned-parameter NER tagger used as the floor
comparison point for the fine-tuned BERT model. It maps the same 10 entity
types from `docs/label_schema.md`, using only:

- designator words (`Jl.`/`Jln.`/`Gang`/`Kp.`/`Dusun` for `JALAN`,
  `No.`/`Nomor` for `NOMOR`, `RT`/`RW` markers, `Kel.`/`Desa`/`Ds.` for
  `KELURAHAN`, `Kec.` for `KECAMATAN`, `Kota`/`Kabupaten` for
  `KOTA_KABUPATEN`, `Provinsi` or the bare forms `Jawa Barat`/`Jabar`/`DKI
  Jakarta` for `PROVINSI`) and their documented typo variants;
- a 5-digit-token regex for `KODEPOS`;
- the kampung/dusun-as-`JALAN` rule from `docs/label_schema.md`'s
  rule-clarification log, for addresses with no formal road name at all.

**No rule here was derived from, or tuned against, any dataset's actual
answers.** Everything implemented is already written down in
`docs/label_schema.md`'s entity definitions, which exist independently of any
specific train/dev/test split -- satisfying ALM-015's "no gold/test
information embedded in the rules" requirement.

## Why it is deliberately weak in specific ways

Per `docs/label_schema.md` section 4: *"without a designator, require
structured evidence or an unambiguous hierarchy"* -- a rule baseline has
neither. It cannot recognize a bare kecamatan/kelurahan/kota name with no
adjacent designator word (for example `Cikuppa Lumbung` meaning
`KELURAHAN`+`KECAMATAN` with both designators omitted by a noise category).
It also never guesses `DETAIL_LOKASI` for text it cannot place, since
guessing an entity for undesignated text is exactly the "plausible guess as
gold" the schema forbids -- that text is left `O`. Both are real, expected
weaknesses of a rule baseline, not implementation bugs, and are exactly the
kind of gap ALM-018's fine-tuned model is expected to close.

A designator-opened span (`JALAN`, `KELURAHAN`, `KECAMATAN`,
`KOTA_KABUPATEN`, `PROVINSI`) is capped at a small maximum length (3-5
tokens, see `MAX_SPAN_LENGTH`) so that unrelated trailing text -- an
instruction, a stray word, anything with no further designator to stop it --
cannot be silently absorbed into the entity forever.

## Reproducing

```bash
python scripts/run_regex_baseline.py --dataset data/synthetic/val.json
python scripts/run_regex_baseline.py --dataset data/synthetic/test.json
python scripts/run_regex_baseline.py --dataset data/interim/evaluation-splits/real_dev.json
```

Fully deterministic -- the same dataset always produces the same report, no
seed needed. Reports are written to `data/interim/baselines/` (internal
only, since the `real_dev` report is derived from data that has no public
redistribution decision yet).

## Results (2026-08-15)

| Dataset | Precision | Recall | F1 |
|---|---:|---:|---:|
| `synthetic_dev` (`val.json`, 750 examples) | 0.947 | 0.844 | 0.892 |
| `synthetic_test` (`test.json`, 750 examples) | 0.958 | 0.851 | 0.902 |
| `real_dev` (70 examples) | 0.922 | 0.861 | 0.890 |

`RT`, `RW`, `NOMOR`, `KODEPOS`, and (once the bare-province fix landed)
`PROVINSI` all score at or near 1.0 F1 -- these are the entities regex
genuinely can nail. `KELURAHAN` and `KECAMATAN` recall sits around 0.55-0.65
because of the undesignated-name gap above; `DETAIL_LOKASI` recall is 0.0 by
design (never guessed). This spread -- strong on unambiguous
designator-marked fields, weak on undesignated or free-form ones -- is
exactly the profile a rule baseline should have, and is what makes it a
meaningful floor for the fine-tuned model to beat.

## Compatibility with the main evaluator

`run_regex_baseline.py` scores its own output with the same
`alamatin.evaluation_metrics.entity_metrics`/`entity_metrics_by_type`
functions ALM-018's evaluation will use, and records latency with the same
`latency_summary_ms` helper -- so its numbers are directly comparable to the
fine-tuned model's, not a bespoke metric.

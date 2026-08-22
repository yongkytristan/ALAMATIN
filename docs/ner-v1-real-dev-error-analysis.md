# ALM-019: NER v1 error analysis on `real_dev`

Status: completed on 2026-08-21 against private release `ner-v1.0.0`.

This report evaluates the frozen NER v1 checkpoint on the permitted 70-example
`real_dev` split. It does not read, enumerate, or score the sealed test. The only
sealed-test information used is the boundary-safe manifest already committed by
ALM-014: split ID `sealed_real_test_v1`, 130 examples, and content SHA-256
`ef3477f338a81526f7cd8173f5a18ab1dc9dd954f48a7273575964c3e8e767c6`.

## Reproduce the run

Download/extract the private `ner-v1.0.0` inference artifact as documented in
`docs/ner-v1.md`, then run:

```powershell
.\.venv-run\Scripts\python.exe scripts/analyze_ner_real_dev.py
python -m unittest discover -s tests -p "test_real_dev_error_analysis.py" -v
```

The analyzer refuses a path containing `sealed` and refuses any payload whose
declared split is not exactly `real_dev`. It records raw word-level predictions,
then applies the explicit `orphan_i_to_b_v1` decoder for canonical exact-span
scoring. All 16 repairs across 14 examples remain visible in the evidence; they
are not silently discarded. No logits or probability-like scores are stored.

## Result

| Measure | Result |
|---|---:|
| Examples | 70 |
| Exact-span TP / FP / FN | 198 / 113 / 76 |
| Micro precision | 0.6367 |
| Micro recall | 0.7226 |
| Micro F1 | 0.6769 |
| Critical exact match | 15 / 70 (0.2143) |
| Examples with any evaluated label error | 59 |
| Examples with invalid raw BIO | 14 |
| Raw orphan-I repairs | 16 |

The largest entity-level failures are `KELURAHAN` (50 FP; F1 0.1071), `JALAN`
(37 FN and 17 FP; F1 0.6029), and `DETAIL_LOKASI` (0 TP, 6 FP, 3 FN; F1 0).
`KOTA_KABUPATEN` is strongest at F1 0.9645. `PROVINSI` and `KODEPOS` are `NA`
because `real_dev` contains no gold or predicted spans for those types; they are
not reported as zero.

The timing values in `metrics.json` are diagnostic batched CPU forward times,
not the production-equivalent ALM-034 latency benchmark.

## Error matrix

Categories are multi-label, so counts do not sum to 59. They are derived from
input tokens, gold spans, and the governed source row—never from the prediction
being evaluated. `typo`/`conflict` use a conservative administrative-value
similarity rule, while `ambiguous_region` indicates multiple distinct gold
administrative values and remains a review signal rather than a claim that the
reference hierarchy has confirmed ambiguity.

| Category | Exposed examples | Error examples | Error rate | Critical failures | Severity |
|---|---:|---:|---:|---:|---|
| abbreviation | 61 | 55 | 0.9016 | 51 | P0 |
| typo | 31 | 26 | 0.8387 | 26 | P0 |
| RT/RW | 15 | 15 | 1.0000 | 11 | P0 |
| landmark | 2 | 2 | 1.0000 | 1 | P1 |
| missing field | 1 | 1 | 1.0000 | 1 | P1 |
| conflict | 4 | 3 | 0.7500 | 3 | P0 safety review |
| ambiguous region | 3 | 3 | 1.0000 | 3 | P0 safety review |
| other surface form | 1 | 0 | 0.0000 | 0 | not observed |

Exact case IDs, tokens, gold/predicted spans, BIO repairs, provenance, categories,
and severity are stored in `experiments/ner-v1-real-dev/error_cases.json`.

## Component separation

| Component | Status | Finding |
|---|---|---|
| Model | observed | 59 examples differ from gold after deterministic BIO repair. |
| Generator | hypothesis | The same 59 failures touch a modeled surface category, dominated by abbreviation and typo. This becomes a generator finding only if an ALM-020 controlled data ablation improves held-out `real_dev`; it is not presented as proven causality now. |
| Normalizer | not observable | Normalization was not executed in this NER-only run. No model error is relabelled as a normalizer error. |
| Validator | observed | 14 examples contain invalid raw BIO and require 16 orphan-I repairs. |
| Annotation | no defect confirmed | Gold provenance is retained. Forty-seven failed cases came from `automated_accepted` gold and are queued for spot review before any training-label change. |

This separation prevents a downstream stage that was never run from being given
a false zero and prevents a suspected generator gap from being stated as fact.

## Prioritized follow-up and traceability

The machine-readable `action_register.json` links every action to exact
`RD-<base_address_id>` evidence:

1. `ALM019-A01` (P0, validator): freeze a BIO decoder/validator before candidate
   comparison in ALM-020; traced to all 14 invalid-BIO cases.
2. `ALM019-A02` (P0, generator hypothesis): add synthetic surface variants and
   perform a controlled ALM-020 comparison; traced to the affected cases, with
   no sealed-test access.
3. `ALM019-A03` (P1, model): measure a targeted `DETAIL_LOKASI` candidate and
   retain it only if it does not harm critical fields.
4. `ALM019-A04` (P1, annotation review): spot-review affected
   `automated_accepted` labels before using them as corrections.

Each later change must cite an action ID and at least one case ID. A candidate
without those links is not considered “based on real_dev” for ALM-020.

## Explicitly deferred before the deadline

- Normalizer/administrative-reference failures are deferred to the integrated
  pipeline (ALM-028/ALM-034); this NER-only run cannot measure them.
- Genuine ambiguous-region resolution requires reference/validator evidence and
  the clarification contract (ALM-028); NER alone must not auto-resolve it.
- Rare landmark recall remains P1 unless a controlled ALM-020 candidate improves
  it without lowering critical-field performance.

## Evidence files

- `experiments/ner-v1-real-dev/predictions.json`: immutable raw/evaluated labels
  and repair ledger.
- `experiments/ner-v1-real-dev/metrics.json`: overall, per-type, critical exact
  match, invalid-BIO, environment, and diagnostic timing.
- `experiments/ner-v1-real-dev/error_cases.json`: per-case qualitative evidence.
- `experiments/ner-v1-real-dev/error_matrix.json`: category/component aggregates
  and sealed-boundary attestation.
- `experiments/ner-v1-real-dev/action_register.json`: severity/frequency-based
  decisions and deferred failure families.

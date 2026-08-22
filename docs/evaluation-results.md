# Sealed evaluation results (ALM-035)

Single authorized opening of `sealed_real_test_v1`, run once against release
candidate `rc-1.0.0`. Every number below comes from
[`experiments/sealed-evaluation/results.json`](../experiments/sealed-evaluation/results.json),
produced by `scripts/run_sealed_evaluation.py`. Nothing here was typed by hand.

## Provenance

| | |
|---|---|
| Split | `sealed_real_test_v1`, 130 examples |
| Dataset digest | `ef3477f338a81526…` (canonical JSON), plus all 130 per-item digests verified |
| System | contract `1.0.0`, extractor `regex-baseline-v1`, normalizer `normalizer-v1`, validator/reference `jabar-reference-v1`, gate `quality-gate-v1` |
| Release | tag `rc-1.0.0` |
| Openings used | 1 of 1 authorized |

The dataset and the per-example predictions stay in the custodian's restricted
location. Only aggregates are published; a test asserts no token, label, or
example id appears in the published file.

## Extraction quality

| Metric | Value |
|---|---|
| Entity precision | 0.9185 |
| Entity recall | 0.8791 |
| Entity F1 | **0.8984** |
| True / false positive / false negative | 451 / 40 / 62 |
| Critical exact match | **87 / 130 = 0.6692** |

Per annotation provenance, which is the closest thing this split has to a
difficulty axis:

| Subset | n | Entity F1 | Critical exact match |
|---|---|---|---|
| `double_annotated_agreed` | 17 | 0.9756 | 0.9412 |
| `automated_accepted` | 93 | 0.9004 | 0.6667 |
| `double_annotated_adjudicated` | 20 | 0.8404 | 0.4500 |

The ordering is the expected one: cases two annotators agreed on immediately are
easy, and cases that needed adjudication are hard. The gap is large — 0.94
against 0.45 critical exact match — so an aggregate figure hides a lot.

## End-to-end outcome, and why it is the important number

| Operational status | Count |
|---|---|
| `SIAP_DIPROSES` | **0** |
| `PERLU_KONFIRMASI` | 127 |
| `TIDAK_VALID` | 3 |

| Reason code | Count |
|---|---|
| `MISSING_ADMINISTRATIVE_FIELDS` | 123 |
| `KELURAHAN_TIDAK_DITEMUKAN` | 4 |
| `ADMINISTRATIVE_CONFLICT` | 2 |
| `KODEPOS_TIDAK_COCOK` | 1 |

**Not one sealed address reached `SIAP_DIPROSES`.** Entity F1 of 0.898 and this
result are both true and must be reported together: the extractor recovers most
spans, but on 123 of 130 real addresses it does not recover a *complete*
administrative chain, so the gate correctly asks for confirmation.

The cause is known and documented in `docs/integration.md`: the rule baseline
needs `Kel.` / `Kec.` style markers, and real addresses frequently omit them.
This is a property of the extractor that shipped, not of the gate.

The honest reading is that the release candidate is a **confirmation-requesting**
system on real input, not an auto-clearing one. Any claim that it clears
addresses without human review is contradicted by this run.

## Conflict and ambiguity detection

| | |
|---|---|
| True positive | 1 |
| False negative | 0 |
| Recall | 1.0 |

**This number must not be quoted as "100% recall".** The denominator is one.
Only a single sealed address is flagworthy under the definition used — the frozen
validator reports a conflict or ambiguity when run over the *gold* components —
so the measurement is consistent but carries essentially no statistical weight.
Reported because the protocol asks for it, with its denominator attached.

## False correction rate

| | |
|---|---|
| Incorrect proposals | 0 |
| Total proposals | **0** |
| Rate | undefined |

The rate is undefined because the release candidate **emitted no correction
proposals at all** on the sealed set. That is a fact about the system, not a
gap in the measurement: the pipeline applies deterministic normalization and
never calls `propose_correction`, so no semantic suggestion is ever produced.

Consequence for the product story: the "suggest a correction, human confirms"
path exists in the contract and in the UI, and it is exercised by tests and
fixtures, but the shipped pipeline does not generate suggestions. A demo that
shows a suggestion being confirmed is showing a fixture, not this build.

## Latency

| | |
|---|---|
| p50 | 0.0723 ms |
| p95 | 0.1129 ms |
| Samples | 130 |

Protocol: one timed call to `tag_tokens` per address, no warmup, single process,
`time.perf_counter`. This measures **extraction only**, not the full pipeline,
and was recorded on the run host — see `experiments/sealed-evaluation/results.json`
for the platform string. Full-pipeline and hardware-comparable latency belong to
ALM-036.

## Evaluator corrections

None. `evaluator_corrections` is an empty list.

The recorded policy: if an evaluator defect is found after this run, the
correction is documented together with **both** the original and the corrected
numbers. The better result is never selected quietly.

## What this run does not support

- No claim about delivery success, returns, or failed deliveries. Nothing here
  measures a downstream outcome.
- No claim about the fine-tuned model. `versions.model` is
  `regex-baseline-v1`; figures from the model evaluation describe a different
  system that is not served.
- No cross-approach comparison. Regex, libpostal, and the NER candidates have
  not been measured on one metric and one split yet — that is ALM-036.
- No generalization beyond Jawa Barat, and none beyond the 130 sealed
  addresses.

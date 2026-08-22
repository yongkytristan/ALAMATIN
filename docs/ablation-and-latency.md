# Ablation, latency, and failure cases (ALM-036)

Every number is read from
[`experiments/ablation/results.json`](../experiments/ablation/results.json),
produced by `scripts/run_ablation.py`. Nothing here was typed by hand.

**Split:** `data/synthetic/val.json`, 750 examples, digest recorded in the
artifact. The sealed set is deliberately not used — it is authorized for exactly
one opening, already spent on ALM-035.

**Evaluator:** `alamatin.evaluation_metrics` for every row. One evaluator is what
makes the rows comparable.

## Cross-approach comparison

Two of the four approaches cannot be executed in this repository. They are shown
with their recorded prior measurements and the reason, rather than omitted or
quietly folded into a column they did not earn.

| Approach | Entity F1 | Measured here | Note |
|---|---|---|---|
| libpostal v1 | 0.3701 | no | `postal` module not installed; recorded from `data/interim/baselines/libpostal-synthetic-dev.json`, same split |
| **regex baseline v1** (shipped) | **0.8923** | **yes** | this run |
| NER v1.0.0 | 0.9994 | no | weights are a 712 MB release asset; **selection split, not this file** |
| NER targeted v2 | 0.9995 | no | as above; not served by the release candidate |

The regex figure reproduces the previously recorded
`regex_rule_v1-synthetic_dev.json` value of 0.8923 exactly, which is a useful
check that the evaluator has not drifted.

**Interpretation limit that matters:** the two NER rows come from the selection
split, not from `val.json`, so they are *not* strictly comparable with the rows
above them. Treating 0.9995 against 0.8923 as a like-for-like margin would be
wrong. A genuine head-to-head needs the weights, and the release candidate does
not serve them.

## Stage ablation

The stages after extraction do not change spans, they change the decision, so
they are measured by whether a reference-backed verdict is reached.

| Stage | Metric | Value |
|---|---|---|
| A. extractor only | entity F1 | 0.8923 |
| A. extractor only | critical exact match | 0.3933 |
| B. extractor + validator | valid administrative chain | 26 / 750 = 0.0347 |
| C. extractor + normalizer + validator | valid administrative chain | 26 / 750 = **0.0347** |
| D. complete system | `SIAP_DIPROSES` / `PERLU_KONFIRMASI` / `TIDAK_VALID` | 26 / 618 / 106 |

### The normalizer contributes nothing to the decision on this split

`additional_valid_chains: 0`.

This is a real result, not a measurement failure, and the artifact records the
counts that make it interpretable: the normalizer applied **4,811 changes across
748 of 750 examples**, under three rules —
`designator_dictionary_v1` (2,489), `component_capitalization_v1` (1,444), and
`rt_rw_three_digit_v1` (878).

So the normalizer is working hard and changing almost every address, yet not one
additional address reaches a valid chain. The validator already tolerates the
surface variation the normalizer removes. Its contribution on this split is
presentational — a clean, canonical string for display and copying — not
decisional.

That is worth stating plainly rather than leaving a reader to assume the stage
earns its place in the decision path.

## Latency

Protocol: 50 warmup iterations, 3 timed repeats over all 750 examples,
`time.perf_counter`, nearest-rank percentiles, single process and single thread.

| Stage | p50 | p95 | p99 |
|---|---|---|---|
| extraction | 0.1027 | 0.1647 | 0.2034 ms |
| extraction + normalizer | 0.1709 | 0.2500 | 0.3477 ms |
| complete pipeline | 28.2479 | 34.4115 | 37.0990 ms |

Hardware: `Intel64 Family 6 Model 154 Stepping 3, GenuineIntel`, Windows, CPython
3.12 — the full platform string is in the artifact.

Stage figures are measured independently and are **not additive**: extraction is
re-run inside the normalizer measurement.

**The cost centre is the validator, not the model.** The complete pipeline is
roughly 275x slower than extraction because the administrative validator searches
the 5,957-row reference on every call. At 28.5 ms p50 this is comfortable for a
single-address review UI, but it is the number to attack first if throughput ever
matters, and it is not where an observer would guess.

## Failure cases

Four cases, each with a **distinct** missed/spurious signature. Selecting the
four worst-damaged examples would have printed one finding four times; the
selector deduplicates by signature.

All four come from the synthetic split, so the published text contains no real
address and no PII. A test asserts every published case is marked synthetic.

| Example | Missed critical | Spurious critical | Noise categories |
|---|---|---|---|
| `SYN-0001685-01` | JALAN, KECAMATAN, KELURAHAN | JALAN, KELURAHAN, KELURAHAN | abbreviation, case_title, separator |
| `SYN-0001735-02` | JALAN, KECAMATAN, KELURAHAN | JALAN, KECAMATAN, KELURAHAN | abbreviation, case_lower, missing_kodepos, missing_provinsi, separator |
| `SYN-0001525-00` | JALAN, KECAMATAN, KELURAHAN | JALAN, KELURAHAN | abbreviation, missing_kodepos, separator |
| `SYN-0001560-00` | JALAN, KECAMATAN, KELURAHAN | JALAN, KOTA_KABUPATEN | abbreviation, case_title, missing_provinsi, separator, typo |

The common thread is boundary placement rather than blindness: the extractor
finds *something* for JALAN, KELURAHAN, and KECAMATAN but sets the span edges
wrong, so the gold span is missed and a near-miss span is emitted. `abbreviation`
and `separator` appear in all four. This matches the sealed-run finding that
missing administrative context, not missing text, is what stops addresses from
clearing.

Full gold and predicted components for each case are in the artifact.

## What this does not support

- No claim about delivery outcomes. Nothing measured here touches one.
- No like-for-like NER-versus-baseline margin, for the reason given above.
- The synthetic split is **not** a proxy for real input, and notably not
  uniformly easier: entity F1 is close to the sealed run (0.892 against 0.898),
  but critical exact match is much lower (0.393 against 0.669), because the
  generator injects abbreviation, casing, and separator noise more aggressively
  than the sealed addresses exhibit. The sealed run stays the measurement of
  record for real input.
- Latency was measured on one machine, single-threaded, with no concurrency.

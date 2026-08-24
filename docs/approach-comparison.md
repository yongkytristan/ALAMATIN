# Head-to-head: which extraction approach is actually best on real addresses

Every number here is read from
[`experiments/comparison-real-dev/results.json`](../experiments/comparison-real-dev/results.json),
produced by `scripts/compare_approaches_real_dev.py`. Nothing was typed by hand.

## The question this answers, and the one it does not

The recorded figures for these approaches were produced at different times, by
different scripts, on different splits. Placing them side by side is not a
comparison — it is unrelated measurements in one table. The previous
cross-approach table in [`ablation-and-latency.md`](ablation-and-latency.md)
said so explicitly and refused to rank.

This document does rank, because three things are now held constant:

| Held constant | How |
|---|---|
| The split | `real_dev`, 70 real addresses. Every row's dataset digest is verified byte-identical (`21cabe85…`); a row measured on anything else is refused, not footnoted. |
| The metric code | Every row is recomputed from raw predicted BIO labels through `alamatin.evaluation_metrics`. No row inherits a number from its own artifact. |
| The treatment of gaps | An approach that cannot run reports `not_measured` with a reason, and never borrows a number from another split. |

**Why not the sealed set.** The sealed evaluation is a one-time protocol that
has already been opened (ALM-035). Running four approaches against it would
destroy the property that makes its number worth anything. `real_dev` is
designated comparison-only and never enters training or checkpoint selection,
which is exactly what a fair comparison needs.

## Result

Exact-span matching, micro-averaged. Critical EM is the share of addresses whose
*entire* set of critical spans is exactly right — the strictest measure here, and
the one closest to what the product actually needs.

**Ranked on the held-out half.** The rule baseline was tuned on the other 35
addresses (DEC-008), so a figure over all 70 would flatter it. The held-out 35
are the only addresses no approach in this table was tuned against.

| Approach | Entity F1 | Precision | Recall | Critical EM |
|---|---|---|---|---|
| **regex baseline v1.2** (shipped) | **0.9027** | 0.9280 | 0.8788 | **25/35 = 0.714** |
| NER targeted v2 | 0.8248 | 0.7958 | 0.8561 | 20/35 = 0.571 |
| NER v1.0.0 | 0.7046 | 0.6644 | 0.7500 | 8/35 = 0.229 |
| NER LoRA candidate | 0.6438 | 0.5875 | 0.7121 | 6/35 = 0.171 |
| libpostal v1 | not measured | — | — | — |

**The rule baseline wins, and not narrowly.** On data no approach was tuned
against it leads the best fine-tuned candidate by 0.0779 entity F1 and by 5
addresses of critical exact match, and it leads on precision and recall
simultaneously — so this is not a precision/recall trade being read as a win.

For continuity with the figures published before the v1.1 rules, the same
comparison over all 70 addresses is in the artifact under each row's top-level
`entity` block. Treat the regex row there as development performance, not an
estimate.

### The cross-check that makes this trustworthy

Each model row is recomputed here from raw predictions, then compared against
the `metrics.json` its original analysis script wrote months earlier. They agree
to twelve decimal places, and the regex row reproduces
`data/interim/baselines/regex_baseline_v1_1-real_dev.json` exactly. Tests enforce
both. So the ranking is not an artifact of new metric code.

## Where the gap comes from

Per-field F1. `*` marks a critical field. A dash means the split has no gold
spans of that type, so no approach can be scored on it.

| Field | regex v1.1 | NER targeted v2 | NER v1.0.0 | LoRA |
|---|---|---|---|---|
| \*JALAN | 0.853 | 0.762 | 0.603 | 0.504 |
| \*KELURAHAN | **0.667** | **0.091** | 0.107 | 0.063 |
| \*KECAMATAN | 0.932 | 0.863 | 0.745 | 0.743 |
| \*KOTA_KABUPATEN | 0.979 | 0.950 | 0.965 | 0.965 |
| \*NOMOR | 0.947 | 0.864 | 0.783 | 0.783 |
| RT | 0.957 | 0.563 | 0.545 | 0.857 |
| RW | 0.909 | 0.643 | 0.593 | 0.483 |
| DETAIL_LOKASI | — | 0.000 | 0.000 | 0.000 |
| \*KODEPOS | — | — | — | — |
| \*PROVINSI | — | — | — | — |

**The baseline leads on every field where any approach scores at all.**

`KELURAHAN` is where the decision is made: **0.667 against 0.091** — roughly
7 times better. That field is the one the administrative validator depends
on most, so an approach that cannot find it cannot clear an address regardless
of its headline F1.

A plausible explanation, offered as such and not as a measurement: the rule
baseline keys on explicit designators (`Kel.`, `Kec.`, `Jl.`), and the real_dev
addresses largely carry them, while the models were trained on synthetic text
from our own generator and appear to have learned that generator rather than a
more robust cue. Confirming that would need an error analysis stratified by
whether the designator is present, which this comparison does not do.

## Why 99% was never a real-world number

| Candidate | Synthetic-dev F1 | real_dev F1 | real_dev critical EM |
|---|---|---|---|
| NER v1.0.0 | 0.9994 | 0.6769 | 15/70 |
| NER targeted v2 | 0.9995 | 0.7832 | 37/70 |

Both models were trained on 4,500 + 3,000 examples from our generator and
evaluated on held-out output of that same generator. 0.9995 measures how
consistent the generator is, not how well the model reads addresses people
write. The drop from 0.9995 to 0.7832 on real text is the whole story, and it is
why no synthetic figure may be quoted as a capability claim.

Targeted v2 was still the right selection *among the models* — it beats v1.0.0
on real text by 0.106 F1 and 22 addresses, which is what its selection gate
required. It simply does not beat the rule baseline.

## libpostal: why it has no row

The `postal` Python binding needs the native libpostal library, which is not
installed in this environment and has no supported build on the Windows
development machine. The adapter deliberately refuses a deterministic fake
parser, because a stand-in would produce something that looks like a
measurement of libpostal and is not one.

Its recorded 0.3701 entity F1 is on **synthetic-dev**, a different split, so it
is not carried into the table above. For context only, and not as a real-data
result: that figure is the lowest of every approach measured anywhere, and the
documented reason is structural — libpostal's labels have no stable one-to-one
mapping to this schema (`suburb` is not `KELURAHAN`, `city_district` is not
`KECAMATAN`), and the adapter is forbidden from inventing one.

To fill the row: run `scripts/compare_approaches_real_dev.py` on a machine with
libpostal installed. The script detects the binding and fills the row
automatically, using the adapter's own entry point.

## What this changes, and what it does not

**It confirms the release-candidate choice.** Serving `regex-baseline-v1.2` was
previously justified on operational grounds — the checkpoint is a 712 MB release
asset outside both repositories, so a clean clone could not start with it. It is
now also the accuracy-preferred option on the only real-data comparison that
exists.

**It does not make the baseline good enough.** `KELURAHAN` at 0.667 and the
sealed run's `0 of 130` addresses reaching `SIAP_DIPROSES` are the same weakness
seen twice. The product's answer is human confirmation, not a claim of
correctness — see [`limitations.md`](limitations.md).

**Limits of this comparison, stated plainly:**

- **70 addresses.** Small enough that a handful of examples moves a per-field
  figure. The 0.112 overall F1 gap is wide relative to that noise; the per-field
  numbers for rare types are not.
- `KODEPOS` and `PROVINSI` have no gold spans in this split, so two critical
  fields are untested here.
- The models are scored from recorded predictions, not re-run. The split digest
  is verified, but the weights themselves are not re-executed.
- Latency is not compared: the model rows have no comparable timing, and in the
  full pipeline extraction is not the cost centre anyway — the validator is, by
  roughly 275x. See [`ablation-and-latency.md`](ablation-and-latency.md).
- One split, one point in time. This is not evidence about Indonesian addresses
  in general.

## Reproduce

```bash
python scripts/compare_approaches_real_dev.py
python -m unittest discover -s tests -p test_approach_comparison.py
```

Requires the governed `real_dev` split, whose row-level content is not
redistributed; see [`../data/sources.md`](../data/sources.md).

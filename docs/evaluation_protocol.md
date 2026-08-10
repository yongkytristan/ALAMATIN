# ALAMATIN evaluation protocol

- Protocol version: `1.0.0`
- NER schema: `1.0.0`
- Canonical metric implementation: `src/alamatin/evaluation_metrics.py`
- Applies to: development evaluation, frozen release evaluation, and the one-time
  sealed real test

This document fixes the metrics, analysis units, slicing rules, and sealed-test
procedure before main model training. Metric targets are release decisions owned
by later evaluation issues; they must not be selected after inspecting sealed-test
results.

## 1. Evaluation records and analysis units

One record is one complete address example with an opaque `example_id`. Its gold
data may contain:

- a token sequence and BIO labels using the canonical NER schema;
- address-level `has_administrative_conflict` and `is_ambiguous` booleans;
- zero or more expected correction proposals and their canonical values;
- one or more noise-category labels;
- provenance, split, consent, and annotation metadata kept outside model input.

An entity span is the tuple `(entity_type, start_token, end_token_exclusive)`.
Entity metrics use spans; conflict and ambiguity recall use address examples;
critical exact match uses address examples; false correction rate uses emitted
correction proposals; latency uses one end-to-end address inference.

Before scoring, the evaluator must reject duplicate IDs, unequal token/label
lengths, invalid BIO transitions, unknown labels, missing required gold fields,
and records whose manifest does not match the selected split. An invalid record
is an evaluation error, not a model error and not a silently skipped row.

## 2. NER entity precision, recall, and F1

Across all examples, compare the set of predicted spans with the set of gold
spans. A true positive has exactly the same entity type, start token, and
exclusive end token. Then:

```text
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2 * precision * recall / (precision + recall)
```

The headline NER score is micro F1: sum TP, FP, and FN over all entity types and
examples before applying the formulas. Also report precision, recall, and F1 for
each canonical entity type. Macro averages, if shown, are secondary and must be
labelled as such.

A boundary overlap, wrong entity type, split entity, or merged entity receives
no partial credit. The unmatched prediction counts as FP and the unmatched gold
span counts as FN. Token accuracy is not an NER success metric.

If a denominator is zero, report the metric as `NA` with its counts; never
convert an undefined value to zero. F1 is `NA` when precision or recall is
undefined. F1 is `0` when both are defined as zero.

## 3. Critical exact match

Critical types are `JALAN`, `NOMOR`, `KELURAHAN`, `KECAMATAN`,
`KOTA_KABUPATEN`, `PROVINSI`, and `KODEPOS`. For every evaluated address,
filter gold and predicted spans to these types. The address passes only when the
two complete sets are identical. Any missing, extra, mistyped, or boundary-
mismatched critical span fails the address.

```text
critical exact match = passing addresses / all evaluated addresses
```

All addresses are included. An address with no gold critical span passes only
when the model also emits no critical span. `RT`, `RW`, and `DETAIL_LOKASI` are
reported through normal entity metrics but do not affect this exact-match score.

## 4. Safety metrics

### Administrative-conflict recall

A gold-positive address has a verified inconsistency between its stated
administrative components, postal code, or reference hierarchy. A predicted
positive means the system explicitly flags that inconsistency instead of
silently accepting or correcting it.

```text
conflict recall = correctly flagged gold conflicts / all gold conflicts
```

Report TP and FN. If there are no gold conflicts, report `NA`.

### Ambiguity recall

A gold-positive address has two or more plausible interpretations after the
documented evidence rules and therefore requires clarification. A predicted
positive means the system explicitly returns an ambiguity/clarification state.

```text
ambiguity recall = correctly flagged gold ambiguities / all gold ambiguities
```

Report TP and FN. If there are no gold ambiguities, report `NA`. Do not count a
generic low-confidence response unless the output explicitly requests or marks
clarification according to the frozen output contract.

### False correction rate

A proposal is any user-visible replacement of an observed component with a
different value. Compare each proposal to the adjudicated canonical correction
after applying only the frozen comparison normalization. A proposal is false if
its target field or canonical value is wrong, unsupported, or should have been
left unresolved.

```text
false correction rate = false proposals / all emitted proposals
```

Report numerator and denominator. If the system emits no proposals, report
`NA`. An address may contribute multiple proposals. Additionally report the
count of false corrections that bypassed confirmation as
`unsafe_auto_correction_count`; it is not folded into a different denominator.

## 5. CPU latency p50 and p95

Measure wall-clock elapsed time with a monotonic high-resolution clock around
the entire single-address pipeline: preprocessing, NER, normalization,
reference lookup, validation, and response assembly. Exclude process startup,
model loading, benchmark harness I/O, and documented warm-up calls.

- Run batch size 1, one process, and one inference thread unless the release
  configuration explicitly requires otherwise.
- Use the frozen release artifact and production-equivalent CPU settings.
- Collect at least 100 measured observations for the release latency benchmark.
- Compute p50 and p95 with nearest rank: sort `N` values and select rank
  `ceil(p / 100 * N)`, using one-based ranks.
- Report milliseconds, `N`, warm-up count, CPU model, cores made available, RAM,
  operating system, runtime/library versions, thread variables, input-length
  distribution, and benchmark commit/config hashes.

Use the fixed non-sealed latency corpus during iteration. During the one-time
sealed run, each sealed address is timed once as part of normal inference; do
not replay sealed inputs to optimize latency. Sealed latency is descriptive if
fewer than 100 observations are available.

## 6. Noise-category evaluation

Every example has one or more labels from this fixed taxonomy:

| Category | Definition |
|---|---|
| `clean` | No intentionally identified noise |
| `typo` | Character insertion, deletion, substitution, or transposition |
| `abbreviation` | Shortened or nonstandard component form |
| `capitalization` | Missing, excessive, or inconsistent capitalization |
| `punctuation` | Missing, extra, or inconsistent separators/punctuation |
| `reordered_components` | Components appear in a noncanonical order |
| `missing_field` | One or more expected address components are absent |
| `rt_rw` | RT/RW notation or separator variation is central to the example |
| `gang_landmark` | Alley, landmark, building, or access-detail expression |
| `pii_mixed` | Address is mixed with recipient or contact PII |
| `administrative_conflict` | Components disagree with the verified hierarchy |
| `ambiguous_region` | Administrative interpretation remains genuinely ambiguous |
| `long_input` | Token count is at or above the frozen corpus p95 threshold |

Recompute every applicable metric on each category slice. A multi-label example
contributes in full to every matching slice; it is not divided or assigned to a
single category. Report slice size, entity counts, and positive denominators for
recall metrics. A zero-size slice is `NA`. Report the overall result separately;
do not average slice scores into it. The dataset manifest must store the frozen
taxonomy version and the `long_input` token threshold.

## 7. Development splits and information boundary

Training code and the ML & Evaluation Lead may access only training splits,
synthetic development/test data, and `real_dev`. The final
`sealed_real_test` inputs, gold labels, metadata that reveals content, and
per-example results are held by the **Sealed Test Custodian**, assigned to the
Data & Research Lead. The custodian must not also be the ML & Evaluation Lead or
participate in model/rule selection.

If those roles map to the same person, the team must assign another named member
as custodian before dataset sealing. Until that assignment is recorded, the
sealed split cannot be created or opened. Access changes and downloads must be
logged.

Before opening the sealed test, the ML & Evaluation Lead may receive only the
opaque split ID, example count, schema/taxonomy versions, creation timestamp,
and SHA-256 manifest hash. No examples, label distribution, noise-slice counts,
or qualitative hints may cross the information boundary.

## 8. Manifest and freeze package

Serialize manifests as UTF-8 canonical JSON with keys sorted, no insignificant
whitespace, no NaN/Infinity, and arrays retained in declared order. Compute
SHA-256 over those exact bytes. The sealed manifest contains at least:

- opaque dataset/split version and ordered example IDs;
- content hash for each immutable input and gold artifact;
- record count, schema version, taxonomy version, and creation timestamp;
- custodian role/identifier and access-control location;
- annotation/adjudication version without raw PII.

The custodian publishes the manifest hash before system freeze and verifies it
immediately before evaluation. Raw or personally identifying data must not be
committed to Git.

Issue ALM-034 freezes a release package containing:

- Git commit and release tag;
- model artifact/checkpoint checksum;
- inference, tokenizer, normalization, and threshold configuration checksums;
- administrative-reference version/checksum;
- NER schema, output-contract, evaluator, and metric-protocol versions;
- dependency lock and runtime/container checksum;
- benchmark hardware/thread configuration and random seeds.

Any changed item creates a different system. The team records approval and the
freeze timestamp before authorizing the custodian to open the test.

## 9. One-time sealed-test procedure

1. The team approves the ALM-034 freeze record. The custodian confirms that no
   sealed content has been disclosed and verifies all dataset hashes.
2. In a clean environment, the custodian checks out only the frozen package,
   verifies every artifact hash, disables network-dependent mutation, and
   records the environment.
3. The custodian runs the frozen pipeline exactly once over each sealed address,
   producing immutable predictions, per-address timings, aggregate metrics, and
   noise-slice metrics. The ML lead does not inspect inputs during the run.
4. The custodian hashes and stores raw predictions, evaluator output, logs, and
   the final report in a restricted evidence location. Only redacted aggregate
   results are copied into the repository.
5. The team records the run timestamp, operator, frozen-system ID, sealed
   manifest hash, output hashes, metric counts/denominators, `NA` values,
   environment, and any incidents. This is the official sealed result.

After step 3 begins, sealed results must not select a model, threshold, rule, or
reference snapshot. A later system change retains the original result as the
official competition result. Any rerun is labelled `post-sealed`, reports the
new system hash and reason, and is non-comparable/non-selection evidence unless
the competition authority explicitly authorizes otherwise.

The only internal rerun exception is a demonstrated evaluator or infrastructure
failure. It requires a written incident, team approval, proof that model, rules,
configuration, references, and inputs did not change, and publication of both
old and corrected results. A disappointing metric is never an evaluator failure.

## 10. Required report structure

Every evaluation report must include:

1. protocol, schema, dataset manifest, system, evaluator, and reference hashes;
2. split name, total examples, exclusions/errors (normally zero), and noise-slice
   sizes;
3. entity micro counts/metrics and per-type counts/metrics;
4. critical exact-match numerator/denominator;
5. conflict recall and ambiguity recall TP/FN counts;
6. false-correction numerator/denominator and unsafe-auto-correction count;
7. CPU p50/p95 metadata and observations count;
8. every `NA` with its zero denominator;
9. immutable prediction/report/log hashes and incident or rerun status.

The executable reference tests demonstrate exact-span treatment, critical-set
matching, zero-denominator handling, nearest-rank percentiles, and stable
manifest hashing. Implementations in training or reporting code must match these
tests rather than restating formulas independently.

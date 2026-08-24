# Release candidate freeze (ALM-034)

The release candidate is defined by
[`experiments/release-candidate/manifest.json`](../experiments/release-candidate/manifest.json),
not by prose. Every component that can change a result is recorded there with
its SHA-256.

```bash
python scripts/build_release_manifest.py --verify
```

The freeze has teeth: appending a single comment to a frozen file makes
`--verify` report drift and fails `tests/test_release_candidate.py`. That was
checked, not assumed.

## What is frozen

Sixteen files. Anything not listed must not be able to change an answer — that
is what makes the freeze meaningful, and a test asserts the whole decision path
is covered.

| File | SHA-256 (first 16) | Bytes |
|---|---|---|
| `src/alamatin/regex_baseline.py` | `484c02269e826328...` | 9,295 |
| `src/alamatin/tokenizer.py` | `7b3a98adb14406a8...` | 811 |
| `src/alamatin/label_schema.py` | `a7dc10f9d659d276...` | 1,491 |
| `src/alamatin/address_normalizer.py` | `388e691d6f65db35...` | 12,045 |
| `src/alamatin/reference_hierarchy.py` | `f8ea46fc6bf599e6...` | 12,930 |
| `src/alamatin/administrative_validator.py` | `476442b319e9b506...` | 10,597 |
| `src/alamatin/quality_gate.py` | `34c7ec90eec75074...` | 12,276 |
| `src/alamatin/pii.py` | `c5a04010b458a601...` | 10,312 |
| `src/alamatin/pipeline.py` | `a2bd60275a3c0738...` | 14,171 |
| `src/alamatin/output_contract.py` | `1534739a8bb21a5b...` | 11,736 |
| `src/alamatin/api.py` | `f65e984c08397a6d...` | 14,813 |
| `src/alamatin/service.py` | `b43f2ee1e012d0eb...` | 4,576 |
| `src/alamatin/geocoding.py` | `ecf6d3b12d020338...` | 10,424 |
| `contracts/address-api.v1.schema.json` | `6a1aba697812e6e9...` | 12,268 |
| `data/processed/jabar-reference-v1-verified.json` | `855ec337f3a56603...` | 8,219,958 |
| `requirements.lock` | `cb402d202ee71ebf...` | 2,352 |

## Declared versions

Every one appears in the `versions` block of an API response, so a result is
traceable to the configuration that produced it.

| Component | Version |
|---|---|
| Output contract | `1.0.0` |
| Extractor | `regex-baseline-v1.2` |
| Normalizer | `normalizer-v1` |
| Validator | `jabar-reference-v1` |
| Reference data | `jabar-reference-v1` |
| Quality gate | `quality-gate-v1` |

## Decision rules

Recorded as data in the manifest, not as prose: the ten entity types, the five
critical validation fields, the three operational statuses, the two severities,
the six reason codes, and the status precedence.

`thresholds` is explicitly `null`. **No score, threshold, or probability
participates in the operational status.** It is recorded so a reader does not go
looking for one, and so a future change that introduces one is visible as drift.

## Model checkpoint

`served_in_release_candidate: false`. The runtime extractor is
`regex-baseline-v1.2`, which lives in the repository. The fine-tuned candidate
`ner-targeted-v2` is a 712 MB release asset recorded in
`experiments/ner-final-candidate/release_manifest.json` with its SHA-256; it is
not tracked in this repository and is not served.

`versions.model` reports the extractor that actually ran, so no response claims a
model that did not. Any accuracy figure quoted from the model evaluation
describes that model, not this release candidate.

## The sealed evaluation describes the previous extractor

The sealed run (ALM-035) was executed against `regex-baseline-v1`. The release
candidate now serves `regex-baseline-v1.2`, whose JALAN span rules changed after
that run. So:

- Every figure in [`evaluation-results.md`](evaluation-results.md) --
  entity F1 `0.8984`, critical exact match `87/130`, `0 of 130` reaching
  `SIAP_DIPROSES` -- describes `v1`, not what is served today.
- The sealed set is **not** re-run to resynchronise them. It is authorised for
  one opening, already spent, and a second opening would destroy the property
  that makes its number worth quoting. A stale-but-honest number beats a fresh
  number with no guarantee behind it.
- The held-out estimate for `v1.1` is
  [`approach-comparison.md`](approach-comparison.md): entity F1 `0.9027` on 35
  real addresses no rule was tuned against.

Recorded as `DEC-008` in [`decision-log.md`](decision-log.md).

## P1 features: all out

The frozen scope forbids a P1 implementation entering the release candidate. A
test asserts the manifest lists none as included.

| Feature | In RC | Why |
|---|---|---|
| ALM-029 consent-gated geocoding | no | implemented but disabled; no provider configured, so no external call is possible |
| ALM-030 map confirmation | no | not implemented |
| ALM-031 batch CSV | no | contract shape exists; endpoint returns `501 FEATURE_NOT_ENABLED` |
| ALM-016 libpostal comparison | no | evidence only, not a runtime dependency |
| ALM-009 OSM extraction | no | evidence only, not a runtime dependency |

## real_dev verification and critical errors

The `real_dev` split is governed and its row-level content is not redistributed
under `data/sources.md`. What is published here:

- `experiments/ner-v1-real-dev/`, `experiments/ner-targeted-v2-real-dev/`, and
  `experiments/ner-lora-kevin-real-dev/` carry `metrics.json`,
  `error_matrix.json`, `predictions.json`, and `action_register.json`.
- `experiments/ner-final-candidate/comparison.json` records the pre-frozen
  selection gates and the deltas that selected `ner-targeted-v2`.
- Per-example `error_cases.json` files are **withheld**: they contain verbatim
  address spans from the governed school benchmark.

Those artefacts describe the fine-tuned candidates. **The release candidate runs
the rule baseline**. Its aggregate comparison against the candidate approaches
is published in `experiments/comparison-real-dev/results.json` and documented in
`docs/approach-comparison.md`. Row-level governed inputs remain withheld.

## Sealed test

- Authorized openings: **1**
- Opened: **yes, once after the release candidate was frozen**

The immutable result is published in
`experiments/sealed-evaluation/results.json`. It records `openings_used: 1` and
the frozen system identifiers used for the run.

The authorization and the no-tuning declaration are recorded in the manifest with
their provenance: given on the project owner's instruction, with per-member
confirmations from the other collaborators not recorded. That is stated rather
than implied so the record can be audited.

The declaration: no model, rule, threshold, or reference change may be made in
response to the sealed result. If the evaluator itself is found to be wrong, the
correction is documented and **both** runs are reported; the better number is
never quietly selected.

## Release tag

The manifest's `built_from_commit` is the parent of the commit that stores it — a
file cannot contain the hash of the commit that adds it. Identity is established
by the per-file digests, which are stable.

The durable pointer is the tag `rc-1.0.0`, created on the merge commit that
brings this freeze into `main`.

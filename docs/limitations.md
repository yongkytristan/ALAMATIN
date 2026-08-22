# Limitations

Everything a reader should know before trusting a number or planning a demo.
Each entry says where the evidence is, so none of this rests on assertion.

## The most important one

**On real addresses this system almost never says "ready".** In the sealed run,
**0 of 130** addresses reached `SIAP_DIPROSES`; 123 returned
`MISSING_ADMINISTRATIVE_FIELDS`.

Entity F1 is 0.8984 on the same run. Both are true. The extractor recovers most
spans, but on real input it rarely recovers a *complete* administrative chain,
because the rule baseline needs `Kel.` / `Kec.` style markers that real
addresses frequently omit.

So this is a **confirmation-requesting** system on real input, not an
auto-clearing one. Any claim that it clears addresses without human review is
contradicted by its own evaluation. Evidence:
[`evaluation-results.md`](evaluation-results.md).

## The model that was selected is not the model that runs

The release candidate serves `regex-baseline-v1`. The selected fine-tuned
candidate `ner-targeted-v2` is a 712 MB release asset, excluded from both
repositories by `.gitignore`, and is **not served**.

`versions.model` reports what actually ran, so no response misrepresents itself.
But any accuracy figure from the model evaluation — including 0.9995 synthetic F1
and 52.9% real_dev critical exact match — describes a different system.
Quoting one beside a demo of this build would be an unsupported claim.

There is also **no like-for-like comparison** between the model and the baseline:
the recorded NER figures come from the selection split, not from the ablation
split. Evidence: [`ablation-and-latency.md`](ablation-and-latency.md),
[`release-candidate.md`](release-candidate.md).

## The system emits no correction suggestions

The pipeline applies deterministic normalization and never calls
`propose_correction`, so **zero** semantic suggestions were produced on the
sealed set. The false-correction rate is therefore undefined — 0 of 0.

The suggest-and-confirm path exists in the contract, the UI, and the tests, but a
demo showing a suggestion being accepted is showing a fixture, not this build.
Evidence: [`evaluation-results.md`](evaluation-results.md).

## The normalizer does not change decisions

On the ablation split it applied 4,811 changes across 748 of 750 addresses and
produced **0** additional valid administrative chains. Its contribution is
presentational — a canonical string to display and copy — not decisional. The
validator already tolerates the variation it removes. Evidence:
[`ablation-and-latency.md`](ablation-and-latency.md).

## Two metrics are reported with denominators too small to mean anything

- **Conflict/ambiguity recall is 1.0 on a denominator of one.** Only a single
  sealed address is flagworthy under the stated definition. It must not be
  quoted as "100% recall".
- **The user study has not been run.** No participant has been recruited and no
  session held, so every study figure is `not_measured`. The protocol, task
  generator, instrument, and analysis harness exist and are tested. Evidence:
  [`user-study-protocol.md`](user-study-protocol.md),
  [`evidence-index.md`](evidence-index.md).

## PII redaction is deliberately conservative

A recipient name is redacted only when it follows a marker — `Penerima:`,
`nama penerima:`, `a.n.:`, `atas nama:`. A bare name with no marker is **not**
redacted. Phone numbers are detected without a marker.

This is the ALM-021 choice: a broader name rule would strip real address tokens.
It means a pasted "Budi Santoso Jl. Braga 1" keeps the name. Evidence:
[`pii-handling.md`](pii-handling.md), [`integration.md`](integration.md).

## Coverage is Jawa Barat, and a coverage gap is not an error

The reference is `jabar-reference-v1`, 5,957 villages. A village outside it
yields `KELURAHAN_TIDAK_DITEMUKAN` at medium severity. **That is a gap in our
reference, not proof the address is wrong,** and it must never be presented as
one. There is no national coverage and no claim to any.

## Only the first span of each entity type is used

If the extractor emits two `KELURAHAN` spans, the first wins and the second is
dropped. Merging them would invent a value neither the model nor the user
supplied.

## Re-validation is stateless

`/validate` takes the same request document as `/parse` and re-evaluates the
submitted text. The server keeps no session, so it holds no record of which
suggestion a user accepted; the client must send the corrected text. This keeps a
result reproducible from its input alone.

## The validator is the performance cost centre

Complete-pipeline p50 is 28.5 ms against 0.10 ms for extraction — roughly 275x —
because the administrative validator searches the 5,957-row reference on every
call. Comfortable for a single-address UI, wrong for bulk throughput, and not
where an observer would guess. Measured single-threaded on one machine. Evidence:
[`ablation-and-latency.md`](ablation-and-latency.md).

## Geocoding and batch are not in the release candidate

Geocoding is implemented but **disabled**: no provider is configured, so no
external call is possible and the parse path reports `NOT_REQUESTED`. `/geocode`
answers `403` without consent and `501` with it. `/batch` answers `501`. No map
confirmation exists. Evidence: [`geocoding.md`](geocoding.md),
[`release-candidate.md`](release-candidate.md).

## The synthetic split is not a proxy for real input

And notably not uniformly easier: entity F1 is close to the sealed run (0.8923
against 0.8984) but critical exact match is much lower (0.3933 against 0.6692),
because the generator injects noise more aggressively than the sealed addresses
exhibit. The sealed run is the measurement of record for real input.

## What this project never claims

- No delivery-risk score, and no probability of delivery failure.
- No reduction in failed deliveries, returns, time, or cost. Nothing here
  measures a downstream outcome, and the sample sizes could not support it.
- No verified physical location. A rooftop geocode, were geocoding enabled,
  would still be `confirmed: false` until a human said otherwise.
- No calibrated confidence. `model_score` is an uncalibrated score and is never
  relabelled.
- No causal conclusion from the four exploratory interviews.

These are enforced, not just promised: the evidence index records
`delivery-outcomes` as `out_of_scope`, and a document quoting a number its
artifact does not hold fails CI.

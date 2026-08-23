# Documentation index

Every document in this repository, grouped by what you need it for.

`scripts/check_documentation.py` fails if a document is missing from this
index, if this index lists a document that does not exist, if a relative
link is broken, if a file is not UTF-8, or if an unfinished marker survives.
So this page cannot quietly fall behind the documentation it describes.

## Start here

| Document | What it covers |
|---|---|
| [README.md](../README.md) | Setup, run, test, Docker, and the review UI |
| [product-scope.md](product-scope.md) | The frozen scope, operational meanings, and allowed claims |
| [architecture.md](architecture.md) | How a request becomes a decision, and what leaves the process |
| [limitations.md](limitations.md) | Everything to know before trusting a number or planning a demo |

## Results and evidence

| Document | What it covers |
|---|---|
| [evidence-index.md](evidence-index.md) | Every reportable number mapped to its artifact and script |
| [evaluation-results.md](evaluation-results.md) | The one-time sealed evaluation of the release candidate |
| [ablation-and-latency.md](ablation-and-latency.md) | Stage ablation, cross-approach comparison, latency, failure cases |
| [approach-comparison.md](approach-comparison.md) | Head-to-head of every extraction approach on real addresses |
| [evaluation_protocol.md](evaluation_protocol.md) | The frozen evaluation protocol |
| [evaluation_splits_status.md](evaluation_splits_status.md) | Split provenance and status |
| [release-candidate.md](release-candidate.md) | The freeze record and its checksums |
| [user-study-protocol.md](user-study-protocol.md) | User-study design, instrument, and status |
| [model-card-ner-final-candidate.md](model-card-ner-final-candidate.md) | Model card for the selected NER candidate |
| [ner-v1.md](ner-v1.md) | NER v1 training and evaluation |
| [ner-v1-real-dev-error-analysis.md](ner-v1-real-dev-error-analysis.md) | Error analysis on the real dev split |
| [ner-schema-review.md](ner-schema-review.md) | Label schema review |

## Components

| Document | What it covers |
|---|---|
| [integration.md](integration.md) | The end-to-end pipeline and its known limitations |
| [quality-gate.md](quality-gate.md) | Operational statuses, reason codes, and precedence |
| [output-contract.md](output-contract.md) | The frozen wire contract and its invariants |
| [backend-api.md](backend-api.md) | Endpoints, error contract, and curl examples |
| [administrative-validator.md](administrative-validator.md) | Chain and postcode validation |
| [address-normalizer.md](address-normalizer.md) | Deterministic normalization and provenance |
| [label_schema.md](label_schema.md) | The ten canonical component types |
| [regex_baseline.md](regex_baseline.md) | The rule baseline that the release candidate serves |
| [reference_hierarchy.md](reference_hierarchy.md) | Reference data structure and lookup |
| [geocoding.md](geocoding.md) | Consent-gated geocoding, disabled by default |

## Privacy, data, and governance

| Document | What it covers |
|---|---|
| [pii-handling.md](pii-handling.md) | What is redacted, what is not, and why |
| [data-handling.md](data-handling.md) | Consent, logging, cache, retention, and attribution obligations |
| [sources.md](../data/sources.md) | Sources, licences, attribution, and redistribution decisions |
| [dataset_card.md](../data/dataset_card.md) | Dataset card |
| [artifact-policy.md](artifact-policy.md) | What may be committed and what may not |
| [decision-log.md](decision-log.md) | Durable decisions, numbering, and supersessions |
| [postal-data-status-and-review-guide.md](postal-data-status-and-review-guide.md) | Postal reference status and review guide |
| [public_address_benchmark.md](public_address_benchmark.md) | Public-address benchmark provenance |
| [synthetic_generator.md](synthetic_generator.md) | Synthetic address generation |
| [synthetic_audit_log.md](synthetic_audit_log.md) | Synthetic generation audit log |
| [osm_extraction.md](osm_extraction.md) | OSM street and landmark extraction |

## Operations and process

| Document | What it covers |
|---|---|
| [deployment.md](deployment.md) | Deploy pipeline, node facts, and required secrets |
| [reproducibility.md](reproducibility.md) | Clean-clone startup, container, and offline requirements |
| [qa.md](qa.md) | Automated tests, privacy scanning, and the QA report |
| [team-workflow.md](team-workflow.md) | Branching, review, and merge workflow |
| [risk-log.md](risk-log.md) | Risk log |
| [neutral-address-workflow-interview.md](neutral-address-workflow-interview.md) | Neutral interview instrument |
| [persona-interview-synthesis.md](research/persona-interview-synthesis.md) | Synthesis of the four persona interviews |
| [R01-fulfillment.md](research/interviews/R01-fulfillment.md) | Interview R01 |
| [R02-press-on-nails.md](research/interviews/R02-press-on-nails.md) | Interview R02 |
| [R03-toko-bahan-kue.md](research/interviews/R03-toko-bahan-kue.md) | Interview R03 |
| [R04-makanan-online.md](research/interviews/R04-makanan-online.md) | Interview R04 |

## Verifying the documentation

```bash
python scripts/check_documentation.py     # encoding, links, markers, index
python scripts/build_evidence_index.py    # every quoted number matches its artifact
python scripts/qa_privacy_scan.py         # no secret or raw PII
```

All three run in CI.

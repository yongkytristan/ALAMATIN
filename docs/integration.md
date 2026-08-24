# End-to-end integration (ALM-028)

`alamatin.pipeline.AddressPipeline` runs one auditable pass from raw address
text to a document that satisfies the frozen ALM-025 contract.
`alamatin.service` wires that pipeline into the ALM-026 transport, so the served
application answers with real results instead of `PIPELINE_UNAVAILABLE`.

## Stages

| Stage | Component | What it contributes |
|---|---|---|
| PII | `pii.process_pii` | A downstream-safe `address_text` and a display-safe `redacted_text` |
| Extraction | injected `Extractor` | Raw component values from the safe text |
| Normalization | `address_normalizer.normalize_address` | Deterministic formatting with provenance, plus proposals |
| Validation | `administrative_validator.AdministrativeValidator` | Administrative chain and postcode against the governed reference |
| Quality gate | `quality_gate.evaluate_quality_gate` | One operational status with reason codes |
| Contract | `output_contract.validate_contract_document` | Refuses to return anything the contract cannot express |

Every stage appends an audit event. Sequence numbers are contiguous from 1, and
the PII stage records reason codes only — never a detected value.

## Service entrypoint

```
uvicorn alamatin.service:app
```

`alamatin.api:app` is the transport with **unconfigured** handlers; it answers
`503 PIPELINE_UNAVAILABLE` by design. Deployments must serve
`alamatin.service:app`. Point `ALAMATIN_REFERENCE_PATH` at a different verified
reference artifact to override the default without a code change.

The health probe runs a real address through the pipeline. Reporting `ready`
without exercising it would defeat the purpose of the health contract.

## Known limitations

These are deliberate and documented rather than hidden.

**The runtime extractor is the rule baseline, not the fine-tuned model.** The
selected NER candidate is a 712 MB release asset, and `.gitignore` excludes
`*.safetensors`, so no model weights are tracked in this repository. The default
extractor is `regex_extractor`, and `versions.model` reports
`regex-baseline-v1.2` — it never claims a model that did not run. The extractor is
injected, so serving the fine-tuned model later requires no pipeline change.
Any accuracy figure quoted from the model evaluation describes that model, not
this default path.

**Recipient-name redaction is marker-based.** A name is redacted when it follows
`Penerima:`, `nama penerima:`, `a.n.:`, or `atas nama:`. A bare name with no
marker is not redacted. This is the conservative choice from ALM-021: a broader
rule would strip real address tokens. Phone numbers are detected without a
marker.

**Names adjacent to a phone number were previously missed.** Name detection now
runs against text whose phone spans are blanked out, because a phone inside the
candidate window used to make the whole candidate fail the name check and the
name survived redaction. Offsets are preserved by blanking rather than removing.

**Re-validation is stateless.** `/validate` takes the same request document as
`/parse`, so it re-evaluates submitted text rather than mutating a stored
session. A client applying a user's confirmation must send the corrected address
text. This keeps a result reproducible from its input alone, but it means the
server holds no record of which suggestion a user accepted.

**Geocoding is never invoked.** The parse path always reports
`status: NOT_REQUESTED` with `consent: false`. `consent` describes whether
consent was exercised *for a geocoding result*, so it stays false even when the
request granted it — nothing was looked up. `/geocode` remains consent-gated and
returns `501 FEATURE_NOT_ENABLED`.

**Only the first span of each entity type is used.** If the extractor emits two
`KELURAHAN` spans, the first wins and the second is dropped. Merging them would
invent a value that neither the model nor the user supplied.

**Coverage is the documented Jawa Barat release.** A village outside the
governed reference yields `KELURAHAN_TIDAK_DITEMUKAN` at medium severity. That
is a coverage gap, not proof the address is wrong, and it must never be
presented as one.

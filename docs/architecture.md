# Architecture

One request, one auditable pass, one decision. There is no queue, no database,
and no outbound call.

```
HTTP POST /parse            alamatin.api          transport only
   |                        (contract validation, timeouts, error contract)
   v
alamatin.service            handlers + dependency probe
   |
   v
alamatin.pipeline           the auditable pass
   |
   +--> pii.process_pii             raw text  -> safe text + redacted text
   +--> regex_baseline.tag_tokens   safe text -> BIO labels        [injected]
   +--> pipeline.decode_bio         BIO       -> components
   +--> address_normalizer          components-> canonical + provenance
   +--> administrative_validator    components-> chain verdict     [reference]
   +--> quality_gate                verdict   -> one status + reasons
   +--> geocoding                   disabled by default
   +--> output_contract             refuses anything the contract cannot express
   |
   v
address_parse_response      status, issues, components, versions, audit trail
```

## Module responsibilities

| Module | Responsibility | Never does |
|---|---|---|
| `api` | ASGI transport, request validation, timeouts, structured errors | know what an address is |
| `service` | wires real handlers and the health probe | contain decision logic |
| `pipeline` | orders the stages, assembles the response, appends audit events | invent a value |
| `pii` | detects phones and marker-led names, emits safe and redacted text | keep a raw detected value |
| `regex_baseline` | rule-based BIO tagging | learn anything |
| `address_normalizer` | representation-preserving rewrites with provenance | change meaning without a proposal |
| `administrative_validator` | compares the chain and postcode with the governed reference | guess a match |
| `quality_gate` | one operational status from issues and frozen rules | use a score or threshold |
| `geocoding` | consent-gated lookup, disabled by default | call out without consent **and** a provider |
| `output_contract` | validates the wire document and its invariants | be bypassed |

## Design decisions that shape everything else

**The extractor is injected.** `AddressPipeline` takes a callable. The release
candidate passes the rule baseline; a model-backed extractor needs no pipeline
change. `versions.model` reports whichever ran, so a response never claims a
model that did not. See [`integration.md`](integration.md).

**The gate is deterministic.** No score, threshold, or probability participates
in the operational status. `thresholds` is explicitly `null` in the release
manifest so the absence is recorded rather than assumed.

**High severity is confined to reference-supported fields.** Only
`KELURAHAN`, `KECAMATAN`, `KOTA_KABUPATEN`, `PROVINSI`, and `KODEPOS` can be
contradicted by the governed reference, so only they can reach `TIDAK_VALID`.
Enforced in both the gate and the contract validator.

**Nothing substantive is applied without a human.** A semantic suggestion is a
proposal with `applied: false` and `user_confirmation: null`. Only an explicit
user action may set `confirmed`.

**Geocoding is resolved after the gate** and is not an input to it, so an
external failure cannot turn a locally valid address into `TIDAK_VALID`.

**The pipeline refuses to emit anything the contract cannot express.**
`validate_contract_document` runs before a response is returned, so a malformed
document becomes a structured 500 rather than reaching a client.

## Data flow and what leaves the process

| Boundary | What crosses it |
|---|---|
| client -> service | raw address text, in request scope only |
| service -> logs | route, status, request id, error code — never input or exception text |
| pipeline -> extractor | PII-safe text only |
| pipeline -> geocoder | PII-safe text only, and only with consent and a provider |
| service -> client | the contract document; PII appears only as `redacted_text` |
| process -> disk | nothing. The reference is read; nothing is written |

Retention, logging, and cache policy for each of these boundaries:
[`data-handling.md`](data-handling.md).

## Frontend

`web/` is a Next.js app. It loads the canonical schema through
`address-contract.js` rather than keeping a copy, and maps the wire contract to
its view model in `lib/contract.ts` so the components never see snake_case
provenance envelopes. With `NEXT_PUBLIC_API_BASE_URL` unset it runs on typed
fixtures, so every state is demonstrable without a backend.

## Deployment

A release is unpacked beside its predecessors and activated by swapping a
symlink, after an import check proves it can start. nginx proxies port 80 to
uvicorn on `127.0.0.1:8000`. See [`deployment.md`](deployment.md) and
[`reproducibility.md`](reproducibility.md).

## What is not here

No database, cache, queue, or background worker. No authentication or
multi-tenancy. No batch endpoint in the release candidate. No map. These are
absences by design for the P0 scope, not gaps waiting to be filled — see
[`product-scope.md`](product-scope.md) and [`limitations.md`](limitations.md).

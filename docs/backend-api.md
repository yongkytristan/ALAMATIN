# Backend API and error contract

ALM-026 exposes a dependency-free ASGI application at `alamatin.api:app`.
Production may run it with any ASGI server; for example, when Uvicorn is
available:

```bash
uvicorn alamatin.api:app --app-dir src --host 127.0.0.1 --port 8000
```

The module-level app deliberately reports a degraded health state and returns
`PIPELINE_UNAVAILABLE` until the model/reference handlers are wired by the
end-to-end pipeline issue. Tests and deployments inject handlers through
`create_app(...)`; the transport never fabricates model output.

## Endpoints

| Method and path | Release | Behaviour |
|---|---|---|
| `GET /health` | P0 | Reports `app=alive` separately from critical dependency readiness. Returns 503 when a critical dependency fails. |
| `POST /parse` | P0 | Validates an ALM-025 request, runs the injected parser with a timeout, and validates its response against the same contract. |
| `POST /validate` | P0 | Uses the same request/success contract and runs the injected validation handler. |
| `POST /geocode` | P1 contract | Rejects missing consent with 403. A consented request currently returns the explicit 501 `FEATURE_NOT_ENABLED`. |
| `POST /batch` | P1 contract | Accepts the frozen bounded batch shape (1–100 items) and currently returns explicit 501. |

The default maximum body size is 64 KiB and default processing/probe timeout is
10 seconds. `create_app` allows a deployment to lower these values. Request
validation occurs before a handler is called. Malformed JSON, schema errors,
timeouts, unavailable dependencies, oversized bodies, unsupported methods, and
unexpected internal errors use the shared `api_error` contract and do not stop
the ASGI process.

Default logs contain only route, HTTP status, safe request ID, and error code.
They never contain the request body or exception text, because downstream
exceptions may accidentally include a raw address.

A client that disconnects before its body is fully read gets no response at
all, rather than the misleading `413 REQUEST_TOO_LARGE` it once received. The
disconnect is logged as route only.

## The error path cannot raise

`error_document` builds the `api_error` payload from untrusted input: handlers
choose their own `APIServiceError` code and message, and the function is called
from inside `except` blocks. A blank, missing, or non-string code or message is
therefore replaced with `FALLBACK_ERROR_CODE` / `FALLBACK_ERROR_MESSAGE`,
`retryable` is coerced to a boolean, and each detail entry is rebuilt in the
same way. If the assembled document still fails contract validation, a document
built only from frozen constants is emitted instead.

Without this, a handler raising `APIServiceError("SOMETHING", "")` made
`error_document` raise `ContractValidationError` from inside the `except` block,
which escaped the application and defeated the guarantee that an internal error
still returns a structured response.

`error.code` is deliberately left as a free-form string in the schema rather
than an enum, because handlers may define deployment-specific codes. The
sanitisation above is what keeps that freedom from breaking the contract.

## Curl examples

Health:

```bash
curl -i http://127.0.0.1:8000/health
```

Parse:

```bash
curl -i -X POST http://127.0.0.1:8000/parse \
  -H "Content-Type: application/json" \
  --data @contracts/examples/success.request.json
```

Validate uses the same frozen request contract:

```bash
curl -i -X POST http://127.0.0.1:8000/validate \
  -H "Content-Type: application/json" \
  --data @contracts/examples/invalid.request.json
```

Consent-gated geocoding contract:

```bash
curl -i -X POST http://127.0.0.1:8000/geocode \
  -H "Content-Type: application/json" \
  --data @contracts/examples/success.request.json
```

A P1 batch request has `document_type=address_batch_request`, schema version
`1.0.0`, a safe request ID, and an `items` array. Each item contains
`address_text` and `geocoding_consent`.

## Structured error example

```json
{
  "document_type": "api_error",
  "schema_version": "1.0.0",
  "request_id": "req_success_001",
  "error": {
    "code": "PIPELINE_UNAVAILABLE",
    "message": "The address-processing pipeline is not configured.",
    "retryable": true,
    "details": []
  }
}
```

Error messages and details are intentionally generic. Field-level schema
diagnostics must never echo the submitted address.

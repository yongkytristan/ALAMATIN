# ALAMATIN

ALAMATIN is a pre-fulfillment address quality gate that helps Indonesian seller
operators identify incomplete, ambiguous, or administratively conflicting
address components and request human confirmation before a waybill is created.

The frozen Jawa Barat release scope, operational meanings, priority cut-line,
and allowed claims are defined in [docs/product-scope.md](docs/product-scope.md).

## Current status

The single-address path runs end to end: PII redaction, component extraction,
normalization with provenance, administrative validation against the governed
Jawa Barat reference, and the frozen quality gate, exposed through the HTTP
contract and a Next.js review UI.

The runtime extractor is the deterministic rule baseline, and responses report
`versions.model` as `regex-baseline-v1`. The fine-tuned NER candidate is a
release asset and is not part of this release candidate; see
[docs/integration.md](docs/integration.md).

Raw and derived source data remain ignored and cannot be redistributed under the
recorded source terms. See [data/sources.md](data/sources.md).

## Repository layout

| Path | Purpose |
|---|---|
| `data/` | Dataset metadata and reproducible data instructions; raw/private data is never committed |
| `scripts/` | Reproducible repository, data, training, and evaluation commands |
| `src/` | Python backend and ML packages |
| `web/` | Frontend application |
| `tests/` | Unit, integration, privacy, and reproducibility tests |
| `docs/` | Architecture, governance, decisions, risks, and evaluation documentation |

## Quick start

Requirements: Python 3.11 or newer, and Git. Python 3.10 is the hard floor: the
code uses `dataclass(slots=True)`.

### Verify the clone

```bash
python scripts/verify_clean_clone.py
```

Checks the interpreter, every runtime file, that no secret is needed, that the
application imports, that the pipeline answers a real address, and that
`/health` returns 200. Every failure names the step at fault.

### Run the tests

```bash
python -m unittest discover -s tests
python scripts/check_repository.py     # tracked-file and repository policy
python scripts/qa_privacy_scan.py      # secrets and raw PII
python scripts/qa_report.py            # critical-path coverage and skips
```

No network access is required for any of these.

### Run the service

```bash
python -m pip install --require-hashes -r requirements.lock
PYTHONPATH=src python -m uvicorn alamatin.service:app --port 8000
```

Then:

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/parse   -H 'Content-Type: application/json'   -d '{"document_type":"address_parse_request","schema_version":"1.0.0",
       "request_id":"req_demo_00001",
       "input":{"address_text":"Jl. Asia Afrika No. 1, Kel. Braga, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111",
                "geocoding_consent":false}}'
```

That address returns `SIAP_DIPROSES`. Dropping the `Kel.`/`Kec.` prefixes or the
province returns `PERLU_KONFIRMASI` with `MISSING_ADMINISTRATIVE_FIELDS`, which
is the intended behaviour: the rule baseline needs those markers.

The files in `contracts/examples/` illustrate the **contract shape** for each
state. They are hand-authored fixtures, not recorded pipeline output, so feeding
`success.request.json` to the running service does not necessarily reproduce
`success.response.json`.

`alamatin.service:app` is the wired application. `alamatin.api:app` is the
transport with unconfigured handlers and answers `503` by design.

### Run in Docker

```bash
docker compose up --build
curl http://localhost:8000/health
```

### Run the review UI

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm test
```

The UI defaults to typed fixtures so every state can be demonstrated without a
backend. Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` to use the live
API.

Installing dependencies needs network access; nothing else does. See
[docs/reproducibility.md](docs/reproducibility.md).

## Working agreement

- Create branches named `feat/<short-description>` or `fix/<short-description>`.
- Keep pull requests small and focused on one reviewable outcome.
- Require at least one reviewer before merge.
- Reference the relevant issue using `Closes #...` or `Refs #...`.
- Never commit secrets, raw personal addresses, customer data, private contact
  details, model checkpoints, or unlicensed datasets.

See [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/team-workflow.md](docs/team-workflow.md) for the complete workflow.

## Security and privacy

Use `.env.example` only as a template. Actual credentials belong in an ignored
`.env` file or the deployment platform's secret store. Public-address datasets
must still pass provenance, licensing, redistribution, and PII reviews before
use. See [docs/artifact-policy.md](docs/artifact-policy.md).

Address text is held for the lifetime of a request and no longer: nothing is
cached, nothing is written to disk on the request path, and no log line contains
address or exception text. Consent, logging, cache, retention, and the OSM
attribution obligation are documented in
[docs/data-handling.md](docs/data-handling.md).

## Documentation

[docs/README.md](docs/README.md) indexes every document. Start with
[docs/architecture.md](docs/architecture.md) for how a request flows, and
[docs/limitations.md](docs/limitations.md) for what the numbers do and do not
support.

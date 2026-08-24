# ALAMATIN

ALAMATIN is a pre-fulfillment address quality gate that helps Indonesian seller
operators identify incomplete, ambiguous, or administratively conflicting
address components and request human confirmation before a waybill is created.

**Live demo:** [alamatin.flow-app.my.id](https://alamatin.flow-app.my.id)

It separates address components, redacts supported PII, checks the
administrative chain against the governed Jawa Barat reference, and returns an
operational status with actionable reason codes.

## What is included

- A Python HTTP API in `src/alamatin/`.
- A Next.js single-address review UI in `web/`.
- The frozen API contract in `contracts/`.
- The governed runtime reference in
  `data/processed/jabar-reference-v1-verified.json`.
- Tests, evaluation evidence, and reproducibility scripts.

The current runtime extractor is the deterministic
`regex-baseline-v1.2`. The selected fine-tuned NER candidate is recorded as a
research/release asset but is not served by this build. See
[the integration notes](docs/integration.md) and
[the frozen release record](docs/release-candidate.md).

## Local setup

### Prerequisites

- Git
- Python 3.11 or newer
- Node.js 20.9 or newer and npm
- Docker Desktop or Docker Engine with Compose, optional

No API key or private dataset is required for the default local demo.

### 1. Clone and prepare the backend

```bash
git clone https://github.com/yongkytristan/ALAMATIN.git
cd ALAMATIN
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

Install the exact runtime dependencies and verify the clone:

```bash
python -m pip install --require-hashes -r requirements.lock
python scripts/verify_clean_clone.py
```

A healthy clone ends with `clean clone is healthy`.

### 2. Start the backend

```bash
python -m uvicorn alamatin.service:app --app-dir src --host 127.0.0.1 --port 8000
```

Verify it from another terminal:

```bash
curl http://127.0.0.1:8000/health
```

The response should report HTTP 200 and `"status":"healthy"`.

The deployed health endpoint is available at
<https://alamatin.flow-app.my.id/api/health>.

### 3. Start the web interface

Keep the backend running, then open another terminal:

```bash
cd web
npm ci
```

Copy the supplied frontend environment template:

```powershell
# Windows PowerShell
Copy-Item .env.example .env.local
```

```bash
# macOS or Linux
cp .env.example .env.local
```

Start the UI:

```bash
npm run dev
```

Open <http://localhost:3000>. The browser sends `/api/*` requests through the
Next.js proxy to the backend at `http://127.0.0.1:8000`.

To demonstrate the interface without the backend, remove
`NEXT_PUBLIC_API_BASE_URL` from `web/.env.local`; the UI will use its typed
synthetic fixtures.

## Docker alternative

The Docker Compose setup starts the backend only:

```bash
docker compose up --build
curl http://127.0.0.1:8000/health
```

Run the web setup above separately if the review UI is also needed.

## Tests

Backend and repository checks:

```bash
python -m unittest discover -s tests
python scripts/check_repository.py
python scripts/qa_privacy_scan.py
python scripts/qa_report.py
```

Frontend checks:

```bash
cd web
npm ci
npm test
npm run build
```

The Python runtime tests do not require network access. Dependency installation
does.

## Repository layout

| Path | Purpose |
|---|---|
| `src/alamatin/` | Backend runtime and reusable address-processing modules |
| `web/` | Next.js review UI and component tests |
| `contracts/` | Canonical API schema and request/response examples |
| `data/` | Redistributable runtime data, dataset metadata, and synthetic splits |
| `tests/` | Unit, integration, privacy, and reproducibility tests |
| `docs/` | Architecture, scope, governance, limitations, and results |
| `scripts/` | Data preparation, evaluation, QA, and deployment utilities |
| `configs/` | Frozen experiment configurations |
| `experiments/` | Small, auditable result artifacts used by project claims |
| `requirements/` | Dependencies used only for reproducible model experiments |

Generated proposal sources, videos, exploratory notebooks, model weights,
raw/private datasets, and local build outputs are intentionally excluded from
the public repository.

## Important boundaries

- The MVP reference covers Jawa Barat and contains 5,957 verified
  administrative rows.
- The running release serves a deterministic rule-based extractor, not the NER
  checkpoint.
- Raw customer addresses are not committed, cached, or written to disk by the
  request path.
- `alamatin.service:app` is the configured application.
  `alamatin.api:app` intentionally has no handlers and returns 503.
- Files in `contracts/examples/` illustrate the contract shape; they are not
  guaranteed recordings of current pipeline output.

The frozen scope and allowed claims are in
[docs/product-scope.md](docs/product-scope.md). Known limitations are in
[docs/limitations.md](docs/limitations.md).

## Documentation and contribution

[docs/README.md](docs/README.md) is the documentation index. Start with
[docs/architecture.md](docs/architecture.md) to understand the request flow and
[docs/reproducibility.md](docs/reproducibility.md) for the clean-clone contract.

Contribution and security rules are documented in
[CONTRIBUTING.md](CONTRIBUTING.md), [docs/team-workflow.md](docs/team-workflow.md),
and [docs/artifact-policy.md](docs/artifact-policy.md).

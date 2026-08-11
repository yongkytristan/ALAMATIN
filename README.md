# ALAMATIN

ALAMATIN is a pre-fulfillment address quality gate for informal Indonesian
addresses. The repository currently contains the project skeleton and working
agreements; product implementation is tracked separately in GitHub Issues.

## Current status

Repository foundation, NER/evaluation contracts, public-source governance, and
the deterministic Jawa Barat hierarchy/postal lookup are implemented. The
governed builder has also produced a real local/internal Jawa Barat reference
from the user-supplied source snapshots. Raw and derived source data remain
ignored and cannot be redistributed from the repository under the recorded
source terms.

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

Requirements: Python 3.11+ and Git.

```bash
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

The initial checks require no third-party dependency. `requirements.lock` is
intentionally empty until the technical stack is frozen.

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

# Reproducibility, containers, and clean-clone startup (ALM-033)

## One command to check a clone

```bash
python scripts/verify_clean_clone.py
```

It checks, in the order a new reviewer hits them: interpreter version, every
runtime file, that no secret is required, that the application imports, that the
pipeline answers a real address, and that `/health` returns `200`. Each failure
names the file or step at fault instead of surfacing a traceback from deep
inside an import.

Verified on an actual fresh `git clone` of this repository, not just on a working
checkout:

```
ok   interpreter            Python 3.12.4
ok   runtime files          7 runtime files present
ok   no secret required     no secret needed to start
ok   import                 alamatin.service imported
ok   pipeline               pipeline answered SIAP_DIPROSES
ok   health endpoint        /health 200 healthy
```

## Container

```bash
docker compose up --build
curl http://localhost:8000/health
```

Design points, each for a reason:

- **`python:3.11-slim` is pinned.** The code uses `dataclass(slots=True)`, which
  is 3.10+, and the deploy node's system `python3` is 3.9. An unpinned base
  image would let that difference come back.
- **Dependencies install with `--require-hashes`.** This is the only step that
  needs network access.
- **The build fails if the app cannot import.** `RUN python -c "import
  alamatin.service"` runs during build, so a broken image is a failed build
  rather than a container that restarts forever.
- **The entrypoint is `alamatin.service:app`.** `alamatin.api:app` is the
  transport with unconfigured handlers and answers `503` by design.
- **Only the approved reference file is copied in.** `data/` is excluded by
  `.dockerignore` and `data/processed/jabar-reference-v1-verified.json` is
  copied by name, so no governed data can reach an image by accident. A test
  asserts that this is the only `data` path copied.
- **Runs as a non-root user, read-only root filesystem, no new privileges.** The
  service reads one file and writes nothing.
- **`HEALTHCHECK` uses the stdlib**, so no `curl` is installed. A `503` fails the
  check: the app being alive is not the same as the pipeline being able to
  answer.

## Internet requirements

| Phase | Network needed |
|---|---|
| `pip install -r requirements.lock` / `docker build` | **yes** — to fetch uvicorn and its dependencies |
| Running the service | **no** |
| Running the test suite | **no** |
| `verify_clean_clone.py` | **no** |

The runtime claim is verified rather than asserted: with all outbound socket
connections blocked, `verify_clean_clone.py` passes and all 448 tests pass. The
governed reference is a file in the repository, the pipeline makes no outbound
call, and geocoding is disabled by default.

For a demo on a limited or untrusted connection, build the image beforehand and
carry it, or pre-populate a pip cache. Nothing is fetched once the process
starts.

## Model checkpoint provisioning

**The demo requires no checkpoint download.** This is the deliberate answer to
the fragile-download risk, not an omission.

The runtime extractor is the deterministic rule baseline in
`alamatin.pipeline.regex_extractor`, which lives in the repository.
`versions.model` reports `regex-baseline-v1.2`, so a response never claims a model
that did not run. There is nothing to download, so there is nothing to fail
during a demo.

The selected fine-tuned candidate (`ner-targeted-v2`) is a 712 MB release asset
recorded in `experiments/ner-final-candidate/release_manifest.json` with its
SHA-256. It is not in either repository — `.gitignore` excludes
`*.safetensors` — and it is **not** part of the release candidate. If it is ever
served, the extractor is injected, so no pipeline change is needed; verify the
asset against the manifest checksum before use.

See `docs/integration.md` for the accuracy consequence: figures from the model
evaluation describe that model, not the baseline the demo runs.

## What is pinned

| Component | Pinned by |
|---|---|
| Python | `python:3.11-slim` in `Dockerfile`; `MIN_PYTHON` in the verifier |
| Runtime dependencies | `requirements.lock`, installed with `--require-hashes` |
| Reference data | `data/processed/jabar-reference-v1-verified.json`, reported as `versions.reference_data` |
| Quality-gate rules | `RULES_VERSION` (`quality-gate-v1`), reported in every response |
| Output contract | `contracts/address-api.v1.schema.json`, `schema_version 1.0.0` |
| Extractor | `REGEX_EXTRACTOR_VERSION` (`regex-baseline-v1.2`) |

Every one of these appears in the `versions` block of an API response, so a
result can be traced to the exact configuration that produced it.

## No committed secret is needed

The service starts with no environment configuration. `.env` and `.env.*` are
git-ignored and excluded from the build context; only `.env.example` is tracked.
`verify_clean_clone.py` records this as a check so a future change that starts
requiring a secret is caught here rather than at a demo.

Deployment secrets (`DEWACLOUD_SSH_*`) belong to the deploy pipeline, not the
application, and are never read by it.

## Contract examples are fixtures, not recorded output

`contracts/examples/*.json` illustrate the shape of each contract state. They
were hand-authored for ALM-025, before the pipeline existed in ALM-028, so a
request fixture does not necessarily reproduce its paired response fixture
against the running service.

Concretely: `success.request.json` returns `PERLU_KONFIRMASI` from the live
pipeline, because its address omits the `Kel.`/`Kec.` markers the rule baseline
needs and omits the province, so administrative context is incomplete.
`success.response.json` shows `SIAP_DIPROSES`.

Both are correct for their purpose — the fixture demonstrates the ready-state
shape, and the pipeline correctly reports missing context for that input — but
they must not be presented as a recorded request/response pair. The README uses
an address that genuinely returns `SIAP_DIPROSES` so a reviewer following it sees
real behaviour.

Recorded here rather than fixed silently: changing the frozen examples is a
contract change, and aligning them with pipeline output belongs to the evidence
work in ALM-038 and ALM-039.

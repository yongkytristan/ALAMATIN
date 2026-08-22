# Decision log

Record durable technical, data, product, and governance decisions here. Do not
overwrite previous decisions; add a superseding entry that links to the old one.

## DEC-001 — Repository workflow baseline

- Date: 2026-08-10
- Status: accepted
- Decision: use `main` with short-lived `feat/*` and `fix/*` branches, small pull
  requests, at least one approving reviewer, and required repository checks.
- Rationale: supports fast delivery while retaining reviewable evidence.
- Consequences: direct changes to `main` should be disabled through branch
  protection once the first collaborator is added.

## DEC-002 — Dependency-free skeleton validation

- Date: 2026-08-10
- Status: accepted
- Decision: use Python 3.11 standard-library checks until the implementation
  stack is frozen.
- Rationale: avoids selecting dependencies before architecture decisions.
- Consequences: `requirements.lock` remains intentionally empty for now.

## DEC-003 - Freeze the single-address product scope and claim boundary

- Date: 2026-08-22
- Status: proposed until the whole-team approval record in the scope-freeze PR
  is complete; accepted immediately after all approvals are recorded.
- Decision: freeze ALAMATIN `1.0.0` as a Jawa Barat, single-address,
  pre-fulfillment quality gate with the status and claim semantics in
  [`product-scope.md`](product-scope.md). Geocoding and batch processing remain
  optional P1 work; P2 remains post-submission backlog.
- Rationale: the persona interviews support an explainable pre-waybill check,
  while current evidence does not support delivery-risk, failed-delivery, or
  verified-location claims.
- Consequences: new scope enters the backlog; P1/P2 cannot delay the release;
  unsupported claims and incomplete optional paths must be removed rather than
  represented by placeholders.

## DEC-005 — Pin uvicorn as the ASGI server

- Date: 2026-08-22
- Status: accepted
- Supersedes: the DEC-002 consequence that `requirements.lock` remains
  intentionally empty. DEC-002 itself still stands: the address pipeline in
  `src/alamatin/` continues to use only the Python standard library.
- Decision: adopt `uvicorn==0.52.4` as the ASGI server and pin it, with
  `click`, `h11`, and the conditional `colorama` and `typing_extensions`, in
  `requirements.lock` with wheel and sdist hashes. The service entrypoint is
  `alamatin.api:app`.
- Rationale: `src/alamatin/api.py` is a dependency-free ASGI application, but
  the Dewacloud deploy needs something to serve it, and the node has neither
  `uvicorn` nor `gunicorn` installed. Pinning with hashes keeps the repository
  dependency policy intact; the deploy installs with `--require-hashes`, so an
  unpinned or unhashed requirement fails the deploy rather than fetching an
  unverified package.
- Consequences: the runtime stack is no longer standard-library-only, so a
  clean-clone check must install this lock file. Bumping the server is a
  reviewed change to this lock file, not an ad-hoc install on the node. The
  node requires Python 3.10+ for both this server and the application's use of
  `dataclass(slots=True)`; its system `python3` is 3.9, so deploys pin
  `python3.11` (see [`deployment.md`](deployment.md)).
- Numbering note: `DEC-004` is deliberately skipped. Decision entries numbered
  `DEC-003` and `DEC-004` are already in flight in the internal repository for
  the postal-review adjudication work, and reusing either number here would
  collide when that work is published.

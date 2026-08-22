# Decision log

Record durable technical, data, product, and governance decisions here. Do not
overwrite previous decisions; add a superseding entry that links to the old one.

## Numbering

Numbers are unique and permanent once published. A published number is never
reused for a different decision, even if a gap results.

`DEC-003` and `DEC-004` are **reserved** for the postal-review adjudication
decisions dated 12 August 2026, which are recorded in the internal repository
and not yet published here. They are not missing; they belong to work whose
supporting evidence is governed by [`../data/sources.md`](../data/sources.md).

The scope-freeze entry below was originally recorded as `DEC-003` and is now
`DEC-006`. That renumbering is deliberate: the postal decisions predate it by
ten days, so `DEC-003` was already theirs, and two different decisions cannot
share a number across the two repositories. This note exists so the change is
auditable rather than silent.

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

## DEC-005 — Pin uvicorn as the ASGI server

- Date: 2026-08-22
- Status: accepted
- Supersedes: the DEC-002 consequence that `requirements.lock` remains
  intentionally empty. DEC-002 itself still stands: the address pipeline in
  `src/alamatin/` continues to use only the Python standard library.
- Decision: adopt `uvicorn==0.52.4` as the ASGI server and pin it, with
  `click`, `h11`, and the conditional `colorama` and `typing_extensions`, in
  `requirements.lock` with wheel and sdist hashes.
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
- Amendment, 2026-08-22: this entry originally named `alamatin.api:app` as the
  service entrypoint. ALM-028 wired the pipeline into
  `alamatin.service:app`, which is what deployments must serve;
  `alamatin.api:app` is the transport with unconfigured handlers and answers
  `503` by design. See [`integration.md`](integration.md).

## DEC-006 — Freeze the single-address product scope and claim boundary

- Date: 2026-08-22
- Renumbered from `DEC-003` on 2026-08-23; see the Numbering section above.
- Status: accepted. The whole-team approval was given outside GitHub and is
  recorded on the project owner's confirmation in
  [issue #4](https://github.com/yongkytristan/ALAMATIN/issues/4); no formal
  review was left on the scope-freeze pull request.
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

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

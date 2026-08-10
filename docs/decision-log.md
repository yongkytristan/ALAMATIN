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

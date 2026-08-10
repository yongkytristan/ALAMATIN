# Artifact, privacy, and secret policy

## Allowed in Git

- Source code, documentation, schemas, and small synthetic fixtures.
- Metadata and reproducible instructions for approved public sources.
- Aggregated evaluation results that contain no personal information.

## Prohibited in Git

- Customer or household addresses, personal phone numbers, and raw PII.
- `.env` files, credentials, tokens, private keys, and service-account files.
- Restricted or ambiguously licensed datasets.
- Model checkpoints, downloaded archives, and generated artifacts above 10 MiB.

If prohibited material enters history, stop work, rotate exposed credentials when
applicable, preserve evidence needed for incident handling, and coordinate a
history cleanup before further collaboration.

# Team workflow

## Work selection

Start only issues whose dependencies and gates are satisfied. Keep blocked work
in `Blocked` with a concise explanation; do not silently bypass a dependency.

## Branches and commits

- Use `feat/<short-description>` or `fix/<short-description>`.
- Use lowercase kebab-case after the prefix.
- Make focused, imperative commits such as `test: cover address conflicts`.
- Never commit secrets, raw PII, restricted datasets, checkpoints, or generated
  files that can be reproduced locally.

## Pull requests and review

- One primary reviewable outcome per pull request.
- Reference the issue with `Closes #...` or `Refs #...`.
- Include verification, privacy/data impact, and known limitations.
- Require at least one approving reviewer and passing required checks.
- Merge only after acceptance criteria are demonstrably satisfied.

## Artifact locations

| Artifact | Location |
|---|---|
| Backend and ML source | `src/` |
| Frontend source | `web/` |
| Reproducible commands | `scripts/` |
| Automated checks | `tests/` |
| Dataset metadata and schemas | `data/` |
| Architecture, governance, results | `docs/` |
| Local raw/private data | ignored `data/raw/` or `data/private/` |
| Local models/checkpoints | ignored `models/` or `checkpoints/` |

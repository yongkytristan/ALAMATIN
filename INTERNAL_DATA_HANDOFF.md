# ALAMATIN internal data handoff

This private repository mirrors the public ALAMATIN `main` branch at merge
commit `4819f0c6ca3e3d5180776ca7c4c00c913ff52560` and adds the local-only source,
interim, processed, workbook, and reviewer artifacts for Issue 8.

## Access boundary

This repository must remain private. Grant access only to project members who
need the data for ALAMATIN. Do not fork it to a public account, publish release
assets, or copy the data into the public `yongkytristan/ALAMATIN` repository.

The payload includes data with internal-use or no-redistribution restrictions,
including Kodepos.dev validation observations. It contains no customer
addresses or intended person-level data.

No `.env`, API key, Git credential, or personal Codex configuration is included.
Each collaborator must create their own ignored `.env` and obtain their own
authorized credentials.

## Clone and verify

```bash
git clone https://github.com/yongkytristan/ALAMATIN-internal.git
cd ALAMATIN-internal
python -m unittest discover -s tests -p 'test_*.py'
python scripts/check_repository.py
```

The repository already contains the same relative paths used by the scripts,
including `data/raw/`, `data/interim/`, `data/processed/`, and the locally
supplied root source files. No overlay step is required.

Use `INTERNAL_DATA_MANIFEST.json` to verify file sizes and SHA-256 values after
clone.

## Reviewer workflow

Reviewers should read
`docs/postal-data-status-and-review-guide.md` before editing anything. Work only
in these editable files:

- `data/interim/postal-review/jabar-postal-corroborated-review.csv`
- `data/interim/postal-review/jabar-postal-unresolved-review.csv`

Do not edit `data/processed/` build outputs directly. Do not automatically copy
one reviewed result across a district or triplet cluster.

When committing reviewer progress, keep evidence concise and exclude customer
addresses, names, phone numbers, credentials, and unrelated personal data.

## Updating code from the public repository

The public repository is configured as the `public` remote. To receive public
code updates without publishing internal data:

```bash
git fetch public main
git merge --no-edit public/main
```

Push only to the private `origin`. Never push an internal-data branch to the
public remote.

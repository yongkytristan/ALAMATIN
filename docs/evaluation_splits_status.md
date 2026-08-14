# Evaluation splits status (ALM-014)

- Protocol: `docs/evaluation_protocol.md` sections 7-9 define the rules this
  record follows.
- Split version: `sealed_real_test_v1`
- Status: **splits created and sealed; system not yet frozen** (`ALM-034` is
  a later milestone). This record exists so the sealed manifest hash is on
  file before that freeze happens, per the protocol's requirement.

## Split sizes (reproduced 2026-08-14, seed `20260814`)

| Split | Source | Example count |
|---|---|---|
| `synthetic_train` | `data/synthetic/train.json` | 4,500 |
| `synthetic_dev` | `data/synthetic/val.json` | 750 |
| `synthetic_test` | `data/synthetic/test.json` | 750 |
| `real_dev` | ALM-013 gold labels, stratified by kabupaten/kota | 70 |
| `sealed_real_test` | ALM-013 gold labels, stratified by kabupaten/kota | 130 |

`real_dev` and `sealed_real_test` are drawn from the same 200-example
ALM-012/ALM-013 gold set, split with
`scripts/build_evaluation_splits.py --real-dev-target 70 --seed 20260814`,
stratified so both splits keep proportional representation across all 27
Jawa Barat kabupaten/kota rather than a plain random cut.

## Sealed test custodian and access

- **Custodian**: Data & Research Lead (project owner), per
  `docs/evaluation_protocol.md` section 7. The custodian must not also act as
  ML & Evaluation Lead or take part in model/rule selection; that role is
  held by a different team member, so there is no conflict.
- The full sealed content and full manifest (ordered example IDs, per-item
  content hashes) exist **only** at
  `data/private/sealed-real-test/` on the custodian's machine --
  `data/private/**` is gitignored, so this never reaches any Git remote,
  internal or public.
- The boundary-safe manifest shareable with the ML & Evaluation Lead is
  committed at `data/interim/evaluation-splits/sealed-test-boundary-manifest.json`.
  It contains only the split version, schema/taxonomy versions, creation
  timestamp, example count, and a single SHA-256 content hash -- no example
  IDs, label distribution, or content, per the information boundary in
  `docs/evaluation_protocol.md` section 7.

## Reproducing and verifying

```bash
python scripts/build_evaluation_splits.py
python scripts/check_split_leakage.py
```

`check_split_leakage.py` verifies: synthetic base-id confinement across
train/val/test; that `real_dev` and `sealed_real_test` never share a
`base_address_id` (only checkable on the custodian's machine, where the
sealed file actually exists -- every other clone skips that specific check
rather than failing); that the synthetic and human-noised ID namespaces
never collide; and that the sealed file's content hash still matches the
committed boundary manifest.

## What ML iteration may read

Per `docs/evaluation_protocol.md` section 7, training code and the ML &
Evaluation Lead may read `synthetic_train`/`synthetic_dev`/`synthetic_test`
and `real_dev` only. `sealed_real_test` stays exclusively in the custodian's
local `data/private/` copy until the one-time sealed run in `ALM-035`, gated
by the `ALM-034` freeze record.

# Human-noised public-address benchmark (ALM-012)

- Benchmark ID: `alamatin_human_noised_public_address_benchmark_v1`
- Source catalog: `data/sources.json` version `1.6.0`, `source_id`
  `open_data_jabar_npsn_sd_2023` and `open_data_jabar_npsn_sma_2023`
- Status: **candidates selected, human rewriting pending** -- this is not a
  finished dataset yet.

## What this is

A benchmark of ~200 Jawa Barat **public-facility** addresses (SD/SMA school
addresses, never a personal residence), each rewritten by a human the way
they would type an address into a checkout form, without adding any new
personal data. Its purpose is to test the parser against real-world address
phrasing that the synthetic generator (ALM-010) cannot produce, since that
generator only ever uses generic, contributor-authored street/landmark
placeholders.

The term "human-noised public-address benchmark" is deliberate. This is not
"real delivery data" -- it is a human paraphrase of a public dataset, with
full source traceability. See `data/sources.md` for the full source review.

## Why a human has to do the rewriting step

The whole point of this benchmark is to capture how a real person phrases an
address, including the messiness (abbreviations, missing punctuation, word
order) that a generator cannot faithfully imitate. If this repository (or an
AI assistant working in it) generated the `rewritten_address` column itself,
the benchmark would misrepresent its own provenance and stop measuring
anything real. **No script in this pipeline writes that column. Only
`scripts/build_human_noised_benchmark.py assemble` reads it back in, and only
after validating a human filled it in.**

## Pipeline

1. **Fetch** raw rows (internal only; not redistributed):

   ```bash
   python scripts/fetch_npsn_school_addresses.py --levels sd sma
   ```

   Writes `data/interim/school-address-benchmark/npsn-{sd,sma}-raw.json`.
   See `data/sources.md` for why this uses paginated JSON requests instead of
   the dataset's own (Cloudflare-blocked) CSV export.

2. **Select candidates** -- a deterministic, stratified sample across all 27
   Jawa Barat kabupaten/kota and both school levels, with an explicit
   field allowlist (school name, NPSN, status, kecamatan/kabupaten, address
   text, year -- never a personal field):

   ```bash
   python scripts/build_public_address_benchmark_candidates.py --target 200 --seed 20260814
   ```

   Writes `data/interim/school-address-benchmark/candidates.csv` and
   `candidates-summary.json`.

3. **Make the annotation worksheet**:

   ```bash
   python scripts/build_human_noised_benchmark.py make-template
   ```

   Writes `data/interim/school-address-benchmark/annotation-template.csv`
   with blank `rewritten_address` and `annotator_id` columns.

4. **A human fills in the worksheet.** For each row:
   - Read `reference_address` (the raw school address) for context.
   - Write `rewritten_address` the way you would type that address into an
     online checkout form -- natural phrasing, typos and abbreviations
     welcome, but do not invent or add a name, phone number, or any personal
     detail that was not already in the reference.
   - Fill in `annotator_id` with a short pseudonymous code (initials + a
     number, e.g. `YT-01`), not your real name.
   - `rewritten_address` must differ from `reference_address` -- copying it
     verbatim will fail assembly.

5. **Assemble and validate**:

   ```bash
   python scripts/build_human_noised_benchmark.py assemble
   ```

   Rejects the run (no output written) if any row has an empty
   `rewritten_address`/`annotator_id`, a verbatim copy of the reference
   address, a duplicate `base_address_id`, or a phone-number-like digit
   sequence in the rewritten text. On success, writes
   `data/interim/school-address-benchmark/human-noised-benchmark.json` (the
   governed manifest: `base_address_id`, `source_id`, `source_record_id`,
   `source_url`, `school_level`, `text`, `annotator_id`) and a coverage
   summary.

## What ALM-012 does *not* include

BIO labels are out of scope here -- ALM-013 (double annotation + adjudication)
labels this benchmark's plain text after it exists. Do not add labels in this
pipeline; doing so would create a second, ungoverned labeling path.

## Redistribution

The raw NPSN rows and the candidate pool stay internal-only
(`data/interim/`), consistent with the `internal_noncommercial_only` license
finding for both source datasets (see `data/sources.md`). Once real
annotations exist, redistributing the *assembled benchmark text* (a human
paraphrase, not a copy of the source's own address field) needs its own
dated review recorded in `data/sources.json`, the same way
`jabar_postal_reference_v1_redistribution_2026_08_13` documented the postal
reference's public release.

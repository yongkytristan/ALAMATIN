# Synthetic address audit log (ALM-011)

- Audit date: 2026-08-13
- Sample: 50 examples, category-stratified across all 3 splits
- Sample seed: `110` (`scripts/sample_synthetic_audit.py`, reproducible)
- Sample artifact: `data/synthetic/audit-sample.json`
- Generator reviewed: `scripts/generate_synthetic_addresses.py`
  (`generator_version 1.0.0`, `template_version 1.0.0`)

## Method

`scripts/sample_synthetic_audit.py` draws a deterministic sample that covers
every noise category present in the generated data at least once, then fills
the remainder with a random draw. The sample was read token-by-token against
`docs/label_schema.md`'s entity definitions and boundary-precedence rules,
checking: language plausibility, whether each labeled span matched its
entity definition, whether administrative-conflict rows still carried a
`KODEPOS` label, and whether the sample was dominated by trivially easy or
implausible text.

## Round 1 findings (before fixes)

1. **Noise-category bookkeeping bug, not a label bug.** `abbreviation` was
   appended to every example's `categories` unconditionally whenever a
   designator was rendered, regardless of whether the chosen form was
   actually a non-canonical/shortened one. Every one of the 50 sampled
   examples carried `abbreviation`, which made the recorded proportion
   meaningless. Labels themselves were unaffected -- this only corrupted the
   noise-distribution bookkeeping, not the BIO annotation.
2. **Generator quality bug in landmark phrasing.** Two `LANDMARK_CATEGORIES`
   entries produced unnatural text: `"Pasar"` + `"Pasar Baru"` rendered as
   the word-doubled *"Pasar Pasar Baru"*, and `"Sekolah"` + `"SDN 1"`
   rendered as the redundant *"Sekolah SDN 1"* (`SDN` already means *Sekolah
   Dasar Negeri*). Both are `DETAIL_LOKASI` spans, so the label itself was
   still correct -- the text just did not read naturally.
3. **No BIO/label corruption found.** All 50 sampled sequences pass
   `alamatin.label_schema.validate_bio_sequence` (also enforced automatically
   at generation time -- the generator refuses to write an invalid sequence),
   and every span matched its intended entity per `docs/label_schema.md`
   (marker+value spans for `JALAN`/`NOMOR`/`RT`/`RW`/`KELURAHAN`/
   `KECAMATAN`/`KOTA_KABUPATEN`, bare digit `KODEPOS`, `[NAME]`/`[PHONE]`
   correctly labeled `O`).
4. **Difficulty distribution.** A minority of samples (roughly 1 in 10-15)
   combine a missing separator with an omitted designator between two
   adjacent components (for example `desa pejuang medansatria , kota bekasi`,
   where the kelurahan and kecamatan names run together with no marker
   between them). This is a legitimately hard, realistic case -- messy
   real-world addresses do run on like this -- and it did not dominate the
   sample; most examples remain readable.

## Fixes applied

- Every designator/marker choice (`JALAN`/`GANG`, `KELURAHAN`, `KECAMATAN`,
  `KOTA_KABUPATEN`, `PROVINSI`) now tags `abbreviation` only when the chosen
  form is outside an explicit canonical set (for example `"Jalan"` is
  canonical, `"Jl."`/`"Jln"`/`"JL"` are not).
- Removed the pre-baked misspelling variants `"Kecmatan"` and `"Jawa Brat"`
  from the designator/form pools -- misspellings are already produced, and
  now exclusively tracked, by the dedicated `typo()` mechanism.
- `LANDMARK_CATEGORIES["Pasar"]` no longer repeats the word "Pasar" in its
  names (`"Baru"`/`"Minggu"`/`"Cikapundung"`). Self-contained school/postal
  landmark names (`SDN 1`, `SD Negeri 4`, `MI Nurul Iman`, `Kantor Pos`,
  `Puskesmas`) moved to an empty-category key so no redundant "Sekolah"
  prefix is added.

## Round 2 re-check (after fixes)

- Regenerated the dataset with the same seed/config and re-ran
  `scripts/sample_synthetic_audit.py` (same seed `110`).
- `abbreviation` coverage in the fresh 50-sample audit set dropped to 49/50
  (was 50/50) -- the tag is now conditional; the aggregate rate stays high
  because an address has several independent designator slots, and it is
  realistic for at least one of them to be non-canonical.
- Enumerated every possible `_build_landmark` output (300 draws) and
  confirmed no repeated or redundant category/name combination remains.
- No new label-boundary or plausibility issues found on re-check.

## Conclusion

No systematic label corruption was found or introduced. The two issues found
were generator-quality issues (noise bookkeeping accuracy and landmark
phrasing naturalness), both fixed and re-verified. The corpus is not
dominated by trivially easy or implausible patterns.

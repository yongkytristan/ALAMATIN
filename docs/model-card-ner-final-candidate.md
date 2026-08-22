# Model card draft: ALAMATIN NER final candidate

## Model details

- Candidate ID: `ner-targeted-v2`
- Status: selected ALM-020 final candidate; not yet the ALM-034 frozen system
- Architecture: `bert-base-multilingual-cased` token classification
- Immutable base revision: `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`
- Parent release: private `ner-v1.0.0`
- Parent model SHA-256: `fc2d1560862d66f388bb58e83486d77dfbc22f67455c70e388887e33b39c63bd`
- Selected model SHA-256: `95523cfe19fcd729e2113aade5472c518fbc7a3bfcf171077d70cd7158afc0fa`
- NER schema: 10 canonical entity types / 21 BIO labels
- Decoder: first-subword projection followed by frozen `orphan_i_to_b_v1`
- Seed: `42`

The model identifies address-component spans for `JALAN`, `NOMOR`, `RT`,
`RW`, `KELURAHAN`, `KECAMATAN`, `KOTA_KABUPATEN`, `PROVINSI`, `KODEPOS`,
and `DETAIL_LOKASI`. It does not verify that a location exists, resolve an
administrative conflict, normalize values, or provide a calibrated probability.

## Intended use

The candidate is intended as the NER stage of the ALAMATIN MVP for Indonesian
address review. Its spans must be passed to the separate normalization,
administrative-reference, validation, and confirmation stages. User-visible
corrections must not be made solely from this model's output.

Out-of-scope uses include identity inference, surveillance, automated delivery
rejection, verified-location claims, and presenting raw logits as confidence.

## Training and traceability

The candidate starts from the NER v1 checkpoint and is fine-tuned for two
configured epochs on a 7,500-example mixture:

- 4,500 governed synthetic v1 training examples; canonical JSON SHA-256
  `ce84d65b810867bc936a227ead5050dcaafad31d72ed69073507d30fe6392a53`;
- 3,000 train-only targeted synthetic examples; canonical JSON SHA-256
  `ab30d227a513acf590477c1444de23af156ebc3c958f16b1839b0a72b2e2686c`.

The targeted data implements `ALM019-A02`: sparse school-style address
structures, `Kp./Jl./Kec./Kab.` abbreviations, administrative typos, fused
markers, RT/RW, and generic landmarks. It uses generic street/landmark pools
and governed public administrative chains. It does not read or copy real_dev
records, raw private addresses, or sealed-test content.

All four ALM-019 actions remain linked:

- `ALM019-A01`: freeze the BIO decoder/validator;
- `ALM019-A02`: controlled targeted synthetic augmentation;
- `ALM019-A03`: measure rather than assume landmark improvement;
- `ALM019-A04`: do not turn automated-gold disagreements into training labels
  without review.

Exact config, dataset hashes, package versions, and artifact hashes are in
`experiments/ner-final-candidate/run_manifest.json`.

## Checkpoint and candidate selection

Within targeted training, checkpoint selection uses only synthetic dev F1.
Epoch 1 / `checkpoint-469` was selected; epoch 1 and epoch 2 tied on F1, and
the trainer retained the first best checkpoint. `real_dev` was then used only
to compare the already-selected targeted candidate against `ner-v1.0.0`.

The selection policy was written into `configs/ner-final-candidate.json` before
the candidate run. Targeted v2 had to satisfy all four gates:

| Gate | Threshold | Actual | Result |
|---|---:|---:|---|
| Synthetic-dev F1 floor | 0.9943608 | 0.9994521 | pass |
| Minimum real_dev F1 gain | 0.0100 | 0.1063 | pass |
| Minimum critical exact-match gain | 5 examples | 22 examples | pass |
| Maximum invalid raw-BIO examples | 14 | 8 | pass |

No checkpoint or rule was selected using sealed-test inputs or results.

## Evaluation

| Candidate | Synthetic-dev F1 | real_dev micro F1 | real_dev critical exact match | Invalid raw BIO |
|---|---:|---:|---:|---:|
| `ner-v1.0.0` | 0.9993608 | 0.6769231 | 15/70 | 14 |
| `ner-targeted-v2` | 0.9994521 | 0.7832168 | 37/70 | 8 |

Targeted v2 improves real_dev exact-span TP/FP/FN to `224/74/50`, from the
baseline's `198/113/76`. Notable targeted-v2 per-type F1 values are:

- `JALAN`: 0.7619 (baseline 0.6029)
- `KECAMATAN`: 0.8630 (baseline 0.7445)
- `KOTA_KABUPATEN`: 0.9504 (baseline 0.9645)
- `NOMOR`: 0.8636 (baseline 0.7826)
- `RT`: 0.5625 (baseline 0.5455)
- `RW`: 0.6429 (baseline 0.5926)

The small decline for `KOTA_KABUPATEN` is retained because all frozen gates
pass and address-level critical exact match improves by 22/70. Full counts and
per-case predictions are stored under `experiments/ner-targeted-v2-real-dev/`.

## Limitations and risks

- `real_dev` contains only 70 examples. Its result supports development
  selection but is not a population estimate.
- `KELURAHAN` remains weak (F1 0.0909; 18 false positives and 2 false
  negatives), despite reducing false positives from 50 to 18.
- `DETAIL_LOKASI` remains F1 0 with 3 false negatives and 9 false positives;
  `ALM019-A03` therefore did not produce a landmark success claim.
- `real_dev` has no gold `PROVINSI` or `KODEPOS` spans, so those per-type
  metrics are `NA`; synthetic-dev performance is the available regression
  evidence for these types.
- Eight examples still produce invalid raw BIO and require the frozen decoder.
- Typo, abbreviation, RT/RW, conflict, and ambiguous-region slices remain
  difficult. NER output alone cannot safely resolve conflicts or ambiguity.
- The diagnostic CPU timing is not the production latency benchmark required
  by ALM-034.
- The model is not probability-calibrated. Evaluation scores must not be
  relabelled as user-facing confidence.
- Normalization, hierarchy lookup, correction confirmation, PII handling, and
  end-to-end safety are separate system responsibilities.

## Reproduction

From the repository root, with the private parent artifact extracted to the
path in the config:

```powershell
python scripts/generate_targeted_ner_augmentation.py
.\.venv-run\Scripts\python.exe scripts/train_ner_targeted_candidate.py
.\.venv-run\Scripts\python.exe scripts/analyze_ner_real_dev.py `
  --artifact models/ner-targeted-v2/inference `
  --output-dir experiments/ner-targeted-v2-real-dev `
  --checkpoint-name ner-targeted-v2
python scripts/select_ner_final_candidate.py
```

The committed augmentation, comparison, metrics, config, dependency lock, and
run manifest allow every selected input and output checksum to be verified.

The inference package is published in the private internal release
`ner-final-candidate-v1.0.0`. Verify both its archive digest from
`experiments/ner-final-candidate/release_manifest.json` and the selected model
digest above before inference.

## Sealed-test boundary

`real_dev` is comparison-only and never enters training or checkpoint
selection. The training manifest records `sealed_test_accessed: false`; the
comparison record does the same. The sealed test remains under the custodian
procedure and may only be run once after ALM-034 system freeze.

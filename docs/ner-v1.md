# ALAMATIN mBERT NER v1

NER v1 fine-tunes `bert-base-multilingual-cased` on the governed synthetic
train split. The immutable base revision is
`3f076fdb1ab68d5b2880cb87a0886f315b8146f8`; the seed is `42`. Labels use the
canonical 10-entity BIO schema and the first-subword alignment strategy from
`src/alamatin/token_alignment.py`.

## Reproduce training

Use Python 3.12 from the repository root:

```bash
python -m venv .venv-ner-v1
.venv-ner-v1/Scripts/python -m pip install -r requirements/ner-v1.lock
.venv-ner-v1/Scripts/python scripts/train_ner_v1.py --config configs/ner-v1.json
```

On POSIX systems, use `.venv-ner-v1/bin/python`. The runner verifies the
canonical label order and dataset availability, pins the model revision, sets
Python/NumPy/PyTorch/Trainer seeds, labels only the first subword, selects the
best saved checkpoint using synthetic-dev entity F1, and writes inference-only
artifacts under the ignored `models/ner-v1/` directory.

The reference run used Python 3.12.4, PyTorch 2.5.1 CPU, Transformers 5.0.0,
Datasets 5.0.1, Accelerate 1.14.0, Seqeval 1.2.2, and NumPy 2.2.0. Hardware may
change runtime but not the recorded data/model revisions or seed.

## Selected checkpoint and metrics

`checkpoint-1410` (epoch 5) was selected because it had the highest saved
synthetic-dev F1, `0.999360788969044`. Synthetic-test F1 was
`0.9989755052621774`. The complete dev history and metric values are stored in
`experiments/ner-v1/metrics.json`; dataset, package, and checkpoint checksums
are stored in `experiments/ner-v1/run_manifest.json`.

Scores are reported only as evaluation metrics. Probability calibration is
outside ALM-018.

## Inference artifact

The inference package is published as the private internal release
`ner-v1.0.0`. It contains only the model/config/tokenizer and experiment
metadata; optimizer state is intentionally excluded.

```bash
gh release download ner-v1.0.0 \
  --repo yongkytristan/ALAMATIN-internal \
  --pattern ner-v1-inference.tar
```

Verify the archive SHA-256 against
`experiments/ner-v1/release_manifest.json`, extract it, then run:

```bash
python scripts/verify_ner_v1_artifact.py \
  --artifact PATH_TO_EXTRACTED_ARTIFACT \
  --dataset data/synthetic/test.json
```

The verifier loads the checkpoint, checks all 21 BIO labels, performs a smoke
prediction, and proves that the checkpoint emits each of the 10 canonical
entity types on governed synthetic examples. Raw logits are not presented as
a user-facing probability.

# libpostal address-parser baseline (ALM-016)

- Baseline ID: `libpostal_v1`
- Canonical adapter: `src/alamatin/libpostal_baseline.py`
- Runner: `scripts/run_libpostal_baseline.py`
- ALAMATIN NER schema: `1.0.0`

## What this is

This baseline adapts the output of [libpostal](https://github.com/openvenues/libpostal) to the canonical ALAMATIN NER schema so that it can be evaluated with the same exact-span metrics used by the regex baseline and the future fine-tuned NER model.

libpostal is treated as an external, general-purpose address parser. The adapter does not use ALAMATIN reference data, gold labels, administrative hierarchy, or dataset-specific rules to correct libpostal predictions.

The purpose of this baseline is therefore not to make libpostal behave like an Indonesia-specific ALAMATIN parser. It provides an independently developed external baseline whose strengths and incompatibilities can be measured directly.

## Installation and versioning

libpostal requires both the native libpostal library and a compatible Python binding.

The exact native-library revision/build configuration and Python-binding version used for reported benchmark results must be recorded before those results are treated as reproducible evidence.

### Recorded environment

The current ALM-016 development environment is recorded below. Update this
record whenever a benchmark is run with a different environment.

#### Native libpostal

- Revision/tag: `v1.1.4` (Homebrew `libpostal` formula)
- Build flags: default Homebrew arm64 Sonoma bottle; no custom native build flags
- Data model: default libpostal model
- Installation method: Homebrew (`brew install libpostal`)

#### Python binding

- Package: `postal`
- Version/revision: `1.1.11`

#### Operating system and runtime

- OS: macOS `14.7.1` (build `23H222`)
- Architecture: `arm64`
- Python: `3.11.8`

Development environments that do not have libpostal installed may still run adapter unit tests by injecting a deterministic fake parser. Real benchmark execution requires the native parser.

For MacOS

```bash
brew install libpostal
python3 -m venv Env
source Env/bin/activate
```

After this, the installation of postal on pip will not work. You should follow these steps:

```bash
export CFLAGS="-I$(brew --prefix libpostal)/include"
export LDFLAGS="-L$(brew --prefix libpostal)/lib"
export PKG_CONFIG_PATH="$(brew --prefix libpostal)/lib/pkgconfig"
pip install postal==1.1.11
```

## Output mapping

ALAMATIN uses the following 10 canonical entity types:

- `JALAN`
- `NOMOR`
- `RT`
- `RW`
- `KELURAHAN`
- `KECAMATAN`
- `KOTA_KABUPATEN`
- `PROVINSI`
- `KODEPOS`
- `DETAIL_LOKASI`

The initial libpostal mapping is intentionally conservative:

| libpostal label | ALAMATIN entity  | Policy                                 |
| --------------- | ---------------- | -------------------------------------- |
| `road`          | `JALAN`          | mapped                                 |
| `house_number`  | `NOMOR`          | mapped                                 |
| `city`          | `KOTA_KABUPATEN` | mapped                                 |
| `state`         | `PROVINSI`       | mapped                                 |
| `postcode`      | `KODEPOS`        | mapped                                 |
| `house`         | —                | unsupported                            |
| `suburb`        | —                | unsupported                            |
| `city_district` | —                | unsupported                            |
| other labels    | —                | unsupported unless explicitly reviewed |

Unsupported labels are left as `O`. The adapter must not infer an ALAMATIN entity from the surface text merely because a plausible Indonesia-specific interpretation exists.

This mapping may only be changed through an explicit documented decision. It must not be tuned against sealed-test answers.

## Why some libpostal labels are intentionally unsupported

Smoke testing on synthetic Indonesian addresses showed that several libpostal administrative labels do not have stable one-to-one semantics with the ALAMATIN schema.

For example:

```text
Input:
Kp. Cihaurseah RT 03 RW 04, Kec. Jampangkulon, Kab. Sukabumi, Jawa Barat
```

libpostal produced:

```text
kp. cihaurseah                   -> house
rt 03                            -> suburb
rw                               -> city_district
04 kec. jampangkulon kab.        -> road
sukabumi                         -> city
jawa barat                       -> state
```

Mapping `suburb` directly to `KELURAHAN` or `city_district` directly to `KECAMATAN` would therefore create an Indonesia-specific reinterpretation that is not supported by libpostal's actual prediction.

Those labels remain unsupported in `libpostal_v1`.

Similarly, `house` is not mapped to `DETAIL_LOKASI` or `JALAN` because observed kampung/dusun expressions and destination-like components do not provide a stable one-to-one semantic equivalence.

## Observed Indonesian parsing limitations

Initial smoke tests show that libpostal can recognize some broad components correctly while merging other Indonesian administrative components into unrelated labels.

Example:

```text
Input:
Jl. Asia Afrika No. 12, Braga, Sumur Bandung, Kota Bandung,
Jawa Barat 40111
```

Observed parse:

```text
jl. asia afrika          -> road
no.                      -> house_number
12 braga sumur bandung   -> road
kota bandung             -> city
jawa barat               -> state
40111                     -> postcode
```

Another example:

```text
Input:
Jl. Diponegoro No. 5, Kel. Citarum, Kec. Bandung Wetan,
Kota Bandung, Jawa Barat 40115
```

Observed parse:

```text
jl. diponegoro                    -> road
no. 5                             -> house_number
kel. citarum kec. bandung wetan   -> road
kota bandung                      -> city
jawa barat                        -> state
40115                              -> postcode
```

These outputs are not corrected by the ALAMATIN adapter. If libpostal predicts a large span as `road`, the mapped baseline predicts that span as `JALAN`, even when ALAMATIN gold semantics differ.

This behavior is intentional. A baseline must preserve the external parser's actual behavior rather than silently incorporate ALAMATIN-specific knowledge.

## Token alignment

libpostal operates on reconstructed address text, while ALAMATIN evaluation operates on the canonical token sequence and BIO labels.

The adapter therefore performs the following steps:

1. Reconstruct address text from the canonical ALAMATIN tokens.
2. Run libpostal.
3. Map supported libpostal labels to ALAMATIN entity types.
4. Align each returned component back to a contiguous span of the original tokens.
5. Emit canonical `B-*` and `I-*` labels for the aligned span.
6. Leave unsupported, unaligned, or conflicting components as `O`.

Alignment normalization may account for representation differences introduced by libpostal, such as case differences or punctuation normalization.

Alignment normalization exists only to recover the source-token span. It must not change the semantic label predicted by libpostal.

When the adapter cannot align a component safely, it must prefer no prediction over a guessed span.

## Baseline purity

`libpostal_v1` must not use:

- Jawa Barat administrative hierarchy lookup;
- postal-code reference data;
- alias dictionaries derived from ALAMATIN reference data;
- gold labels;
- `real_dev` answers to introduce special-case mappings;
- sealed-test examples or results;
- regex-baseline predictions;
- fine-tuned model predictions.

For example, this is not allowed:

```text
libpostal: Sukabumi -> city

ALAMATIN hierarchy lookup:
"Sukabumi is actually ..."

adapter changes label based on hierarchy
```

Such a system would be a hybrid `libpostal + ALAMATIN` pipeline rather than the ALM-016 external baseline.

## Evaluation

The runner evaluates libpostal predictions using the same canonical evaluator as the other ALAMATIN NER systems.

At minimum, reports contain:

- example count;
- exact-span micro precision;
- exact-span micro recall;
- exact-span micro F1;
- per-entity precision, recall, and F1;
- per-address inference latency summary.

The benchmark must be run only on development/test splits whose access is allowed by `docs/evaluation_protocol.md`.

The sealed real test must not be used during ALM-016 implementation or mapping decisions.

## Results

Results below use the recorded environment above and exact-span evaluation.

| Dataset                                                   | Precision |  Recall |      F1 |
| --------------------------------------------------------- | --------: | ------: | ------: |
| `synthetic_dev` (`data/synthetic/val.json`, 750 examples) |    52.02% |  28.73% |  37.01% |
| `real_dev`                                                |   Not run | Not run | Not run |

Synthetic-dev inference latency was 0.19 ms at p50 and 0.70 ms at p95 across
750 examples.

### Per-entity observations

- `JALAN`: 46.04% precision, 72.80% recall, and 56.40% F1 (546 true positives). It has relatively strong recall, but 640 false positives indicate that libpostal frequently assigns overly broad spans to `road`.
- `NOMOR`: 81.69% precision, 67.20% recall, and 73.74% F1 (504 true positives), the strongest non-postcode mapped entity.
- `RT`: no true positives; all 439 gold spans were missed because `RT` has no supported direct libpostal-to-ALAMATIN mapping.
- `RW`: no true positives; all 439 gold spans were missed because `RW` has no supported direct libpostal-to-ALAMATIN mapping.
- `KELURAHAN`: no true positives; all 750 gold spans were missed because `suburb` is intentionally unsupported.
- `KECAMATAN`: no true positives; all 750 gold spans were missed because `city_district` is intentionally unsupported.
- `KOTA_KABUPATEN`: 7.73% precision, 6.80% recall, and 7.23% F1 (51 true positives), indicating substantial mismatch between libpostal's `city` interpretation and the ALAMATIN schema.
- `PROVINSI`: 57.98% precision, 34.60% recall, and 43.34% F1 (109 true positives).
- `KODEPOS`: 97.32% precision, 96.03% recall, and 96.67% F1 (363 true positives), making it the most reliable mapped entity in this run.
- `DETAIL_LOKASI`: no true positives; all 155 gold spans were missed because there is no supported direct mapping.

## Expected incompatibilities

The following limitations are expected and should be reported as measured behavior rather than treated automatically as adapter bugs:

- no stable direct mapping for Indonesian `RT`;
- no stable direct mapping for Indonesian `RW`;
- no reliable direct mapping for `KELURAHAN`;
- no reliable direct mapping for `KECAMATAN`;
- no stable mapping for `DETAIL_LOKASI`;
- merging multiple Indonesian components into a single `road` prediction;
- normalization of punctuation or component surface forms;
- different administrative granularity from the ALAMATIN schema.

The final benchmark report should separate:

1. external parser behavior;
2. mapping incompatibility;
3. alignment failure;
4. adapter implementation error.

Only the last category should be fixed by changing adapter code without a documented mapping decision.

## Reproducing the benchmark

After native libpostal and its Python binding are installed:

```bash
python scripts/run_libpostal_baseline.py \
  --dataset data/synthetic/val.json
```

To save a report:

```bash
python scripts/run_libpostal_baseline.py \
  --dataset data/synthetic/val.json \
  --output data/interim/baselines/libpostal-synthetic-dev.json
```

Additional allowed development splits may be evaluated using the same runner.

Benchmark numbers must only be added to this document after the implementation, mapping, dependency versions, and evaluation command have been reviewed.

## Current status

The `libpostal_v1` adapter, runner, conservative label mapping, and
synthetic-development evaluation are implemented.

The initial `synthetic_dev` result is reported below. The result must
be regenerated after every mapping-policy change before it is used as
evaluation evidence.

Evaluation on additional allowed development splits remains separate
work. The sealed real test must not be opened for ALM-016 development.

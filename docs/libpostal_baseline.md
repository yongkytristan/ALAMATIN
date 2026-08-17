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

Development environments that do not have libpostal installed may still run adapter unit tests by injecting a deterministic fake parser. Real benchmark execution requires the native parser.

For MacOS

```bash
brew install libpostal
python3 -m venv Env
source Env/activate/bin
```

After this, the installation of postal on pip will not work. You should follow these steps:

```bash
export CFLAGS="-I$(brew --prefix libpostal)/include"
export LDFLAGS="-L$(brew --prefix libpostal)/lib"
export PKG_CONFIG_PATH="$(brew --prefix libpostal)/lib/pkgconfig"
pip install postal
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

The adapter and runner are being implemented for ALM-016.

The initial Indonesia-specific smoke test has been completed and informed the conservative mapping policy documented above.

Full development-set metrics and latency results are not yet reported. They must not be replaced by estimates or placeholder performance claims.

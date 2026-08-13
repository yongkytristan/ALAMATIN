from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from alamatin.label_schema import validate_bio_sequence  # noqa: E402
from generate_synthetic_addresses import (  # noqa: E402
    DEFAULT_REFERENCE,
    GeneratorError,
    _check_no_leakage,
    build_base_address,
    build_dataset,
    render_variant,
)


SAMPLE_CHAINS = [
    {
        "village_code": "32.01.01.1001",
        "province_name": "JAWA BARAT",
        "city_name": "KAB. BOGOR",
        "district_name": "CIBINONG",
        "village_name": "PONDOK RAJEG",
        "postal_code": "16913",
    },
    {
        "village_code": "32.04.02.1002",
        "province_name": "JAWA BARAT",
        "city_name": "KOTA BANDUNG",
        "district_name": "SUMUR BANDUNG",
        "village_name": "BRAGA",
        "postal_code": "40111",
    },
]


class GenerateSyntheticAddressesTest(unittest.TestCase):
    def test_default_reference_is_the_public_governed_file(self) -> None:
        self.assertEqual(
            DEFAULT_REFERENCE,
            ROOT / "data" / "final" / "jabar-postal-app-lookup.csv",
        )
        self.assertNotIn("raw", DEFAULT_REFERENCE.parts)
        self.assertNotIn("private", DEFAULT_REFERENCE.parts)

    def test_build_dataset_is_reproducible_from_the_same_seed(self) -> None:
        first = build_dataset(SAMPLE_CHAINS, seed=42, train_bases=10, val_bases=3, test_bases=3, variants_per_base=2)
        second = build_dataset(SAMPLE_CHAINS, seed=42, train_bases=10, val_bases=3, test_bases=3, variants_per_base=2)
        self.assertEqual(first, second)

    def test_different_seed_changes_output(self) -> None:
        first = build_dataset(SAMPLE_CHAINS, seed=1, train_bases=10, val_bases=3, test_bases=3, variants_per_base=2)
        second = build_dataset(SAMPLE_CHAINS, seed=2, train_bases=10, val_bases=3, test_bases=3, variants_per_base=2)
        self.assertNotEqual(first, second)

    def test_every_generated_example_has_a_valid_bio_sequence(self) -> None:
        splits = build_dataset(SAMPLE_CHAINS, seed=7, train_bases=25, val_bases=5, test_bases=5, variants_per_base=3)
        checked = 0
        for examples in splits.values():
            for example in examples:
                valid, reason = validate_bio_sequence(example["labels"])
                self.assertTrue(valid, reason)
                self.assertEqual(len(example["tokens"]), len(example["labels"]))
                checked += 1
        self.assertGreater(checked, 0)

    def test_variants_of_one_base_share_base_id_and_differ_in_text(self) -> None:
        import random

        rng = random.Random(99)
        base = build_base_address(0, SAMPLE_CHAINS[0], rng)
        variants = [render_variant(base, random.Random(seed)) for seed in range(5)]
        self.assertTrue(all(v["base_id"] == 0 for v in variants))
        rendered = {" ".join(v["tokens"]) for v in variants}
        self.assertGreater(len(rendered), 1)

    def test_no_leakage_check_passes_for_a_clean_split_and_fails_for_a_leak(self) -> None:
        clean = {
            "train": [{"base_id": 1}, {"base_id": 1}],
            "val": [{"base_id": 2}],
        }
        _check_no_leakage(clean)  # should not raise

        leaking = {
            "train": [{"base_id": 1}],
            "val": [{"base_id": 1}],
        }
        with self.assertRaises(GeneratorError):
            _check_no_leakage(leaking)

    def test_noise_categories_cover_multiple_kinds_at_reasonable_scale(self) -> None:
        splits = build_dataset(SAMPLE_CHAINS, seed=11, train_bases=80, val_bases=10, test_bases=10, variants_per_base=3)
        categories: set[str] = set()
        for example in splits["train"]:
            categories.update(example["categories"])
        expected = {"abbreviation", "typo", "missing_provinsi", "missing_kodepos", "separator"}
        self.assertTrue(expected.issubset(categories), categories)

    def test_administrative_conflict_rows_still_label_the_postal_code(self) -> None:
        splits = build_dataset(SAMPLE_CHAINS, seed=5, train_bases=150, val_bases=1, test_bases=1, variants_per_base=1)
        conflict_examples = [
            example for example in splits["train"] if "admin_conflict" in example["categories"]
        ]
        self.assertGreater(len(conflict_examples), 0)
        for example in conflict_examples:
            self.assertIn("B-KODEPOS", example["labels"])

    def test_cli_writes_reproducible_split_files_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            args = [
                sys.executable,
                "scripts/generate_synthetic_addresses.py",
                "--train-bases", "5",
                "--val-bases", "2",
                "--test-bases", "2",
                "--variants-per-base", "2",
                "--seed", "123",
                "--output-dir", output_dir,
            ]
            result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            output_path = Path(output_dir)
            train = json.loads((output_path / "train.json").read_text(encoding="utf-8"))
            summary = json.loads((output_path / "generation-summary.json").read_text(encoding="utf-8"))

            self.assertEqual(len(train["examples"]), 10)
            self.assertEqual(summary["seed"], 123)
            self.assertEqual(summary["split_example_counts"]["train"], 10)
            self.assertIn("reference_sha256", summary)
            self.assertIn("no_raw_private_address", summary)


if __name__ == "__main__":
    unittest.main()

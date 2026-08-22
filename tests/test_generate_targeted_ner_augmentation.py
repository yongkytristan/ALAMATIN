from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_targeted_ner_augmentation",
    ROOT / "scripts" / "generate_targeted_ner_augmentation.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TargetedNerAugmentationTest(unittest.TestCase):
    CHAINS = [
        {
            "village_code": "32.01.01.2001",
            "district_name": "CILANDAK",
            "city_name": "KAB. BANDUNG",
        }
    ]

    def test_is_deterministic_and_covers_every_frozen_pattern(self) -> None:
        first = MODULE.build_examples(self.CHAINS, 80, 42)
        second = MODULE.build_examples(self.CHAINS, 80, 42)
        self.assertEqual(first, second)
        categories = {category for item in first for category in item["categories"]}
        self.assertLessEqual(set(MODULE.PATTERNS), categories)

    def test_sparse_examples_never_introduce_kelurahan_postcode_or_province(self) -> None:
        examples = MODULE.build_examples(self.CHAINS, 80, 7)
        labels = {label for item in examples for label in item["labels"]}
        self.assertFalse(any("KELURAHAN" in label for label in labels))
        self.assertFalse(any("KODEPOS" in label for label in labels))
        self.assertFalse(any("PROVINSI" in label for label in labels))

    def test_namespaces_and_traceability_do_not_copy_real_dev_ids(self) -> None:
        examples = MODULE.build_examples(self.CHAINS, 8, 9)
        self.assertTrue(all(item["id"].startswith("TGT-") for item in examples))
        self.assertTrue(
            all("alm019_a02" in item["categories"] for item in examples)
        )
        self.assertTrue(all("base_address_id" not in item for item in examples))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "build_evaluation_splits", ROOT / "scripts" / "build_evaluation_splits.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _examples(kabupaten_counts: dict[str, int]) -> tuple[list[dict], dict[str, str]]:
    examples = []
    kabupaten_by_id = {}
    for kabupaten, count in kabupaten_counts.items():
        for i in range(count):
            base_id = f"{kabupaten}_{i}"
            examples.append({"base_address_id": base_id, "tokens": ["x"], "labels": ["O"]})
            kabupaten_by_id[base_id] = kabupaten
    return examples, kabupaten_by_id


class StratifiedSplitTest(unittest.TestCase):
    def test_totals_hit_the_exact_target(self) -> None:
        examples, kabupaten_by_id = _examples({"A": 50, "B": 50, "C": 50, "D": 50})
        real_dev, sealed = MODULE.stratified_split(examples, kabupaten_by_id, 70, random.Random(1))
        self.assertEqual(len(real_dev), 70)
        self.assertEqual(len(sealed), 130)

    def test_every_example_lands_in_exactly_one_split(self) -> None:
        examples, kabupaten_by_id = _examples({"A": 20, "B": 30})
        real_dev, sealed = MODULE.stratified_split(examples, kabupaten_by_id, 20, random.Random(2))
        real_dev_ids = {e["base_address_id"] for e in real_dev}
        sealed_ids = {e["base_address_id"] for e in sealed}
        self.assertEqual(real_dev_ids & sealed_ids, set())
        self.assertEqual(real_dev_ids | sealed_ids, {e["base_address_id"] for e in examples})

    def test_raises_when_kabupaten_is_missing(self) -> None:
        with self.assertRaises(MODULE.SplitBuildError):
            MODULE.stratified_split(
                [{"base_address_id": "x", "tokens": [], "labels": []}], {}, 1, random.Random(1)
            )

    def test_preserves_rough_proportion_per_kabupaten(self) -> None:
        examples, kabupaten_by_id = _examples({"A": 100, "B": 100})
        real_dev, _ = MODULE.stratified_split(examples, kabupaten_by_id, 100, random.Random(3))
        from_a = sum(1 for e in real_dev if kabupaten_by_id[e["base_address_id"]] == "A")
        from_b = sum(1 for e in real_dev if kabupaten_by_id[e["base_address_id"]] == "B")
        self.assertEqual(from_a, 50)
        self.assertEqual(from_b, 50)


if __name__ == "__main__":
    unittest.main()

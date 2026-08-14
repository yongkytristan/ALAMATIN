from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "sample_double_annotation", ROOT / "scripts" / "sample_double_annotation.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _example(base_id: str, flags: list[str]) -> dict:
    return {"base_address_id": base_id, "tokens": ["Jl.", "Mawar"], "labels": ["B-JALAN", "I-JALAN"], "flags": flags}


class SelectSampleTest(unittest.TestCase):
    def test_raises_on_empty_pool(self) -> None:
        with self.assertRaises(MODULE.SamplingError):
            MODULE.select_sample([], target=5, rng=random.Random(1))

    def test_always_includes_every_flagged_example(self) -> None:
        examples = [_example(f"A{i}", ["needs_review"]) for i in range(5)] + [
            _example(f"B{i}", []) for i in range(20)
        ]
        sample = MODULE.select_sample(examples, target=10, rng=random.Random(1))
        flagged_ids = {f"A{i}" for i in range(5)}
        self.assertTrue(flagged_ids.issubset({e["base_address_id"] for e in sample}))
        self.assertEqual(len(sample), 10)

    def test_includes_all_flagged_even_if_more_than_target(self) -> None:
        examples = [_example(f"A{i}", ["needs_review"]) for i in range(8)] + [_example("B0", [])]
        sample = MODULE.select_sample(examples, target=5, rng=random.Random(1))
        self.assertEqual(len(sample), 8)

    def test_is_deterministic_for_the_same_seed(self) -> None:
        examples = [_example(f"B{i}", []) for i in range(30)]
        first = MODULE.select_sample(list(examples), target=10, rng=random.Random(9))
        second = MODULE.select_sample(list(examples), target=10, rng=random.Random(9))
        self.assertEqual([e["base_address_id"] for e in first], [e["base_address_id"] for e in second])


class CliTest(unittest.TestCase):
    def test_cli_writes_a_blind_worksheet_with_no_candidate_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidates_path = Path(directory) / "bio-candidates.json"
            payload = {
                "examples": [_example(f"B{i}", ["needs_review"] if i < 2 else []) for i in range(10)]
            }
            candidates_path.write_text(json.dumps(payload), encoding="utf-8")

            worksheet_path = Path(directory) / "worksheet.csv"
            manifest_path = Path(directory) / "manifest.json"
            args = [
                sys.executable,
                "scripts/sample_double_annotation.py",
                "--candidates", str(candidates_path),
                "--target", "5",
                "--seed", "3",
                "--worksheet", str(worksheet_path),
                "--manifest", str(manifest_path),
            ]
            result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            content = worksheet_path.read_text(encoding="utf-8")
            self.assertNotIn("B-JALAN", content)
            self.assertIn("indexed_tokens", content)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["sample_size"], 5)
            self.assertEqual(manifest["flagged_in_sample"], 2)


if __name__ == "__main__":
    unittest.main()

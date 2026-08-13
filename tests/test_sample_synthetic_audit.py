from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sample_synthetic_audit import AuditSampleError, stratified_sample  # noqa: E402


def _example(example_id: str, categories: list[str]) -> dict:
    return {"id": example_id, "categories": categories, "tokens": ["Jl.", "Mawar"], "labels": ["B-JALAN", "I-JALAN"]}


class SampleSyntheticAuditTest(unittest.TestCase):
    def test_sample_covers_every_category_when_enough_examples_exist(self) -> None:
        examples = [
            _example("A", ["abbreviation"]),
            _example("B", ["typo"]),
            _example("C", ["separator"]),
            _example("D", ["abbreviation", "typo"]),
            _example("E", ["gang"]),
        ]
        sample = stratified_sample(examples, sample_size=3, rng=random.Random(1))
        covered = {category for example in sample for category in example["categories"]}
        self.assertGreaterEqual(len(covered), 3)

    def test_sample_is_deterministic_for_the_same_seed(self) -> None:
        examples = [_example(str(i), ["abbreviation", "typo"] if i % 2 else ["separator"]) for i in range(30)]
        first = stratified_sample(examples, sample_size=10, rng=random.Random(5))
        second = stratified_sample(examples, sample_size=10, rng=random.Random(5))
        self.assertEqual([e["id"] for e in first], [e["id"] for e in second])

    def test_empty_examples_raise(self) -> None:
        with self.assertRaises(AuditSampleError):
            stratified_sample([], sample_size=5, rng=random.Random(1))

    def test_cli_writes_a_sample_file_with_full_category_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir)
            gen_args = [
                sys.executable,
                "scripts/generate_synthetic_addresses.py",
                "--train-bases", "20", "--val-bases", "5", "--test-bases", "5",
                "--variants-per-base", "3", "--seed", "9",
                "--output-dir", str(output_path),
            ]
            gen_result = subprocess.run(gen_args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(gen_result.returncode, 0, gen_result.stderr)

            sample_output = output_path / "audit-sample.json"
            audit_args = [
                sys.executable,
                "scripts/sample_synthetic_audit.py",
                "--split-dir", str(output_path),
                "--sample-size", "20",
                "--seed", "3",
                "--output", str(sample_output),
            ]
            audit_result = subprocess.run(audit_args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(audit_result.returncode, 0, audit_result.stderr)

            payload = json.loads(sample_output.read_text(encoding="utf-8"))
            self.assertEqual(payload["sample_size"], 20)
            self.assertGreater(len(payload["category_coverage"]), 1)


if __name__ == "__main__":
    unittest.main()

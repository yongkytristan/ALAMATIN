"""Tests for the real-data head-to-head comparison.

The comparison's whole claim is that its rows are commensurable. These tests
attack that claim from three sides:

1. **Cross-check against independent artifacts.** Every model row is
   recomputed here from raw predictions; the recorded `metrics.json` produced
   months earlier by a different script must agree. If this file's metric code
   drifted, the agreement breaks and these tests fail rather than quietly
   publishing a different definition under the same name.
2. **Refusal, not footnoting.** A row whose predictions were made against a
   different split must be rejected outright.
3. **No invented rows.** An approach that cannot execute must appear as
   `not_measured` with a reason, and must never carry a number.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "compare_approaches_real_dev.py"
    spec = importlib.util.spec_from_file_location("compare_approaches_real_dev", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = _load()

SPLIT_PRESENT = compare.SPLIT.is_file()
skip_without_data = unittest.skipUnless(
    SPLIT_PRESENT, "real_dev split is governed data; see data/sources.md"
)


@skip_without_data
class SplitIntegrityTest(unittest.TestCase):
    def test_every_model_row_used_the_same_split(self) -> None:
        _, digest = compare.load_split()
        for _, relative, _ in compare.MODEL_ROWS:
            path = ROOT / relative / "predictions.json"
            if not path.is_file():
                continue
            with self.subTest(artifact=relative):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    payload["dataset_canonical_json_sha256"],
                    digest,
                    f"{relative} was measured on a different dataset",
                )

    def test_a_foreign_split_is_refused_not_footnoted(self) -> None:
        examples, digest = compare.load_split()
        directory = ROOT / compare.MODEL_ROWS[0][1]
        if not (directory / "predictions.json").is_file():
            self.skipTest("no predictions artifact present")
        with self.assertRaises(SystemExit) as caught:
            compare.read_model_predictions(directory, examples, "0" * 64)
        self.assertIn("Refusing", str(caught.exception))
        # And the real digest still works, so the guard is not simply always-on.
        labels, _ = compare.read_model_predictions(directory, examples, digest)
        self.assertEqual(len(labels), len(examples))


@skip_without_data
class RecomputationAgreesWithRecordedMetricsTest(unittest.TestCase):
    """The independent cross-check that makes the table trustworthy."""

    def test_model_rows_reproduce_their_recorded_metrics(self) -> None:
        examples, digest = compare.load_split()
        gold = [list(example["labels"]) for example in examples]

        for name, relative, _ in compare.MODEL_ROWS:
            recorded_path = ROOT / relative / "metrics.json"
            predictions_path = ROOT / relative / "predictions.json"
            if not (recorded_path.is_file() and predictions_path.is_file()):
                continue
            with self.subTest(approach=name):
                recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
                predicted, _ = compare.read_model_predictions(
                    ROOT / relative, examples, digest
                )
                fresh = compare.measure(gold, predicted)

                self.assertAlmostEqual(
                    fresh["entity"]["f1"], recorded["overall"]["f1"], places=12
                )
                self.assertEqual(
                    fresh["entity"]["true_positive"], recorded["overall"]["true_positive"]
                )
                self.assertEqual(
                    fresh["critical_exact_match"]["numerator"],
                    recorded["critical_exact_match"]["numerator"],
                )
                self.assertEqual(
                    fresh["critical_exact_match"]["denominator"],
                    recorded["critical_exact_match"]["denominator"],
                )

    def test_regex_row_reproduces_its_recorded_baseline_file(self) -> None:
        recorded_path = (
            ROOT / "data" / "interim" / "baselines" / "regex_baseline_v1_2-real_dev.json"
        )
        if not recorded_path.is_file():
            self.skipTest("recorded regex baseline file is not present")
        recorded = json.loads(recorded_path.read_text(encoding="utf-8"))

        examples, _ = compare.load_split()
        gold = [list(example["labels"]) for example in examples]
        predicted, _ = compare.run_regex(examples)
        fresh = compare.measure(gold, predicted)

        self.assertAlmostEqual(
            fresh["entity"]["f1"], recorded["overall"]["f1"], places=12
        )
        self.assertEqual(
            fresh["entity"]["true_positive"], recorded["overall"]["true_positive"]
        )


@skip_without_data
class ReportShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.report = compare.build()

    def test_unmeasured_rows_carry_a_reason_and_no_numbers(self) -> None:
        unmeasured = [row for row in self.report["rows"] if not row["measured"]]
        for row in unmeasured:
            with self.subTest(approach=row["approach"]):
                self.assertTrue(row["reason"].strip())
                self.assertIsNone(row["entity"])
                self.assertIsNone(row["critical_exact_match"])

    def test_ranking_contains_only_measured_rows(self) -> None:
        measured = {row["approach"] for row in self.report["rows"] if row["measured"]}
        self.assertEqual(set(self.report["ranking_by_entity_f1"]), measured)
        self.assertTrue(measured, "no approach was measured at all")

    def test_ranking_is_ordered_by_entity_f1(self) -> None:
        scores = {
            row["approach"]: row["entity"]["f1"]
            for row in self.report["rows"]
            if row["measured"]
        }
        ordered = [scores[name] for name in self.report["ranking_by_entity_f1"]]
        self.assertEqual(ordered, sorted(ordered, reverse=True))

    def test_the_sealed_set_is_not_used(self) -> None:
        # Re-running approaches against the sealed set would void ALM-035.
        self.assertFalse(self.report["method"]["sealed_set_used"])
        self.assertIn("one-time", self.report["method"]["sealed_set_reason"])
        self.assertEqual(self.report["split"]["name"], "real_dev")

    def test_mismatched_label_lengths_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compare.measure([["O", "O"]], [["O"]])
        with self.assertRaises(ValueError):
            compare.measure([["O"], ["O"]], [["O"]])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "run_sealed_evaluation", ROOT / "scripts" / "run_sealed_evaluation.py"
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)

RESULTS = ROOT / "experiments" / "sealed-evaluation" / "results.json"
RELEASE_MANIFEST = ROOT / "experiments" / "release-candidate" / "manifest.json"


class ResultsExistTest(unittest.TestCase):
    def test_the_sealed_result_is_published(self) -> None:
        self.assertTrue(
            RESULTS.is_file(),
            "the sealed result must be an artifact, not a number quoted in prose",
        )


@unittest.skipUnless(RESULTS.is_file(), "no sealed result published")
class PublishedResultTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(RESULTS.read_text(encoding="utf-8"))

    def test_no_sealed_content_is_published(self) -> None:
        # The whole point of the split: aggregates here, per-example content in
        # the custodian's restricted location only.
        serialized = json.dumps(self.report)
        for forbidden in (
            "tokens",
            "gold_labels",
            "predicted_labels",
            "base_address_id",
            "examples",
        ):
            with self.subTest(key=forbidden):
                self.assertNotIn(f'"{forbidden}"', serialized)
        self.assertFalse(self.report["dataset"]["content_published"])

    def test_the_run_is_attributable_and_traceable(self) -> None:
        run = self.report["run"]
        for field in ("started_at_utc", "operator", "commit", "python", "platform"):
            with self.subTest(field=field):
                self.assertTrue(str(run[field]).strip())
        self.assertEqual(run["openings_used"], 1)

    def test_the_result_names_the_dataset_it_measured(self) -> None:
        dataset = self.report["dataset"]
        self.assertEqual(dataset["split_version"], "sealed_real_test_v1")
        self.assertEqual(dataset["example_count"], 130)
        self.assertEqual(len(dataset["canonical_sha256"]), 64)
        self.assertEqual(dataset["per_item_digests_verified"], 130)

    def test_the_system_versions_match_the_frozen_release(self) -> None:
        frozen = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(self.report["system"], frozen["declared_versions"])

    def test_the_release_manifest_records_the_opening(self) -> None:
        frozen = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
        self.assertTrue(frozen["sealed_test"]["opened"])
        self.assertEqual(frozen["sealed_test"]["authorized_openings"], 1)

    def test_every_required_metric_is_present(self) -> None:
        metrics = self.report["metrics"]
        for key in (
            "entity_overall",
            "entity_by_type",
            "critical_exact_match",
            "conflict_or_ambiguity_recall",
            "false_correction_rate",
            "by_annotation_provenance",
            "extraction_latency_ms",
        ):
            with self.subTest(metric=key):
                self.assertIn(key, metrics)

    def test_derived_metrics_state_their_definition(self) -> None:
        # A recall figure whose definition is unstated cannot be checked by a
        # reader, and cannot be reproduced.
        metrics = self.report["metrics"]
        self.assertIn("definition", metrics["conflict_or_ambiguity_recall"])
        self.assertIn("definition", metrics["false_correction_rate"])

    def test_the_latency_protocol_is_recorded(self) -> None:
        latency = self.report["metrics"]["extraction_latency_ms"]
        self.assertIn("perf_counter", latency["protocol"])
        self.assertEqual(latency["sample_count"], 130)

    def test_entity_counts_are_internally_consistent(self) -> None:
        overall = self.report["metrics"]["entity_overall"]
        by_type = self.report["metrics"]["entity_by_type"]
        for field in ("true_positive", "false_positive", "false_negative"):
            with self.subTest(field=field):
                self.assertEqual(
                    overall[field],
                    sum(value[field] for value in by_type.values()),
                    "per-type counts must sum to the overall count",
                )

    def test_status_counts_cover_every_example(self) -> None:
        counts = self.report["metrics"]["quality_gate_status_counts"]
        self.assertEqual(sum(counts.values()), self.report["dataset"]["example_count"])

    def test_the_evaluator_correction_policy_is_recorded(self) -> None:
        self.assertIn("never selected quietly", self.report["evaluator_correction_policy"])
        self.assertIsInstance(self.report["evaluator_corrections"], list)


class OneTimeGuardTest(unittest.TestCase):
    """A second opening must not be possible by accident."""

    def test_a_published_result_blocks_another_run(self) -> None:
        self.assertTrue(RESULTS.is_file())
        source = (ROOT / "scripts" / "run_sealed_evaluation.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("already exists", source)
        self.assertIn("Only one opening is authorized", source)

    def test_an_operator_is_required(self) -> None:
        self.assertIn("--operator is required", (ROOT / "scripts" / "run_sealed_evaluation.py").read_text(encoding="utf-8"))

    def test_the_runner_refuses_without_governed_inputs(self) -> None:
        # A public clone has neither the sealed dataset nor the boundary
        # manifest; the failure must say so rather than look like a bug. The
        # path is repointed rather than relying on this checkout, so the test is
        # deterministic wherever it runs.
        original = RUNNER.SEALED_DATASET
        RUNNER.SEALED_DATASET = ROOT / "data" / "private" / "does-not-exist.json"
        try:
            with self.assertRaises(RUNNER.SealedRunError) as caught:
                RUNNER.verify_manifests()
        finally:
            RUNNER.SEALED_DATASET = original
        message = str(caught.exception).lower()
        self.assertIn("custodian", message)
        self.assertIn("public clone", message)


if __name__ == "__main__":
    unittest.main()

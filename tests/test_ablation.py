from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "run_ablation", ROOT / "scripts" / "run_ablation.py"
)
assert SPEC and SPEC.loader
ABLATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ABLATION
SPEC.loader.exec_module(ABLATION)

RESULTS = ROOT / "experiments" / "ablation" / "results.json"
SEALED_RESULTS = ROOT / "experiments" / "sealed-evaluation" / "results.json"


class ResultsExistTest(unittest.TestCase):
    def test_the_ablation_result_is_published(self) -> None:
        self.assertTrue(RESULTS.is_file())


@unittest.skipUnless(RESULTS.is_file(), "no ablation result published")
class ComparabilityTest(unittest.TestCase):
    """A comparison is only valid if the rows share a split and an evaluator."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(RESULTS.read_text(encoding="utf-8"))

    def test_the_split_and_evaluator_are_recorded(self) -> None:
        split = self.report["split"]
        self.assertEqual(split["path"], "data/synthetic/val.json")
        self.assertEqual(split["example_count"], 750)
        self.assertEqual(len(split["canonical_sha256"]), 64)
        self.assertIn("evaluation_metrics", self.report["evaluator"]["module"])

    def test_the_sealed_split_is_not_reused(self) -> None:
        # It is authorized for one opening, already spent.
        self.assertNotIn("sealed", self.report["split"]["path"])

    def test_every_unmeasured_row_says_so_and_why(self) -> None:
        for name, entry in self.report["recorded_prior_measurements"].items():
            with self.subTest(system=name):
                self.assertFalse(entry["available_here"])
                self.assertTrue(entry["reason"].strip())
                self.assertTrue(entry["source"].strip())

    def test_the_ner_rows_declare_a_different_split(self) -> None:
        # Presenting them as like-for-like with the measured rows would be wrong.
        for name in ("ner_v1_0_0", "ner_targeted_v2"):
            with self.subTest(system=name):
                entry = self.report["recorded_prior_measurements"][name]
                self.assertNotEqual(entry["split"], self.report["split"]["path"])

    def test_the_measured_extractor_reproduces_the_recorded_baseline(self) -> None:
        # Guards against evaluator drift: the shipped extractor on this split
        # must still score what its own recorded baseline artifact holds. Read
        # from the artifact rather than pinned to a literal, so a deliberate
        # rule change updates one file instead of two.
        recorded_path = (
            ROOT
            / "data"
            / "interim"
            / "baselines"
            / "regex_baseline_v1_2-synthetic_dev.json"
        )
        if not recorded_path.is_file():
            self.skipTest("recorded synthetic-dev baseline is not present")
        recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
        measured = self.report["measured_here"]["extractor_only"]["entity"]["f1"]
        self.assertAlmostEqual(measured, recorded["overall"]["f1"], places=12)


@unittest.skipUnless(RESULTS.is_file(), "no ablation result published")
class StageAblationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.measured = json.loads(RESULTS.read_text(encoding="utf-8"))["measured_here"]

    def test_each_stage_is_reported(self) -> None:
        for stage in (
            "extractor_only",
            "extractor_plus_validator",
            "extractor_plus_normalizer_plus_validator",
            "normalizer_contribution",
            "complete_system",
        ):
            with self.subTest(stage=stage):
                self.assertIn(stage, self.measured)

    def test_a_null_normalizer_contribution_is_accompanied_by_its_activity(self) -> None:
        # Without the change counts, a zero contribution is indistinguishable
        # from the stage not running at all.
        contribution = self.measured["normalizer_contribution"]
        self.assertIn("additional_valid_chains", contribution)
        self.assertGreater(contribution["total_changes"], 0)
        self.assertGreater(contribution["examples_changed"], 0)
        self.assertTrue(contribution["changes_by_rule"])

    def test_complete_system_statuses_cover_the_split(self) -> None:
        complete = self.measured["complete_system"]
        self.assertEqual(
            sum(complete["quality_gate_status_counts"].values()),
            complete["example_count"],
        )

    def test_valid_chain_rate_matches_the_ready_count(self) -> None:
        # The two must agree: a valid chain with no pending issue is exactly
        # what SIAP_DIPROSES means.
        ready = self.measured["complete_system"]["quality_gate_status_counts"].get(
            "SIAP_DIPROSES", 0
        )
        self.assertEqual(
            ready,
            self.measured["extractor_plus_normalizer_plus_validator"]["valid_chain_count"],
        )


@unittest.skipUnless(RESULTS.is_file(), "no ablation result published")
class LatencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.latency = json.loads(RESULTS.read_text(encoding="utf-8"))["latency"]

    def test_the_protocol_records_warmup_and_repeats(self) -> None:
        protocol = self.latency["protocol"]
        self.assertGreater(protocol["warmup_iterations"], 0)
        self.assertGreater(protocol["timed_repeats"], 1)
        self.assertIn("perf_counter", protocol["clock"])
        self.assertIn("nearest rank", protocol["percentile_method"])

    def test_the_protocol_warns_that_stages_are_not_additive(self) -> None:
        self.assertIn("not", self.latency["protocol"]["note"].lower())

    def test_hardware_is_recorded(self) -> None:
        hardware = self.latency["hardware"]
        for field in ("platform", "machine", "python"):
            with self.subTest(field=field):
                self.assertTrue(str(hardware[field]).strip())

    def test_percentiles_are_ordered(self) -> None:
        for stage in ("extraction", "extraction_plus_normalizer", "complete_pipeline"):
            with self.subTest(stage=stage):
                values = self.latency[stage]
                self.assertLessEqual(values["p50"], values["p95"])
                self.assertLessEqual(values["p95"], values["p99"])


@unittest.skipUnless(RESULTS.is_file(), "no ablation result published")
class FailureCaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(RESULTS.read_text(encoding="utf-8"))["failure_cases"]

    def test_at_least_two_cases_are_published(self) -> None:
        self.assertGreaterEqual(len(self.cases), 2)

    def test_each_case_has_a_distinct_failure_signature(self) -> None:
        # Four copies of one finding is not "representative".
        signatures = [
            (tuple(case["missed_critical_spans"]), tuple(case["spurious_critical_spans"]))
            for case in self.cases
        ]
        self.assertEqual(len(signatures), len(set(signatures)))

    def test_every_case_is_synthetic_and_carries_no_pii(self) -> None:
        phone = re.compile(r"(?<![\w.+-])(?:\+?62|0)8\d{2}[\s.-]?\d{3,4}[\s.-]?\d{3,5}")
        for case in self.cases:
            with self.subTest(example=case["example_id"]):
                self.assertTrue(case["synthetic"])
                self.assertTrue(case["example_id"].startswith("SYN-"))
                self.assertIsNone(phone.search(case["address_text"]))

    def test_each_case_shows_gold_against_predicted(self) -> None:
        # A failure case without both sides cannot be reasoned about.
        for case in self.cases:
            with self.subTest(example=case["example_id"]):
                self.assertTrue(case["gold_components"])
                self.assertIn("predicted_components", case)


@unittest.skipUnless(
    RESULTS.is_file() and SEALED_RESULTS.is_file(),
    "both the ablation and sealed results are required",
)
class CrossArtifactConsistencyTest(unittest.TestCase):
    """Numbers quoted in two places must come from one source."""

    def test_the_interpretation_limits_match_the_sealed_numbers(self) -> None:
        ablation = json.loads(RESULTS.read_text(encoding="utf-8"))
        sealed = json.loads(SEALED_RESULTS.read_text(encoding="utf-8"))
        limits = " ".join(ablation["interpretation_limits"])
        sealed_f1 = sealed["metrics"]["entity_overall"]["f1"]
        sealed_cem = sealed["metrics"]["critical_exact_match"]["rate"]
        # The document claims specific sealed figures; assert they are the real
        # ones rather than a stale copy.
        self.assertIn(f"{sealed_f1:.3f}", limits)
        self.assertIn(f"{sealed_cem:.3f}", limits)

    def test_the_synthetic_split_is_not_claimed_to_be_easier(self) -> None:
        ablation = json.loads(RESULTS.read_text(encoding="utf-8"))
        sealed = json.loads(SEALED_RESULTS.read_text(encoding="utf-8"))
        synthetic_cem = ablation["measured_here"]["extractor_only"][
            "critical_exact_match"
        ]["rate"]
        sealed_cem = sealed["metrics"]["critical_exact_match"]["rate"]
        # It is in fact harder on this metric, which is why the blanket
        # "synthetic is optimistic" claim was removed.
        self.assertLess(synthetic_cem, sealed_cem)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


INDEX = load("build_evidence_index", "scripts/build_evidence_index.py")
STUDY = load("analyze_user_study", "scripts/analyze_user_study.py")

INDEX_ARTIFACT = ROOT / "experiments" / "evidence" / "index.json"


class EvidenceIndexTest(unittest.TestCase):
    """Every reportable number must resolve to an artifact, and match it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = INDEX.build()

    def test_no_claim_is_unresolved_or_stale(self) -> None:
        # This is the acceptance criterion: every main claim has an evidence
        # path, and the citing document holds the artifact's value.
        self.assertEqual(
            self.index["problems"], [], "\n".join(self.index["problems"])
        )

    def test_every_claim_names_artifact_pointer_and_script(self) -> None:
        for entry in self.index["claims"]:
            with self.subTest(claim=entry["id"]):
                self.assertTrue(entry["artifact"])
                self.assertTrue(entry["pointer"])
                self.assertTrue(entry["script"])
                self.assertTrue(entry["documents"])
                self.assertEqual(entry["status"], "measured")

    def test_every_cited_artifact_and_script_exists(self) -> None:
        for entry in self.index["claims"]:
            with self.subTest(claim=entry["id"]):
                self.assertTrue((ROOT / entry["artifact"]).is_file())
                self.assertTrue((ROOT / entry["script"]).is_file())
                for document in entry["documents"]:
                    self.assertTrue((ROOT / document).is_file())

    def test_values_are_read_from_artifacts_not_typed_in(self) -> None:
        # Re-resolve independently: if the index held a hand-typed number this
        # would disagree.
        for entry in self.index["claims"]:
            with self.subTest(claim=entry["id"]):
                document = json.loads(
                    (ROOT / entry["artifact"]).read_text(encoding="utf-8")
                )
                try:
                    raw = INDEX.resolve(document, entry["pointer"])
                except INDEX.EvidenceError:
                    raw = entry["value"]  # zero-count claims use an explicit default
                expected = raw if not isinstance(raw, list) else len(raw)
                self.assertEqual(entry["value"], expected)

    def test_a_stale_document_number_is_detected(self) -> None:
        # Proves the check is not vacuous: point a claim at a value the document
        # does not contain and the verifier must complain.
        original = INDEX.CLAIMS
        INDEX.CLAIMS = (
            INDEX.claim(
                "probe",
                "probe",
                "experiments/ablation/results.json",
                ("split", "example_count"),
                "scripts/run_ablation.py",
                ("docs/user-study-protocol.md",),
                fmt="{:d}",
            ),
        )
        try:
            probe = INDEX.build()
        finally:
            INDEX.CLAIMS = original
        self.assertTrue(probe["problems"])
        self.assertIn("does not contain", probe["problems"][0])

    def test_every_unmeasured_claim_states_a_reason(self) -> None:
        for entry in self.index["not_measured"]:
            with self.subTest(claim=entry["id"]):
                self.assertIn(entry["status"], {"not_measured", "out_of_scope"})
                self.assertTrue(entry["reason"].strip())

    def test_delivery_claims_are_recorded_as_out_of_scope(self) -> None:
        entry = next(
            item for item in self.index["not_measured"] if item["id"] == "delivery-outcomes"
        )
        self.assertEqual(entry["status"], "out_of_scope")

    def test_the_user_study_claims_are_marked_unmeasured(self) -> None:
        # No study has run; a results table must not imply otherwise.
        study = [
            item for item in self.index["not_measured"] if item["id"].startswith("study-")
        ]
        self.assertGreaterEqual(len(study), 3)
        for entry in study:
            with self.subTest(claim=entry["id"]):
                self.assertEqual(entry["status"], "not_measured")


@unittest.skipUnless(INDEX_ARTIFACT.is_file(), "evidence index not written")
class PublishedIndexTest(unittest.TestCase):
    def test_the_published_index_is_current(self) -> None:
        stored = json.loads(INDEX_ARTIFACT.read_text(encoding="utf-8"))
        current = INDEX.build()
        self.assertEqual(stored["summary"], current["summary"])
        self.assertEqual(
            [item["id"] for item in stored["claims"]],
            [item["id"] for item in current["claims"]],
        )

    def test_the_published_index_has_no_problems(self) -> None:
        stored = json.loads(INDEX_ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(stored["problems"], [])


class UserStudyAnalysisTest(unittest.TestCase):
    """Absent data must be reported as absent, never as a placeholder."""

    def test_missing_records_report_not_measured(self) -> None:
        report = STUDY.not_measured("no session has been run", STUDY.DEFAULT_RECORDS)
        self.assertEqual(report["status"], "not_measured")
        self.assertIsNone(report["metrics"])
        self.assertIn("placeholder", report["note"].lower())

    def test_the_current_state_is_not_measured(self) -> None:
        self.assertFalse(
            STUDY.DEFAULT_RECORDS.is_file(),
            "session records appeared; the analysis and docs must be regenerated",
        )

    def test_the_harness_computes_real_numbers_when_data_exists(self) -> None:
        # Exercising only the not_measured path would leave the analysis itself
        # untested until the day it matters.
        records = {
            "tasks": [
                {
                    "participant_id": "P01",
                    "task_id": f"T{index}",
                    "condition": "manual" if index < 4 else "alamatin",
                    "seconds_to_decision": 40 if index < 4 else 20,
                    "defects_found": ["typo"] if index % 2 else [],
                    "defects_missed": [] if index % 2 else ["typo"],
                    "false_defects": [],
                    "corrections_accepted": [],
                    "decision_matches_ground_truth": bool(index % 2),
                }
                for index in range(8)
            ],
            "sessions": [
                {
                    "participant_id": "P01",
                    "usability_ease": 4,
                    "usability_trust": 5,
                    "usability_reuse": 4,
                    "comments": "useful before printing",
                    "quote_permission": True,
                    "protocol_deviations": "longer break",
                }
            ],
        }
        report = STUDY.analyse(records)
        self.assertEqual(report["status"], "measured")
        self.assertEqual(report["sample"]["participants"], 1)
        self.assertEqual(
            report["metrics"]["by_condition"]["manual"]["seconds_to_decision"]["median"], 40
        )
        self.assertEqual(len(report["permitted_quotes"]), 1)
        self.assertEqual(len(report["protocol_deviations"]), 1)

    def test_a_quote_without_permission_is_dropped(self) -> None:
        records = {
            "tasks": [
                {
                    "participant_id": "P01",
                    "task_id": "T0",
                    "condition": "manual",
                    "seconds_to_decision": 10,
                }
            ],
            "sessions": [
                {
                    "participant_id": "P01",
                    "comments": "do not quote me",
                    "quote_permission": False,
                }
            ],
        }
        self.assertEqual(STUDY.analyse(records)["permitted_quotes"], [])

    def test_no_significance_claim_is_made(self) -> None:
        records = {
            "tasks": [{"participant_id": "P01", "task_id": "T0", "condition": "manual", "seconds_to_decision": 5}],
            "sessions": [],
        }
        report = STUDY.analyse(records)
        self.assertIn("No significance test", report["uncertainty"])
        self.assertIn("delivery", " ".join(report["prohibited_claims"]))


if __name__ == "__main__":
    unittest.main()

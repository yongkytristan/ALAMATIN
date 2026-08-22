from __future__ import annotations

import unittest
from pathlib import Path
import sys
import json


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.real_dev_error_analysis import (
    build_error_case,
    build_error_matrix,
    classify_error_categories,
    repair_orphan_i_tags,
    validate_real_dev_payload,
)
from alamatin.evaluation_metrics import critical_exact_match, entity_metrics


class RealDevErrorAnalysisTest(unittest.TestCase):
    def test_repairs_orphan_i_and_records_the_change(self) -> None:
        repaired, changes = repair_orphan_i_tags(["I-JALAN", "I-JALAN", "O"])
        self.assertEqual(repaired, ["B-JALAN", "I-JALAN", "O"])
        self.assertEqual(changes, [{"index": 0, "from": "I-JALAN", "to": "B-JALAN"}])

    def test_category_classification_is_multi_label_and_source_grounded(self) -> None:
        categories = classify_error_categories(
            ["Jl.", "Mawar", "RT", "01", "Kec", "Cilndak"],
            ["B-JALAN", "I-JALAN", "B-RT", "I-RT", "B-KECAMATAN", "I-KECAMATAN"],
            ["B-JALAN", "I-JALAN", "O", "O", "B-KECAMATAN", "I-KECAMATAN"],
            {
                "reference_address": "Jalan Mawar",
                "kecamatan": "Cilandak",
                "kabupaten_kota": "Kota Jakarta Selatan",
            },
        )
        self.assertIn("abbreviation", categories)
        self.assertIn("rt_rw", categories)
        self.assertIn("typo", categories)
        self.assertIn("missing_field", categories)

    def test_error_case_keeps_model_and_validator_separate(self) -> None:
        example = {
            "base_address_id": "X-1",
            "tokens": ["Jl", "Mawar"],
            "labels": ["B-JALAN", "I-JALAN"],
            "annotation_provenance": "double_annotated_agreed",
        }
        case = build_error_case(example, ["I-KELURAHAN", "I-KELURAHAN"])
        assert case is not None
        self.assertIn("model", case["components"])
        self.assertIn("validator", case["components"])
        self.assertTrue(case["bio_repairs"])

    def test_matrix_has_every_required_category_and_component(self) -> None:
        example = {
            "base_address_id": "X-1",
            "tokens": ["RT", "01"],
            "labels": ["B-RT", "I-RT"],
            "annotation_provenance": "automated_accepted",
        }
        case = build_error_case(example, ["O", "O"])
        assert case is not None
        matrix = build_error_matrix(
            [case],
            {"rt_rw": [case["case_id"]], "abbreviation": [case["case_id"]]},
        )
        self.assertEqual(
            set(matrix["categories"]),
            {
                "typo", "abbreviation", "rt_rw", "landmark", "missing_field",
                "conflict", "ambiguous_region", "other_surface_form",
            },
        )
        self.assertEqual(
            set(matrix["components"]),
            {"model", "generator", "normalizer", "validator", "annotation"},
        )
        self.assertIsNone(matrix["components"]["normalizer"]["case_count"])
        self.assertEqual(matrix["categories"]["rt_rw"]["error_rate"], 1.0)

    def test_information_boundary_refuses_sealed_payload_or_path(self) -> None:
        real_dev = {
            "split": "real_dev",
            "examples": [{"base_address_id": "X-1"}],
        }
        validate_real_dev_payload(real_dev, "data/real_dev.json")
        with self.assertRaisesRegex(ValueError, "only.*real_dev"):
            validate_real_dev_payload(real_dev, "data/private/sealed-test.json")
        with self.assertRaisesRegex(ValueError, "only.*real_dev"):
            validate_real_dev_payload(
                {"split": "sealed_real_test", "examples": [{"base_address_id": "X"}]},
                "data/input.json",
            )


# These evidence gates read governed datasets that data/sources.md keeps in the
# private repository, so they run there and skip in the public mirror. The
# assertions stay visible either way; only the restricted inputs are absent.
GOVERNED_INPUTS = (
    ROOT / "data" / "interim" / "evaluation-splits" / "real_dev.json",
    # Verbatim benchmark spans; not redistributed (see data/sources.md).
    ROOT / "experiments" / "ner-v1-real-dev" / "error_cases.json",
)
GOVERNED_REASON = (
    "governed dataset not present in this repository; see data/sources.md"
)


@unittest.skipUnless(
    all(path.exists() for path in GOVERNED_INPUTS), GOVERNED_REASON
)
class RealDevEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.experiment = ROOT / "experiments" / "ner-v1-real-dev"
        cls.dataset = json.loads(
            (ROOT / "data" / "interim" / "evaluation-splits" / "real_dev.json")
            .read_text(encoding="utf-8")
        )
        cls.predictions = json.loads(
            (cls.experiment / "predictions.json").read_text(encoding="utf-8")
        )
        cls.metrics = json.loads(
            (cls.experiment / "metrics.json").read_text(encoding="utf-8")
        )
        cls.matrix = json.loads(
            (cls.experiment / "error_matrix.json").read_text(encoding="utf-8")
        )
        cls.cases = json.loads(
            (cls.experiment / "error_cases.json").read_text(encoding="utf-8")
        )["cases"]
        cls.actions = json.loads(
            (cls.experiment / "action_register.json").read_text(encoding="utf-8")
        )

    def test_evidence_scores_all_and_only_real_dev(self) -> None:
        self.assertEqual(self.dataset["split"], "real_dev")
        self.assertEqual(self.predictions["split"], "real_dev")
        self.assertEqual(len(self.dataset["examples"]), 70)
        self.assertEqual(len(self.predictions["examples"]), 70)
        self.assertEqual(self.metrics["example_count"], 70)
        dataset_ids = [item["base_address_id"] for item in self.dataset["examples"]]
        prediction_ids = [
            item["base_address_id"] for item in self.predictions["examples"]
        ]
        self.assertEqual(prediction_ids, dataset_ids)

    def test_saved_metrics_recompute_from_saved_predictions(self) -> None:
        gold = [item["labels"] for item in self.dataset["examples"]]
        predicted = [
            item["evaluated_predicted_labels"]
            for item in self.predictions["examples"]
        ]
        overall = entity_metrics(gold, predicted)
        critical = critical_exact_match(gold, predicted)
        self.assertAlmostEqual(self.metrics["overall"]["f1"], overall.f1)
        self.assertEqual(
            self.metrics["critical_exact_match"]["numerator"],
            critical.numerator,
        )

    def test_matrix_and_actions_are_traceable_to_saved_cases(self) -> None:
        case_ids = {case["case_id"] for case in self.cases}
        self.assertEqual(len(case_ids), self.metrics["error_example_count"])
        self.assertEqual(
            set(self.matrix["matrix"]["categories"]),
            {
                "typo", "abbreviation", "rt_rw", "landmark", "missing_field",
                "conflict", "ambiguous_region", "other_surface_form",
            },
        )
        for action in self.actions["actions"]:
            self.assertEqual(
                action["evidence_case_count"], len(action["evidence_case_ids"])
            )
            self.assertLessEqual(set(action["evidence_case_ids"]), case_ids)
            self.assertEqual(action["target_issue"], 20)

    def test_sealed_boundary_attests_non_access(self) -> None:
        boundary = self.matrix["information_boundary"]
        self.assertFalse(boundary["sealed_test_opened"])
        self.assertEqual(
            boundary["evidence_source"], "sealed-test-boundary-manifest.json only"
        )
        self.assertEqual(len(boundary["sealed_content_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()

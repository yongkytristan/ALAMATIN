from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.evaluation_metrics import critical_exact_match, entity_metrics


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# These evidence gates read governed datasets that data/sources.md keeps in the
# private repository, so they run there and skip in the public mirror. The
# assertions stay visible either way; only the restricted inputs are absent.
GOVERNED_INPUTS = (ROOT / "data" / "interim" / "evaluation-splits" / "real_dev.json",)
GOVERNED_REASON = (
    "governed dataset not present in this repository; see data/sources.md"
)


@unittest.skipUnless(
    all(path.exists() for path in GOVERNED_INPUTS), GOVERNED_REASON
)
class NerFinalCandidateEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.experiment = ROOT / "experiments" / "ner-final-candidate"
        cls.real_experiment = ROOT / "experiments" / "ner-targeted-v2-real-dev"
        cls.config = read_json(ROOT / "configs" / "ner-final-candidate.json")
        cls.comparison = read_json(cls.experiment / "comparison.json")
        cls.manifest = read_json(cls.experiment / "run_manifest.json")
        cls.release = read_json(cls.experiment / "release_manifest.json")
        cls.real_metrics = read_json(cls.real_experiment / "metrics.json")
        cls.real_predictions = read_json(cls.real_experiment / "predictions.json")
        cls.real_dataset = read_json(
            ROOT / "data" / "interim" / "evaluation-splits" / "real_dev.json"
        )

    def test_targeted_candidate_passes_every_frozen_gate(self) -> None:
        self.assertTrue(self.comparison["targeted_candidate_eligible"])
        self.assertEqual(self.comparison["selected_candidate"], "ner-targeted-v2")
        self.assertTrue(
            all(
                gate["passed"]
                for gate in self.comparison["targeted_candidate_gates"].values()
            )
        )
        self.assertEqual(
            self.comparison["selection_policy"], self.config["selection_policy"]
        )

    def test_config_dataset_and_model_hashes_are_consistent(self) -> None:
        self.assertEqual(
            self.manifest["config"]["canonical_json_sha256"],
            canonical_json_sha256(self.config),
        )
        augmentation = read_json(
            ROOT / "data" / "synthetic-v2-targeted" / "train-augmentation.json"
        )
        augmentation_entry = self.manifest["datasets"]["train"][1]
        self.assertEqual(
            augmentation_entry["canonical_json_sha256"],
            canonical_json_sha256(augmentation),
        )
        selected_hash = self.comparison["selected_model_sha256"]
        self.assertEqual(selected_hash, self.release["selected_model"]["sha256"])
        self.assertEqual(
            selected_hash,
            self.manifest["artifact_files"]["model.safetensors"]["sha256"],
        )

    def test_real_dev_metrics_recompute_from_saved_predictions(self) -> None:
        gold = [example["labels"] for example in self.real_dataset["examples"]]
        predicted = [
            example["evaluated_predicted_labels"]
            for example in self.real_predictions["examples"]
        ]
        overall = entity_metrics(gold, predicted)
        critical = critical_exact_match(gold, predicted)
        self.assertAlmostEqual(self.real_metrics["overall"]["f1"], overall.f1)
        self.assertEqual(
            self.real_metrics["critical_exact_match"]["numerator"],
            critical.numerator,
        )

    def test_training_and_selection_attest_the_information_boundary(self) -> None:
        self.assertFalse(self.manifest["datasets"]["real_dev_used_for_training"])
        self.assertFalse(self.manifest["datasets"]["sealed_test_accessed"])
        traceability = self.comparison["traceability"]
        self.assertFalse(traceability["real_dev_used_for_training"])
        self.assertFalse(traceability["sealed_test_accessed"])
        self.assertEqual(traceability["checkpoint_selected_on"], "synthetic_dev")

    def test_release_manifest_is_content_addressed_and_complete(self) -> None:
        self.assertEqual(self.release["release"]["tag"], "ner-final-candidate-v1.0.0")
        self.assertEqual(len(self.release["asset"]["sha256"]), 64)
        self.assertGreater(self.release["asset"]["bytes"], 700_000_000)
        self.assertIn("model-card.md", self.release["contents"])
        self.assertIn("model.safetensors", self.release["contents"])
        self.assertIn("comparison.json", self.release["contents"])

    def test_packaged_verifier_projection_is_repository_independent(self) -> None:
        verifier_path = ROOT / "scripts" / "verify_ner_v1_artifact.py"
        spec = importlib.util.spec_from_file_location("artifact_verifier", verifier_path)
        assert spec and spec.loader
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        labels = verifier.predictions_to_word_labels(
            [0, 1, 2, 0],
            [None, 0, 0, None],
            word_count=1,
            id_to_label={0: "O", 1: "B-JALAN", 2: "I-JALAN"},
        )
        self.assertEqual(labels, ["B-JALAN"])


if __name__ == "__main__":
    unittest.main()

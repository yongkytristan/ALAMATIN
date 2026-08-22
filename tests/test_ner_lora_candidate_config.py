from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from train_ner_v1 import load_config  # noqa: E402


class NerLoraCandidateConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = ROOT / "configs" / "ner-lora-kevin.json"
        self.config = load_config(self.path)

    def test_kevin_lora_settings_are_preserved(self) -> None:
        self.assertEqual(
            self.config["source"]["commit"],
            "866303afffb178e8b5910764b303db0b7c500d7f",
        )
        self.assertEqual(
            self.config["lora"],
            {
                "r": 8,
                "alpha": 16,
                "dropout": 0.1,
                "target_modules": ["query", "value"],
                "bias": "none",
            },
        )
        self.assertEqual(self.config["training"]["learning_rate"], 0.0002)
        self.assertEqual(self.config["training"]["num_train_epochs"], 5)

    def test_reproducibility_and_dev_selection_are_explicit(self) -> None:
        self.assertEqual(self.config["seed"], 42)
        self.assertRegex(self.config["base_model"]["revision"], r"^[0-9a-f]{40}$")
        training = self.config["training"]
        self.assertTrue(training["load_best_model_at_end"])
        self.assertEqual(training["metric_for_best_model"], "f1")
        self.assertTrue(training["greater_is_better"])
        self.assertEqual(
            set(self.config["dataset"]),
            {"train", "dev", "test"},
        )

    def test_config_is_valid_json_and_uses_repository_paths(self) -> None:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        for relative in document["dataset"].values():
            self.assertTrue((ROOT / relative).is_file())
        self.assertEqual(document["output_dir"], "models/ner-lora-kevin")

    def test_saved_evidence_is_traceable_to_the_same_run(self) -> None:
        evidence = ROOT / "experiments" / "ner-lora-kevin"
        manifest = json.loads(
            (evidence / "run_manifest.json").read_text(encoding="utf-8")
        )
        metrics = json.loads(
            (evidence / "training_metrics.json").read_text(encoding="utf-8")
        )
        comparison = json.loads(
            (evidence / "comparison.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["source"], self.config["source"])
        self.assertEqual(manifest["lora"], self.config["lora"])
        self.assertEqual(
            metrics["selection"]["value"],
            comparison["candidate"]["synthetic_dev_f1"],
        )

    def test_failed_selection_gates_keep_current_final_candidate(self) -> None:
        comparison = json.loads(
            (
                ROOT / "experiments" / "ner-lora-kevin" / "comparison.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(comparison["eligible_for_final_selection"])
        self.assertEqual(
            comparison["selected_baseline"]["candidate_id"],
            "ner-targeted-v2",
        )
        gates = comparison["frozen_selection_gates"]
        self.assertTrue(gates["synthetic_dev_f1_floor"]["passed"])
        self.assertFalse(gates["minimum_real_dev_f1_gain_over_v1"]["passed"])
        self.assertFalse(
            gates["minimum_critical_exact_match_gain_over_v1_examples"]["passed"]
        )
        self.assertFalse(gates["maximum_raw_invalid_bio_examples"]["passed"])


if __name__ == "__main__":
    unittest.main()

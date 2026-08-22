from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ner-final-candidate.json"
SPEC = importlib.util.spec_from_file_location(
    "train_ner_targeted_candidate",
    ROOT / "scripts" / "train_ner_targeted_candidate.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NerFinalCandidateConfigTest(unittest.TestCase):
    def test_selection_policy_is_frozen_and_forbids_real_dev_training(self) -> None:
        config = MODULE.load_config(CONFIG)
        self.assertFalse(config["traceability"]["training_uses_real_dev"])
        self.assertEqual(
            config["traceability"]["checkpoint_selection_split"], "synthetic_dev"
        )
        self.assertTrue(config["selection_policy"]["frozen_before_candidate_run"])
        self.assertEqual(
            config["traceability"]["action_ids"],
            ["ALM019-A01", "ALM019-A02", "ALM019-A03", "ALM019-A04"],
        )

    def test_parent_model_and_base_revision_are_content_addressed(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(len(config["base_model"]["revision"]), 40)
        self.assertEqual(len(config["parent_checkpoint"]["model_sha256"]), 64)

    def test_real_dev_is_comparison_only_and_sealed_is_absent(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        serialized = json.dumps(config).casefold()
        self.assertIn("real_dev_comparison_only", serialized)
        self.assertNotIn("sealed_real_test", serialized)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "select_ner_final_candidate", ROOT / "scripts" / "select_ner_final_candidate.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def training(f1: float, checkpoint: str = "checkpoint-1") -> dict:
    return {
        "selection": {
            "value": f1,
            "selected_checkpoint": checkpoint,
            "selected_epoch": 1.0,
        }
    }


def real(f1: float, exact: int, invalid: int, model_hash: str) -> dict:
    return {
        "overall": {"f1": f1},
        "critical_exact_match": {"numerator": exact, "denominator": 70, "rate": exact / 70},
        "raw_invalid_bio": {"example_count": invalid},
        "system": {"model_sha256": model_hash},
    }


class SelectNerFinalCandidateTest(unittest.TestCase):
    CONFIG = {
        "selection_policy": {
            "frozen_before_candidate_run": True,
            "synthetic_dev_f1_floor": 0.99,
            "minimum_real_dev_f1_gain": 0.01,
            "minimum_critical_exact_match_gain_examples": 5,
            "maximum_raw_invalid_bio_examples": 14,
            "ranking": ["eligibility_constraints", "real_dev_critical_exact_match"],
        },
        "traceability": {"action_ids": ["ALM019-A01", "ALM019-A02"]},
    }

    def test_selects_targeted_candidate_only_when_every_gate_passes(self) -> None:
        result = MODULE.select_candidate(
            self.CONFIG,
            training(0.999),
            real(0.67, 15, 14, "a" * 64),
            training(0.998),
            real(0.78, 37, 8, "b" * 64),
        )
        self.assertTrue(result["targeted_candidate_eligible"])
        self.assertEqual(result["selected_candidate"], "ner-targeted-v2")
        self.assertTrue(
            all(gate["passed"] for gate in result["targeted_candidate_gates"].values())
        )

    def test_retains_baseline_when_one_gate_fails(self) -> None:
        result = MODULE.select_candidate(
            self.CONFIG,
            training(0.999),
            real(0.67, 15, 14, "a" * 64),
            training(0.98),
            real(0.80, 40, 5, "b" * 64),
        )
        self.assertFalse(result["targeted_candidate_eligible"])
        self.assertEqual(result["selected_candidate"], "ner-v1.0.0")


if __name__ == "__main__":
    unittest.main()

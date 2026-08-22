#!/usr/bin/env python3
"""Apply the pre-frozen ALM-020 policy to baseline and targeted candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def select_candidate(
    config: dict[str, Any],
    baseline_training: dict[str, Any],
    baseline_real: dict[str, Any],
    targeted_training: dict[str, Any],
    targeted_real: dict[str, Any],
) -> dict[str, Any]:
    policy = config["selection_policy"]
    if not policy.get("frozen_before_candidate_run"):
        raise ValueError("selection policy was not frozen")

    baseline = {
        "candidate_id": "ner-v1.0.0",
        "synthetic_dev_f1": baseline_training["selection"]["value"],
        "real_dev_micro_f1": baseline_real["overall"]["f1"],
        "real_dev_critical_exact_match": baseline_real["critical_exact_match"],
        "raw_invalid_bio_examples": baseline_real["raw_invalid_bio"]["example_count"],
        "model_sha256": baseline_real["system"]["model_sha256"],
    }
    targeted = {
        "candidate_id": "ner-targeted-v2",
        "synthetic_dev_f1": targeted_training["selection"]["value"],
        "synthetic_dev_selected_checkpoint": targeted_training["selection"]["selected_checkpoint"],
        "synthetic_dev_selected_epoch": targeted_training["selection"]["selected_epoch"],
        "real_dev_micro_f1": targeted_real["overall"]["f1"],
        "real_dev_critical_exact_match": targeted_real["critical_exact_match"],
        "raw_invalid_bio_examples": targeted_real["raw_invalid_bio"]["example_count"],
        "model_sha256": targeted_real["system"]["model_sha256"],
    }
    deltas = {
        "synthetic_dev_f1": targeted["synthetic_dev_f1"] - baseline["synthetic_dev_f1"],
        "real_dev_micro_f1": targeted["real_dev_micro_f1"] - baseline["real_dev_micro_f1"],
        "real_dev_critical_exact_match_examples": (
            targeted["real_dev_critical_exact_match"]["numerator"]
            - baseline["real_dev_critical_exact_match"]["numerator"]
        ),
        "raw_invalid_bio_examples": (
            targeted["raw_invalid_bio_examples"] - baseline["raw_invalid_bio_examples"]
        ),
    }
    gates = {
        "synthetic_dev_f1_floor": {
            "threshold": policy["synthetic_dev_f1_floor"],
            "actual": targeted["synthetic_dev_f1"],
            "passed": targeted["synthetic_dev_f1"] >= policy["synthetic_dev_f1_floor"],
        },
        "minimum_real_dev_f1_gain": {
            "threshold": policy["minimum_real_dev_f1_gain"],
            "actual": deltas["real_dev_micro_f1"],
            "passed": deltas["real_dev_micro_f1"] >= policy["minimum_real_dev_f1_gain"],
        },
        "minimum_critical_exact_match_gain_examples": {
            "threshold": policy["minimum_critical_exact_match_gain_examples"],
            "actual": deltas["real_dev_critical_exact_match_examples"],
            "passed": (
                deltas["real_dev_critical_exact_match_examples"]
                >= policy["minimum_critical_exact_match_gain_examples"]
            ),
        },
        "maximum_raw_invalid_bio_examples": {
            "threshold": policy["maximum_raw_invalid_bio_examples"],
            "actual": targeted["raw_invalid_bio_examples"],
            "passed": (
                targeted["raw_invalid_bio_examples"]
                <= policy["maximum_raw_invalid_bio_examples"]
            ),
        },
    }
    eligible = all(gate["passed"] for gate in gates.values())
    selected = targeted if eligible else baseline
    return {
        "schema_version": "1.0.0",
        "selection_policy": policy,
        "candidates": [baseline, targeted],
        "targeted_candidate_deltas": deltas,
        "targeted_candidate_gates": gates,
        "targeted_candidate_eligible": eligible,
        "selected_candidate": selected["candidate_id"],
        "selected_model_sha256": selected["model_sha256"],
        "selection_reason": (
            "Targeted v2 passed every pre-frozen gate and ranks ahead on real_dev critical exact match."
            if eligible
            else "Targeted v2 failed at least one pre-frozen gate; retain the baseline."
        ),
        "traceability": {
            "source_issue": "ALM-019",
            "action_ids": config["traceability"]["action_ids"],
            "real_dev_used_for_training": False,
            "checkpoint_selected_on": "synthetic_dev",
            "sealed_test_accessed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "experiments" / "ner-final-candidate" / "comparison.json",
    )
    args = parser.parse_args(argv)
    result = select_candidate(
        read_json(ROOT / "configs" / "ner-final-candidate.json"),
        read_json(ROOT / "experiments" / "ner-v1" / "metrics.json"),
        read_json(ROOT / "experiments" / "ner-v1-real-dev" / "metrics.json"),
        read_json(ROOT / "experiments" / "ner-final-candidate" / "training_metrics.json"),
        read_json(ROOT / "experiments" / "ner-targeted-v2-real-dev" / "metrics.json"),
    )
    write_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

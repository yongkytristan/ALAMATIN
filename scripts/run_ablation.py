#!/usr/bin/env python3
"""Ablation, latency, and failure cases for the release candidate (ALM-036).

Runs every stage combination that can be executed in this repository over one
split with one evaluator, so the comparison is valid. Stages that cannot be
executed here are reported as recorded prior measurements with the reason, never
silently omitted and never mixed into a column they did not earn.

The measured split is `data/synthetic/val.json` (750 examples). The sealed set is
deliberately not used: it is authorized for exactly one opening, already spent.

Two metric families, because the stages answer different questions:

* extraction stages are compared with entity P/R/F1 and critical exact match;
* the stages after extraction do not change spans, they change the decision, so
  they are compared by how often a reference-backed verdict is reached.

Usage:
    python scripts/run_ablation.py --write
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SPLIT = ROOT / "data" / "synthetic" / "val.json"
OUTPUT = ROOT / "experiments" / "ablation" / "results.json"

#: Prior measurements on the same split and evaluator that cannot be re-run
#: here. Each states why, so a reader knows it was not measured in this run.
RECORDED_PRIOR = {
    "libpostal_v1": {
        "source": "data/interim/baselines/libpostal-synthetic-dev.json",
        "available_here": False,
        "reason": "the `postal` module is not installed in this environment",
        "split": "data/synthetic/val.json",
        "entity_f1": 0.3701176470588235,
        "entity_precision": 0.5201719576719577,
        "entity_recall": 0.2872534696859021,
        "latency_p50_ms": 0.19308300034026615,
        "latency_p95_ms": 0.6991250002101879,
    },
    "ner_targeted_v2": {
        "source": "experiments/ner-final-candidate/comparison.json",
        "available_here": False,
        "reason": (
            "model weights are a 712 MB release asset excluded by .gitignore; "
            "not served by the release candidate"
        ),
        "split": "data/synthetic dev split used during selection",
        "entity_f1": 0.9994520547945206,
        "latency_p50_ms": None,
        "latency_p95_ms": None,
    },
    "ner_v1_0_0": {
        "source": "experiments/ner-final-candidate/comparison.json",
        "available_here": False,
        "reason": "model weights are a release asset, as above",
        "split": "data/synthetic dev split used during selection",
        "entity_f1": 0.999360788969044,
        "latency_p50_ms": None,
        "latency_p95_ms": None,
    },
}

WARMUP_ITERATIONS = 50
TIMED_REPEATS = 3


def load_split() -> list[dict]:
    payload = json.loads(SPLIT.read_text(encoding="utf-8"))
    examples = payload["examples"] if isinstance(payload, dict) else payload
    if not examples:
        raise SystemExit(f"{SPLIT} has no examples")
    return examples


def detokenize(tokens: list[str]) -> str:
    text = ""
    for token in tokens:
        if not text:
            text = token
        elif token in {",", ".", ";", ":"}:
            text += token
        else:
            text += " " + token
    return text


def metric_dict(result) -> dict[str, object]:
    return {
        "true_positive": result.true_positive,
        "false_positive": result.false_positive,
        "false_negative": result.false_negative,
        "precision": result.precision,
        "recall": result.recall,
        "f1": result.f1,
    }


def measure_extraction(examples: list[dict]) -> dict[str, object]:
    """Stage A: the extractor alone, on entity spans."""

    from alamatin.evaluation_metrics import (
        critical_exact_match,
        entity_metrics,
        entity_metrics_by_type,
    )
    from alamatin.regex_baseline import tag_tokens

    gold = [example["labels"] for example in examples]
    predicted = [tag_tokens(example["tokens"]) for example in examples]
    critical = critical_exact_match(gold, predicted)
    return {
        "entity": metric_dict(entity_metrics(gold, predicted)),
        "entity_by_type": {
            name: metric_dict(value)
            for name, value in sorted(entity_metrics_by_type(gold, predicted).items())
        },
        "critical_exact_match": {
            "numerator": critical.numerator,
            "denominator": critical.denominator,
            "rate": critical.rate,
        },
    }


def measure_decision_stages(examples: list[dict]) -> dict[str, object]:
    """Stages B and C: what normalization and validation add to the decision."""

    from alamatin.address_normalizer import ValueSource, normalize_address
    from alamatin.pipeline import decode_bio
    from alamatin.regex_baseline import tag_tokens
    from alamatin.service import load_pipeline

    pipeline = load_pipeline()
    validator = pipeline.validator

    raw_valid = 0
    normalized_valid = 0
    raw_reasons: dict[str, int] = {}
    normalized_reasons: dict[str, int] = {}
    statuses: dict[str, int] = {}
    # Recorded so a null contribution is interpretable: without these counts a
    # reader cannot tell whether the normalizer did nothing or did work that
    # simply did not change the outcome.
    examples_changed = 0
    change_count = 0
    change_rules: dict[str, int] = {}

    for example in examples:
        tokens = example["tokens"]
        extracted = decode_bio(tokens, tag_tokens(tokens))

        # Without the normalizer: validate the extractor's surface forms.
        raw_result = validator.validate(extracted)
        raw_valid += raw_result.status == "valid"
        for reason in raw_result.reason_codes:
            raw_reasons[reason] = raw_reasons.get(reason, 0) + 1

        # With the normalizer.
        normalized = normalize_address(
            extracted, default_source=ValueSource.RULE_EXTRACTED
        )
        if normalized.changes:
            examples_changed += 1
            change_count += len(normalized.changes)
            for change in normalized.changes:
                change_rules[change.rule_id] = change_rules.get(change.rule_id, 0) + 1
        norm_result = validator.validate(normalized.values())
        normalized_valid += norm_result.status == "valid"
        for reason in norm_result.reason_codes:
            normalized_reasons[reason] = normalized_reasons.get(reason, 0) + 1

        # Complete system, including the gate.
        outcome = pipeline.process(
            detokenize(tokens), request_id=f"ablation{example['id'][-8:]:>08}".replace(" ", "0")
        )
        statuses[outcome.status] = statuses.get(outcome.status, 0) + 1

    total = len(examples)
    return {
        "extractor_plus_validator": {
            "valid_chain_count": raw_valid,
            "valid_chain_rate": raw_valid / total,
            "validator_reason_codes": dict(sorted(raw_reasons.items())),
        },
        "extractor_plus_normalizer_plus_validator": {
            "valid_chain_count": normalized_valid,
            "valid_chain_rate": normalized_valid / total,
            "validator_reason_codes": dict(sorted(normalized_reasons.items())),
        },
        "normalizer_contribution": {
            "additional_valid_chains": normalized_valid - raw_valid,
            "examples_changed": examples_changed,
            "total_changes": change_count,
            "changes_by_rule": dict(sorted(change_rules.items())),
            "note": (
                "additional_valid_chains counts addresses that only reach a "
                "reference-backed valid chain once deterministic normalization "
                "has run. The change counts are reported alongside it so a zero "
                "contribution is not mistaken for the normalizer doing nothing: "
                "it rewrites designators, capitalization, and RT/RW padding, and "
                "the validator already tolerates that variation."
            ),
        },
        "complete_system": {
            "quality_gate_status_counts": dict(sorted(statuses.items())),
            "example_count": total,
        },
    }


def measure_latency(examples: list[dict]) -> dict[str, object]:
    """Per-stage CPU latency with an explicit warmup and repeats."""

    from alamatin.address_normalizer import ValueSource, normalize_address
    from alamatin.evaluation_metrics import latency_summary_ms, nearest_rank_percentile
    from alamatin.pipeline import decode_bio
    from alamatin.regex_baseline import tag_tokens
    from alamatin.service import load_pipeline

    pipeline = load_pipeline()
    sample = examples[:WARMUP_ITERATIONS]

    # Warmup: first calls pay import, cache, and branch-prediction costs that do
    # not represent steady state.
    for example in sample:
        tokens = example["tokens"]
        extracted = decode_bio(tokens, tag_tokens(tokens))
        normalize_address(extracted, default_source=ValueSource.RULE_EXTRACTED)
        pipeline.process(detokenize(tokens), request_id="warmup00000001")

    stages: dict[str, list[float]] = {
        "extraction": [],
        "extraction_plus_normalizer": [],
        "complete_pipeline": [],
    }
    for _ in range(TIMED_REPEATS):
        for example in examples:
            tokens = example["tokens"]

            started = time.perf_counter()
            labels = tag_tokens(tokens)
            stages["extraction"].append((time.perf_counter() - started) * 1000)

            started = time.perf_counter()
            extracted = decode_bio(tokens, tag_tokens(tokens))
            normalize_address(extracted, default_source=ValueSource.RULE_EXTRACTED)
            stages["extraction_plus_normalizer"].append(
                (time.perf_counter() - started) * 1000
            )

            started = time.perf_counter()
            pipeline.process(detokenize(tokens), request_id="latency000001")
            stages["complete_pipeline"].append((time.perf_counter() - started) * 1000)

    summary = {}
    for name, values in stages.items():
        stats = latency_summary_ms(values)
        summary[name] = {
            "sample_count": stats.sample_count,
            "p50": stats.p50_ms,
            "p95": stats.p95_ms,
            "p99": nearest_rank_percentile(values, 99.0),
            "mean": statistics.fmean(values),
        }
    summary["protocol"] = {
        "warmup_iterations": WARMUP_ITERATIONS,
        "timed_repeats": TIMED_REPEATS,
        "clock": "time.perf_counter",
        "percentile_method": "nearest rank",
        "concurrency": "single process, single thread",
        "note": (
            "each stage is timed independently, so the stage figures are not "
            "additive: extraction is re-run inside the normalizer measurement"
        ),
    }
    summary["hardware"] = {
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    return summary


def collect_failure_cases(examples: list[dict], limit: int = 4) -> list[dict[str, object]]:
    """Pick representative failures, worst critical-field damage first.

    The split is synthetic, so publishing the text carries no PII risk. A test
    asserts these cases contain no real-address content.
    """

    from alamatin.evaluation_metrics import CRITICAL_ENTITY_TYPES, extract_bio_entities
    from alamatin.pipeline import decode_bio
    from alamatin.regex_baseline import tag_tokens

    scored: list[tuple[int, dict[str, object]]] = []
    for example in examples:
        tokens = example["tokens"]
        predicted = tag_tokens(tokens)
        gold_spans = extract_bio_entities(example["labels"])
        predicted_spans = extract_bio_entities(predicted)
        missed = {
            span for span in gold_spans - predicted_spans if span[0] in CRITICAL_ENTITY_TYPES
        }
        spurious = {
            span
            for span in predicted_spans - gold_spans
            if span[0] in CRITICAL_ENTITY_TYPES
        }
        damage = len(missed) + len(spurious)
        if not damage:
            continue
        scored.append(
            (
                damage,
                {
                    "example_id": example["id"],
                    "categories": example.get("categories", []),
                    "address_text": detokenize(tokens),
                    "gold_components": decode_bio(tokens, example["labels"]),
                    "predicted_components": decode_bio(tokens, predicted),
                    "missed_critical_spans": sorted(item[0] for item in missed),
                    "spurious_critical_spans": sorted(item[0] for item in spurious),
                    "synthetic": True,
                },
            )
        )
    # One case per distinct failure signature. Three cases with the same
    # missed/spurious pattern would be one finding printed three times, which is
    # not what "representative" means.
    scored.sort(key=lambda item: (-item[0], item[1]["example_id"]))
    selected: list[dict[str, object]] = []
    seen: set[tuple] = set()
    for _, case in scored:
        signature = (
            tuple(case["missed_critical_spans"]),
            tuple(case["spurious_critical_spans"]),
        )
        if signature in seen:
            continue
        seen.add(signature)
        case["failure_signature"] = {
            "missed": list(signature[0]),
            "spurious": list(signature[1]),
        }
        selected.append(case)
        if len(selected) >= limit:
            break
    return selected


def build() -> dict[str, object]:
    examples = load_split()
    from alamatin.evaluation_metrics import canonical_json_sha256
    from alamatin.pipeline import REGEX_EXTRACTOR_VERSION

    extraction = measure_extraction(examples)
    decisions = measure_decision_stages(examples)
    latency = measure_latency(examples)
    failures = collect_failure_cases(examples)

    return {
        "schema_version": "1.0.0",
        "split": {
            "path": SPLIT.relative_to(ROOT).as_posix(),
            "example_count": len(examples),
            "canonical_sha256": canonical_json_sha256(
                json.loads(SPLIT.read_text(encoding="utf-8"))
            ),
            "note": (
                "synthetic split, chosen because the sealed set is authorized for "
                "one opening which is already spent"
            ),
        },
        "evaluator": {
            "module": "alamatin.evaluation_metrics",
            "note": "one evaluator for every row, which is what makes the rows comparable",
        },
        "measured_here": {
            "extractor_only": {
                "system": REGEX_EXTRACTOR_VERSION,
                **extraction,
            },
            **decisions,
        },
        "recorded_prior_measurements": RECORDED_PRIOR,
        "latency": latency,
        "failure_cases": failures,
        "interpretation_limits": [
            "The synthetic split is generated and must not be read as a proxy "
            "for real input. Note it is not uniformly easier: entity F1 is "
            "similar to the sealed run (0.892 here against 0.898 sealed), but "
            "critical exact match is markedly lower (0.393 here against 0.669 "
            "sealed), because the generator injects abbreviation, casing, and "
            "separator noise more aggressively than the sealed addresses "
            "exhibit. The sealed run remains the measurement of record for real "
            "input.",
            "libpostal and the NER candidates could not be executed here. Their "
            "numbers are recorded prior measurements, and the NER figures come "
            "from the selection split rather than this exact file.",
            "Stage latencies are measured independently and are not additive. "
            "The complete pipeline is roughly two orders of magnitude slower "
            "than extraction because the administrative validator searches the "
            "5,957-row reference per call; that is the cost centre, not the "
            "extractor.",
            "No row supports a claim about delivery outcomes.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the artifact")
    args = parser.parse_args()

    report = build()
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}")
        measured = report["measured_here"]
        print(f"  extractor F1            : {measured['extractor_only']['entity']['f1']}")
        print(
            f"  valid chain, no norm    : "
            f"{measured['extractor_plus_validator']['valid_chain_rate']}"
        )
        print(
            f"  valid chain, with norm  : "
            f"{measured['extractor_plus_normalizer_plus_validator']['valid_chain_rate']}"
        )
        print(f"  complete system statuses: {measured['complete_system']['quality_gate_status_counts']}")
        print(f"  failure cases collected : {len(report['failure_cases'])}")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run the ALM-015 regex/rule NER baseline and report metrics + latency.

Single command, fully deterministic (no learned parameters, no randomness):

    python scripts/run_regex_baseline.py --dataset data/synthetic/val.json

Only ever reads tokens from the dataset; gold labels are used solely to
score the baseline afterwards with the same entity-metric functions the main
evaluator uses (`alamatin.evaluation_metrics`), never to influence tagging.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.evaluation_metrics import (  # noqa: E402
    entity_metrics,
    entity_metrics_by_type,
    latency_summary_ms,
)
from alamatin.label_schema import validate_bio_sequence  # noqa: E402
from alamatin.pipeline import REGEX_EXTRACTOR_VERSION
from alamatin.regex_baseline import tag_tokens  # noqa: E402

DEFAULT_DATASET = ROOT / "data" / "synthetic" / "val.json"


class BaselineRunError(ValueError):
    """Raised when the baseline cannot be run or scored safely."""


#: Derived from the extractor version so a rule change cannot be recorded
#: under a label whose published numbers describe different rules.
BASELINE_LABEL = REGEX_EXTRACTOR_VERSION.replace('-', '_').replace('.', '_')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.loads(args.dataset.read_text(encoding="utf-8"))
        examples = payload["examples"]
        if not examples:
            raise BaselineRunError(f"{args.dataset} has no examples")

        gold_sequences: list[list[str]] = []
        predicted_sequences: list[list[str]] = []
        latencies_ms: list[float] = []

        for example in examples:
            tokens = example["tokens"]
            start = time.perf_counter()
            predicted = tag_tokens(tokens)
            latencies_ms.append((time.perf_counter() - start) * 1000)

            valid, reason = validate_bio_sequence(predicted)
            if not valid:
                raise BaselineRunError(f"{example.get('id', '?')}: baseline produced invalid BIO: {reason}")

            gold_sequences.append(example["labels"])
            predicted_sequences.append(predicted)

        overall = entity_metrics(gold_sequences, predicted_sequences)
        by_type = entity_metrics_by_type(gold_sequences, predicted_sequences)
        latency = latency_summary_ms(latencies_ms)

        report: dict[str, Any] = {
            "baseline": BASELINE_LABEL,
            "dataset": str(args.dataset),
            "example_count": len(examples),
            "overall": {
                "true_positive": overall.true_positive,
                "false_positive": overall.false_positive,
                "false_negative": overall.false_negative,
                "precision": overall.precision,
                "recall": overall.recall,
                "f1": overall.f1,
            },
            "by_type": {
                entity: {
                    "true_positive": result.true_positive,
                    "false_positive": result.false_positive,
                    "false_negative": result.false_negative,
                    "precision": result.precision,
                    "recall": result.recall,
                    "f1": result.f1,
                }
                for entity, result in by_type.items()
            },
            "latency_ms": {
                "sample_count": latency.sample_count,
                "p50": latency.p50_ms,
                "p95": latency.p95_ms,
            },
        }

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_name(f".{args.output.name}.part")
            temporary.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary.replace(args.output)
    except (OSError, KeyError, BaselineRunError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

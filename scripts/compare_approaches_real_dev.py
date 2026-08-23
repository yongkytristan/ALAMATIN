#!/usr/bin/env python3
"""Head-to-head comparison of every extraction approach on real addresses.

The four approaches were each measured at different times, by different
scripts, on different splits. Quoting those numbers side by side is not a
comparison -- it is four unrelated measurements in one table. This script
produces a real comparison by holding three things constant:

1. **One split.** `data/interim/evaluation-splits/real_dev.json`, 70 real
   addresses. Every row's dataset digest is verified byte-identical to it; a
   row measured on anything else is refused, not footnoted.
2. **One metric implementation.** Every row is recomputed from raw predicted
   BIO labels using `alamatin.evaluation_metrics`. No row inherits a number
   from its own artifact's `metrics.json`, so no row can carry a metric
   definition that has since changed.
3. **One decision about missing rows.** An approach that cannot be executed
   here is reported `not_measured` with the reason. It is never filled in from
   a different split, and never silently dropped.

Why `real_dev` and not the sealed set: the sealed evaluation is a one-time
protocol that has already been opened (ALM-035). Re-running four approaches
against it would destroy the property that makes its number trustworthy.
`real_dev` is designated comparison-only and never enters training or
checkpoint selection, which is exactly what this comparison needs.

Usage:
    python scripts/compare_approaches_real_dev.py
    python scripts/compare_approaches_real_dev.py --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.evaluation_metrics import (  # noqa: E402
    CRITICAL_ENTITY_TYPES,
    critical_exact_match,
    entity_metrics,
    entity_metrics_by_type,
    latency_summary_ms,
)
from alamatin.pipeline import REGEX_EXTRACTOR_VERSION  # noqa: E402
from alamatin.regex_baseline import tag_tokens as regex_tag_tokens  # noqa: E402

SPLIT = ROOT / "data" / "interim" / "evaluation-splits" / "real_dev.json"
#: The rule baseline was tuned on part of real_dev, so a figure over all 70
#: is no longer a clean estimate for it. The held-out half is the only subset
#: no approach in this table was tuned against.
PARTITION = (
    ROOT / "data" / "interim" / "evaluation-splits" / "real-dev-tuning-partition.json"
)
OUT_DIR = ROOT / "experiments" / "comparison-real-dev"
OUT = OUT_DIR / "results.json"

#: Model rows are read from their recorded predictions rather than re-run: the
#: checkpoints are release assets, and a prediction file plus a verified split
#: digest is sufficient to recompute every metric from scratch.
MODEL_ROWS = (
    ("ner_v1.0.0", "experiments/ner-v1-real-dev", "fine-tuned NER, first candidate"),
    (
        "ner_targeted_v2",
        "experiments/ner-targeted-v2-real-dev",
        "fine-tuned NER, selected candidate",
    ),
    (
        "ner_lora_kevin",
        "experiments/ner-lora-kevin-real-dev",
        "LoRA candidate",
    ),
)


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_split() -> tuple[list[dict], str]:
    payload = json.loads(SPLIT.read_text(encoding="utf-8"))
    digest = canonical_json_sha256(payload)
    examples = payload["examples"]
    if len(examples) != payload["example_count"]:
        raise SystemExit("real_dev example_count disagrees with its own examples")
    return examples, digest


def measure(gold: list[list[str]], predicted: list[list[str]]) -> dict:
    """Compute every reported metric from label sequences alone."""

    if len(gold) != len(predicted):
        raise ValueError(f"{len(gold)} gold sequences against {len(predicted)}")
    for index, (g, p) in enumerate(zip(gold, predicted)):
        if len(g) != len(p):
            raise ValueError(
                f"example {index}: {len(g)} gold labels against {len(p)} predicted"
            )

    overall = entity_metrics(gold, predicted)
    by_type = entity_metrics_by_type(gold, predicted)
    critical = critical_exact_match(gold, predicted)
    return {
        "entity": {
            "precision": overall.precision,
            "recall": overall.recall,
            "f1": overall.f1,
            "true_positive": overall.true_positive,
            "false_positive": overall.false_positive,
            "false_negative": overall.false_negative,
        },
        "critical_exact_match": {
            "numerator": critical.numerator,
            "denominator": critical.denominator,
            "rate": critical.rate,
        },
        "entity_by_type": {
            name: {
                "precision": result.precision,
                "recall": result.recall,
                "f1": result.f1,
                "true_positive": result.true_positive,
                "false_positive": result.false_positive,
                "false_negative": result.false_negative,
            }
            for name, result in sorted(by_type.items())
        },
    }


def run_regex(examples: list[dict]) -> tuple[list[list[str]], dict]:
    predicted: list[list[str]] = []
    latencies: list[float] = []
    for example in examples:
        tokens = list(example["tokens"])
        start = time.perf_counter()
        labels = regex_tag_tokens(tokens)
        latencies.append((time.perf_counter() - start) * 1000.0)
        predicted.append(labels)
    summary = latency_summary_ms(latencies)
    return predicted, {
        "p50_ms": summary.p50_ms,
        "p95_ms": summary.p95_ms,
        "sample_count": summary.sample_count,
    }


def run_libpostal(examples: list[dict]) -> tuple[list[list[str]], dict] | None:
    """Return libpostal predictions, or None when the native parser is absent.

    The adapter is deliberately not faked here. A deterministic stand-in would
    produce a number that looks like a measurement of libpostal and is not one.
    """

    try:
        import postal  # noqa: F401
    except ModuleNotFoundError:
        return None

    # The adapter's own entry point, with its default parser -- so this row is
    # produced by the same code path as scripts/run_libpostal_baseline.py and
    # not by a second, divergent adapter written here.
    from alamatin.libpostal_baseline import tag_tokens as libpostal_tag_tokens

    predicted: list[list[str]] = []
    latencies: list[float] = []
    for example in examples:
        tokens = list(example["tokens"])
        start = time.perf_counter()
        labels = libpostal_tag_tokens(tokens)
        latencies.append((time.perf_counter() - start) * 1000.0)
        predicted.append(labels)
    summary = latency_summary_ms(latencies)
    return predicted, {
        "p50_ms": summary.p50_ms,
        "p95_ms": summary.p95_ms,
        "sample_count": summary.sample_count,
    }


def read_model_predictions(
    directory: Path, examples: list[dict], split_digest: str
) -> tuple[list[list[str]], dict]:
    payload = json.loads((directory / "predictions.json").read_text(encoding="utf-8"))

    recorded = payload.get("dataset_canonical_json_sha256")
    if recorded != split_digest:
        raise SystemExit(
            f"{directory.name}: predictions were made against dataset "
            f"{recorded!r}, not the split being compared ({split_digest!r}). "
            "Refusing to place them in the same table."
        )
    if payload.get("split") != "real_dev":
        raise SystemExit(f"{directory.name}: split is {payload.get('split')!r}")

    # Align by address id rather than by position, so a reordered artifact
    # cannot silently pair one address's prediction with another's gold.
    by_id = {row["base_address_id"]: row for row in payload["examples"]}
    predicted: list[list[str]] = []
    for example in examples:
        row = by_id.get(example["base_address_id"])
        if row is None:
            raise SystemExit(
                f"{directory.name}: no prediction for {example['base_address_id']}"
            )
        predicted.append(list(row["evaluated_predicted_labels"]))

    provenance = {
        "model_sha256": payload.get("model_sha256"),
        "decoder": payload.get("decoder"),
        "bio_repairs_applied": sum(
            1 for row in payload["examples"] if row.get("bio_repairs")
        ),
    }
    return predicted, provenance


def _holdout_index(examples: list[dict]) -> list[int] | None:
    """Return positions of the held-out addresses, or None if unpartitioned."""

    if not PARTITION.is_file():
        return None
    partition = json.loads(PARTITION.read_text(encoding="utf-8"))
    holdout = set(partition["holdout"])
    index = [
        position
        for position, example in enumerate(examples)
        if example["base_address_id"] in holdout
    ]
    if len(index) != len(holdout):
        raise SystemExit(
            "the tuning partition names addresses this split does not contain"
        )
    return index


def build() -> dict:
    examples, split_digest = load_split()
    gold = [list(example["labels"]) for example in examples]

    rows: list[dict] = []

    holdout_index = _holdout_index(examples)

    def with_holdout(payload: dict, predicted: list[list[str]]) -> dict:
        if holdout_index is None:
            payload["held_out"] = None
            return payload
        payload["held_out"] = measure(
            [gold[i] for i in holdout_index], [predicted[i] for i in holdout_index]
        )
        return payload

    predicted, latency = run_regex(examples)
    rows.append(
        with_holdout(
            {
                "approach": f"regex_baseline ({REGEX_EXTRACTOR_VERSION})",
                "kind": "rule",
                "note": "the extractor the release candidate actually serves",
                "measured": True,
                "recomputed_from": "live run in this repository",
                "tuned_on_part_of_this_split": True,
                "latency_ms": latency,
                **measure(gold, predicted),
            },
            predicted,
        )
    )

    libpostal = run_libpostal(examples)
    if libpostal is None:
        rows.append(
            {
                "approach": "libpostal_v1",
                "kind": "external parser",
                "measured": False,
                "reason": (
                    "the native libpostal parser and its `postal` Python binding "
                    "are not installed in this environment, and the adapter "
                    "refuses to substitute a fake parser. Its recorded 0.3701 "
                    "entity F1 is on synthetic-dev, a different split, so it is "
                    "not carried into this table."
                ),
                "entity": None,
                "critical_exact_match": None,
                "entity_by_type": None,
            }
        )
    else:
        predicted, latency = libpostal
        rows.append(
            {
                "approach": "libpostal_v1",
                "kind": "external parser",
                "note": "general-purpose parser, no Indonesia-specific tuning",
                "measured": True,
                "recomputed_from": "live run in this repository",
                "latency_ms": latency,
                **measure(gold, predicted),
            }
        )

    for name, relative, note in MODEL_ROWS:
        directory = ROOT / relative
        if not (directory / "predictions.json").is_file():
            rows.append(
                {
                    "approach": name,
                    "kind": "fine-tuned model",
                    "measured": False,
                    "reason": f"{relative}/predictions.json is not present",
                    "entity": None,
                    "critical_exact_match": None,
                    "entity_by_type": None,
                }
            )
            continue
        predicted, provenance = read_model_predictions(directory, examples, split_digest)
        rows.append(
            with_holdout(
                {
                    "approach": name,
                    "kind": "fine-tuned model",
                    "note": note,
                    "measured": True,
                    "recomputed_from": f"{relative}/predictions.json",
                    "provenance": provenance,
                    "tuned_on_part_of_this_split": False,
                    "latency_ms": None,
                    **measure(gold, predicted),
                },
                predicted,
            )
        )

    measured = [row for row in rows if row["measured"]]
    # Ranked on the held-out half when it is available, because one row was
    # tuned on the rest and ranking on the full split would flatter it.
    def rank_key(row: dict) -> float:
        held = row.get("held_out")
        return (held["entity"] if held else row["entity"])["f1"]

    ranked = sorted(measured, key=rank_key, reverse=True)

    return {
        "schema_version": "1.0.0",
        "comparison": "extraction approaches on real addresses",
        "split": {
            "path": SPLIT.relative_to(ROOT).as_posix(),
            "name": "real_dev",
            "example_count": len(examples),
            "canonical_json_sha256": split_digest,
            "role": (
                "comparison-only; never used for training or checkpoint selection"
            ),
        },
        "method": {
            "metric_module": "alamatin.evaluation_metrics",
            "matching": "exact span, micro-averaged over entity types",
            "critical_entity_types": sorted(CRITICAL_ENTITY_TYPES),
            "every_row_recomputed": True,
            "sealed_set_used": False,
            "sealed_set_reason": (
                "the sealed evaluation is a one-time protocol already opened; "
                "re-running approaches against it would void its guarantee"
            ),
        },
        "rows": rows,
        "ranking_by_entity_f1": [row["approach"] for row in ranked],
        "not_measured": [row["approach"] for row in rows if not row["measured"]],
    }


def render(report: dict) -> str:
    lines = [
        f"split: {report['split']['name']} "
        f"({report['split']['example_count']} real addresses), "
        f"digest {report['split']['canonical_json_sha256'][:16]}",
        "",
        f"{'approach':22} {'entity F1':>10} {'precision':>10} {'recall':>8} "
        f"{'critical EM':>13}",
        "-" * 68,
    ]
    for row in report["rows"]:
        if not row["measured"]:
            lines.append(f"{row['approach']:22} {'not measured':>10}")
            continue
        entity = row["entity"]
        critical = row["critical_exact_match"]
        lines.append(
            f"{row['approach']:22} {entity['f1']:>10.4f} "
            f"{entity['precision']:>10.4f} {entity['recall']:>8.4f} "
            f"{critical['numerator']:>5}/{critical['denominator']:<3} "
            f"{critical['rate']:.3f}"
        )
    lines.append("")
    lines.append("ranking by entity F1: " + " > ".join(report["ranking_by_entity_f1"]))
    if report["not_measured"]:
        lines.append("not measured: " + ", ".join(report["not_measured"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    print(f"\nwritten to {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

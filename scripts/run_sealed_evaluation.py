#!/usr/bin/env python3
"""Run the one-time sealed evaluation of the release candidate (ALM-035).

Follows `docs/evaluation_protocol.md` section 9. The manifest hash is verified
before any example is read, the frozen system runs exactly once over each sealed
address, and the outputs are split by sensitivity:

* **restricted** — raw per-example predictions and timings, written under the
  custodian's gitignored directory;
* **repository** — aggregate metrics and provenance only, with no example id,
  token, or address text.

Usage:
    python scripts/run_sealed_evaluation.py --verify-only
    python scripts/run_sealed_evaluation.py --operator "Name <email>" --run
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SEALED_DIR = ROOT / "data" / "private" / "sealed-real-test"
SEALED_DATASET = SEALED_DIR / "sealed_real_test.json"
SEALED_MANIFEST = SEALED_DIR / "sealed-test-full-manifest.json"
BOUNDARY_MANIFEST = (
    ROOT / "data" / "interim" / "evaluation-splits" / "sealed-test-boundary-manifest.json"
)
RELEASE_MANIFEST = ROOT / "experiments" / "release-candidate" / "manifest.json"

PUBLISHED_RESULTS = ROOT / "experiments" / "sealed-evaluation" / "results.json"

SCHEMA_VERSION = "1.0.0"


class SealedRunError(RuntimeError):
    """Raised when the run must not proceed."""


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def verify_manifests() -> dict[str, object]:
    """Verify every hash before the sealed content is used for evaluation."""

    from alamatin.evaluation_metrics import canonical_json_sha256

    for path in (SEALED_DATASET, SEALED_MANIFEST, BOUNDARY_MANIFEST, RELEASE_MANIFEST):
        if not path.is_file():
            raise SealedRunError(
                f"required artifact missing: {path.relative_to(ROOT).as_posix()}. "
                "The sealed run happens in the custodian's environment, where the "
                "sealed dataset (data/private/**) and the committed boundary "
                "manifest (data/interim/**) are both available. Neither is "
                "published, so this command cannot run from a public clone."
            )

    dataset = json.loads(SEALED_DATASET.read_text(encoding="utf-8"))
    full = json.loads(SEALED_MANIFEST.read_text(encoding="utf-8"))
    boundary = json.loads(BOUNDARY_MANIFEST.read_text(encoding="utf-8"))

    computed = canonical_json_sha256(dataset)
    if computed != full["content_sha256"]:
        raise SealedRunError(
            "sealed dataset does not match its full manifest; refusing to open"
        )
    if computed != boundary["content_sha256"]:
        raise SealedRunError(
            "sealed dataset does not match the committed boundary manifest; "
            "refusing to open"
        )
    if len(dataset["examples"]) != full["example_count"] != boundary["example_count"]:
        raise SealedRunError("example count disagrees with the manifests")

    # Per-item digests, so a single swapped example cannot hide behind a
    # recomputed whole-file hash.
    per_item = full["per_item_sha256"]
    ordered = full["ordered_example_ids"]
    if len(per_item) != len(ordered) != len(dataset["examples"]):
        raise SealedRunError("per-item manifest length disagrees with the dataset")
    for example, example_id in zip(dataset["examples"], ordered):
        if example["base_address_id"] != example_id:
            raise SealedRunError("sealed example order does not match the manifest")
        if canonical_json_sha256(example) != per_item[example_id]:
            raise SealedRunError(f"sealed example digest mismatch: {example_id}")

    release = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))
    if release["sealed_test"]["authorized_openings"] < 1:
        raise SealedRunError("no sealed-test opening is authorized")

    return {
        "dataset_canonical_sha256": computed,
        "split_version": full["split_version"],
        "taxonomy_version": full["taxonomy_version"],
        "example_count": len(dataset["examples"]),
        "per_item_digests_verified": len(per_item),
        "release_manifest_versions": release["declared_versions"],
        "custodian_note": boundary["custodian"],
    }


def detokenize(tokens: list[str]) -> str:
    """Rebuild address text from tokens without inventing separators."""

    text = ""
    for token in tokens:
        if not text:
            text = token
        elif token in {",", ".", ";", ":"}:
            text += token
        else:
            text += " " + token
    return text


def gold_components(tokens: list[str], labels: list[str]) -> dict[str, str]:
    from alamatin.pipeline import decode_bio

    return decode_bio(tokens, labels)


def evaluate(operator: str) -> tuple[dict[str, object], dict[str, object]]:
    """Run the frozen system once and return (published, restricted) reports."""

    from alamatin.administrative_validator import (
        ADMINISTRATIVE_CONFLICT,
        AMBIGUOUS_CANDIDATES,
    )
    from alamatin.evaluation_metrics import (
        binary_recall,
        critical_exact_match,
        entity_metrics,
        entity_metrics_by_type,
        false_correction_rate,
        latency_summary_ms,
    )
    from alamatin.regex_baseline import tag_tokens
    from alamatin.service import load_pipeline

    provenance = verify_manifests()
    dataset = json.loads(SEALED_DATASET.read_text(encoding="utf-8"))
    examples = dataset["examples"]
    pipeline = load_pipeline()

    gold_sequences: list[list[str]] = []
    predicted_sequences: list[list[str]] = []
    latencies_ms: list[float] = []
    gold_flagworthy: list[bool] = []
    predicted_flagged: list[bool] = []
    proposal_correct: list[bool] = []
    status_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    per_provenance: dict[str, dict[str, list]] = {}
    per_example: list[dict[str, object]] = []

    for index, example in enumerate(examples):
        tokens = example["tokens"]
        gold = example["labels"]
        address_text = detokenize(tokens)

        # Extraction, timed on its own so the figure is the model's, not the
        # whole pipeline's.
        started = time.perf_counter()
        predicted = tag_tokens(tokens)
        latencies_ms.append((time.perf_counter() - started) * 1000)

        gold_sequences.append(gold)
        predicted_sequences.append(predicted)

        # The full frozen system, run exactly once per address.
        result = pipeline.process(
            address_text, request_id=f"sealed{index:08d}"
        )
        status = result.status
        status_counts[status] = status_counts.get(status, 0) + 1
        codes = [
            issue["reason_code"]
            for issue in result.document["quality_gate"]["issues"]
        ]
        for code in codes:
            reason_counts[code] = reason_counts.get(code, 0) + 1

        # Conflict/ambiguity ground truth is derived, not guessed: run the same
        # validator over the GOLD components. If it reports a conflict or an
        # ambiguity there, the address genuinely has that property given this
        # reference version, which is exactly what the gate claims to detect.
        gold_validation = pipeline.validator.validate(gold_components(tokens, gold))
        is_flagworthy = any(
            reason in (ADMINISTRATIVE_CONFLICT, AMBIGUOUS_CANDIDATES)
            for reason in gold_validation.reason_codes
        )
        gold_flagworthy.append(is_flagworthy)
        predicted_flagged.append(status in {"TIDAK_VALID", "PERLU_KONFIRMASI"})

        # A proposal is correct when it moves a field toward its gold value.
        gold_values = gold_components(tokens, gold)
        for correction in result.document["corrections"]:
            field = correction["field"]
            proposed = correction["proposed_value"]["value"].strip().casefold()
            expected = gold_values.get(field, "").strip().casefold()
            proposal_correct.append(bool(expected) and proposed == expected)

        bucket = per_provenance.setdefault(
            example["annotation_provenance"], {"gold": [], "pred": []}
        )
        bucket["gold"].append(gold)
        bucket["pred"].append(predicted)

        per_example.append(
            {
                "base_address_id": example["base_address_id"],
                "annotation_provenance": example["annotation_provenance"],
                "gold_labels": gold,
                "predicted_labels": predicted,
                "quality_gate_status": status,
                "reason_codes": codes,
                "gold_flagworthy": is_flagworthy,
            }
        )

    overall = entity_metrics(gold_sequences, predicted_sequences)
    by_type = entity_metrics_by_type(gold_sequences, predicted_sequences)
    critical = critical_exact_match(gold_sequences, predicted_sequences)
    flagging = binary_recall(gold_flagworthy, predicted_flagged)
    corrections = false_correction_rate(proposal_correct)
    latency = latency_summary_ms(latencies_ms)

    by_provenance = {
        name: {
            "example_count": len(bucket["gold"]),
            "entity": _metric_dict(entity_metrics(bucket["gold"], bucket["pred"])),
            "critical_exact_match": _rate_dict(
                critical_exact_match(bucket["gold"], bucket["pred"])
            ),
        }
        for name, bucket in sorted(per_provenance.items())
    }

    published: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "operator": operator,
            "commit": git("rev-parse", "HEAD"),
            "release_tag": _release_tag(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "openings_used": 1,
        },
        "dataset": {
            "split_version": provenance["split_version"],
            "taxonomy_version": provenance["taxonomy_version"],
            "canonical_sha256": provenance["dataset_canonical_sha256"],
            "example_count": provenance["example_count"],
            "per_item_digests_verified": provenance["per_item_digests_verified"],
            # No example id, token, or address text is published here by design.
            "content_published": False,
        },
        "system": provenance["release_manifest_versions"],
        "metrics": {
            "entity_overall": _metric_dict(overall),
            "entity_by_type": {name: _metric_dict(value) for name, value in sorted(by_type.items())},
            "critical_exact_match": _rate_dict(critical),
            "conflict_or_ambiguity_recall": {
                "true_positive": flagging.true_positive,
                "false_negative": flagging.false_negative,
                "recall": flagging.recall,
                "definition": (
                    "gold positive = the frozen validator reports a conflict or "
                    "ambiguity on the gold components; predicted positive = the "
                    "gate returned TIDAK_VALID or PERLU_KONFIRMASI"
                ),
            },
            "false_correction_rate": {
                **_rate_dict(corrections),
                "definition": (
                    "emitted correction proposals whose proposed value does not "
                    "equal the gold value for that field, over all proposals"
                ),
            },
            "quality_gate_status_counts": dict(sorted(status_counts.items())),
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "by_annotation_provenance": by_provenance,
            "extraction_latency_ms": {
                "sample_count": latency.sample_count,
                "p50": latency.p50_ms,
                "p95": latency.p95_ms,
                "protocol": (
                    "one timed call to tag_tokens per address, no warmup, "
                    "single process, measured with time.perf_counter"
                ),
            },
        },
        "evaluator_corrections": [],
        "evaluator_correction_policy": (
            "If an evaluator defect is found after this run, the correction is "
            "documented here together with both the original and corrected "
            "numbers. The better result is never selected quietly."
        ),
    }

    restricted: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run": published["run"],
        "dataset_canonical_sha256": provenance["dataset_canonical_sha256"],
        "warning": (
            "Contains per-example sealed content. Restricted to the custodian's "
            "location; never commit or publish."
        ),
        "examples": per_example,
    }
    return published, restricted


def _metric_dict(result) -> dict[str, object]:
    return {
        "true_positive": result.true_positive,
        "false_positive": result.false_positive,
        "false_negative": result.false_negative,
        "precision": result.precision,
        "recall": result.recall,
        "f1": result.f1,
    }


def _rate_dict(result) -> dict[str, object]:
    return {
        "numerator": result.numerator,
        "denominator": result.denominator,
        "rate": result.rate,
    }


def _release_tag() -> str | None:
    try:
        return git("describe", "--tags", "--exact-match", "HEAD")
    except subprocess.CalledProcessError:
        try:
            return git("describe", "--tags", "--abbrev=0")
        except subprocess.CalledProcessError:
            return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify manifests without opening the test",
    )
    parser.add_argument("--run", action="store_true", help="perform the one-time run")
    parser.add_argument("--operator", default="", help="who performed the run")
    args = parser.parse_args()

    if args.verify_only:
        print(json.dumps(verify_manifests(), indent=2, sort_keys=True))
        return 0

    if not args.run:
        parser.error("pass --run to perform the one-time evaluation")
    if not args.operator.strip():
        parser.error("--operator is required: the run must be attributable")

    if PUBLISHED_RESULTS.is_file():
        raise SealedRunError(
            f"{PUBLISHED_RESULTS.relative_to(ROOT).as_posix()} already exists. "
            "Only one opening is authorized; remove it deliberately and record "
            "why before running again."
        )

    published, restricted = evaluate(args.operator.strip())

    PUBLISHED_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_RESULTS.write_text(
        json.dumps(published, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    stamp = published["run"]["started_at_utc"].replace(":", "").replace("-", "")[:15]
    restricted_path = SEALED_DIR / f"run-{stamp}" / "raw-predictions.json"
    restricted_path.parent.mkdir(parents=True, exist_ok=True)
    restricted_path.write_text(
        json.dumps(restricted, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"published aggregate : {PUBLISHED_RESULTS.relative_to(ROOT).as_posix()}")
    print(f"restricted raw      : {restricted_path.relative_to(ROOT).as_posix()}")
    metrics = published["metrics"]
    print(f"  entity F1              : {metrics['entity_overall']['f1']}")
    print(f"  critical exact match   : {metrics['critical_exact_match']['rate']}")
    print(f"  conflict/amb. recall   : {metrics['conflict_or_ambiguity_recall']['recall']}")
    print(f"  false correction rate  : {metrics['false_correction_rate']['rate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

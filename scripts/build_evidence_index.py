#!/usr/bin/env python3
"""Map every reportable claim to the artifact that supports it (ALM-038).

Each claim names the artifact, the exact path inside it, and the script that
produced it. Values are **read from the artifacts at build time**, never typed
here, so the index cannot drift from the evidence.

Two checks run over the result:

* every claim resolves to a real value in a real artifact;
* every document that cites a claim contains the value the artifact actually
  holds — so a stale number in prose fails rather than sitting there looking
  authoritative.

Claims with no supporting data are recorded as `not_measured` with the reason.
A missing measurement is a finding, not something to leave blank.

Usage:
    python scripts/build_evidence_index.py --write
    python scripts/build_evidence_index.py --verify
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

OUTPUT = ROOT / "experiments" / "evidence" / "index.json"

SEALED = "experiments/sealed-evaluation/results.json"
ABLATION = "experiments/ablation/results.json"
RELEASE = "experiments/release-candidate/manifest.json"
STUDY = "data/private/user-study/session-records.json"


def claim(
    claim_id: str,
    statement: str,
    artifact: str,
    pointer: tuple[str, ...],
    script: str,
    docs: tuple[str, ...],
    *,
    fmt: str = "{:.4f}",
    default: object = None,
) -> dict[str, object]:
    return {
        # A count of zero is absent from a counts mapping rather than present as
        # 0, and "zero addresses were ready" is precisely the finding, so an
        # explicit default is required rather than treating it as a lookup bug.
        "default": default,
        "id": claim_id,
        "statement": statement,
        "artifact": artifact,
        "pointer": list(pointer),
        "script": script,
        "documents": list(docs),
        "format": fmt,
    }


#: Every number this project may report. Adding a claim to a document without
#: adding it here means the verifier does not cover it, so the index is also the
#: list of what may be said.
CLAIMS = (
    claim(
        "sealed-entity-f1",
        "Entity F1 on the sealed real test set",
        SEALED,
        ("metrics", "entity_overall", "f1"),
        "scripts/run_sealed_evaluation.py",
        ("docs/evaluation-results.md",),
    ),
    claim(
        "sealed-entity-precision",
        "Entity precision on the sealed real test set",
        SEALED,
        ("metrics", "entity_overall", "precision"),
        "scripts/run_sealed_evaluation.py",
        ("docs/evaluation-results.md",),
    ),
    claim(
        "sealed-entity-recall",
        "Entity recall on the sealed real test set",
        SEALED,
        ("metrics", "entity_overall", "recall"),
        "scripts/run_sealed_evaluation.py",
        ("docs/evaluation-results.md",),
    ),
    claim(
        "sealed-critical-exact-match",
        "Critical exact match on the sealed real test set",
        SEALED,
        ("metrics", "critical_exact_match", "rate"),
        "scripts/run_sealed_evaluation.py",
        ("docs/evaluation-results.md",),
    ),
    claim(
        "sealed-ready-count",
        "Sealed addresses reaching SIAP_DIPROSES",
        SEALED,
        ("metrics", "quality_gate_status_counts", "SIAP_DIPROSES"),
        "scripts/run_sealed_evaluation.py",
        ("docs/evaluation-results.md",),
        fmt="{:d}",
        default=0,
    ),
    claim(
        "sealed-missing-admin-count",
        "Sealed addresses reporting MISSING_ADMINISTRATIVE_FIELDS",
        SEALED,
        ("metrics", "reason_code_counts", "MISSING_ADMINISTRATIVE_FIELDS"),
        "scripts/run_sealed_evaluation.py",
        ("docs/evaluation-results.md",),
        fmt="{:d}",
    ),
    claim(
        "ablation-regex-f1",
        "Shipped extractor entity F1 on the synthetic validation split",
        ABLATION,
        ("measured_here", "extractor_only", "entity", "f1"),
        "scripts/run_ablation.py",
        ("docs/ablation-and-latency.md",),
    ),
    claim(
        "ablation-regex-critical-exact-match",
        "Shipped extractor critical exact match on the synthetic validation split",
        ABLATION,
        ("measured_here", "extractor_only", "critical_exact_match", "rate"),
        "scripts/run_ablation.py",
        ("docs/ablation-and-latency.md",),
    ),
    claim(
        "ablation-normalizer-contribution",
        "Additional valid administrative chains contributed by the normalizer",
        ABLATION,
        ("measured_here", "normalizer_contribution", "additional_valid_chains"),
        "scripts/run_ablation.py",
        ("docs/ablation-and-latency.md",),
        fmt="{:d}",
    ),
    claim(
        "ablation-normalizer-changes",
        "Normalization changes applied on the synthetic validation split",
        ABLATION,
        ("measured_here", "normalizer_contribution", "total_changes"),
        "scripts/run_ablation.py",
        ("docs/ablation-and-latency.md",),
        fmt="{:,d}",
    ),
    claim(
        "ablation-libpostal-f1",
        "libpostal entity F1 on the same split (recorded prior measurement)",
        ABLATION,
        ("recorded_prior_measurements", "libpostal_v1", "entity_f1"),
        "scripts/run_libpostal_baseline.py",
        ("docs/ablation-and-latency.md",),
    ),
    claim(
        "latency-extraction-p50",
        "Extraction latency p50 in milliseconds",
        ABLATION,
        ("latency", "extraction", "p50"),
        "scripts/run_ablation.py",
        ("docs/ablation-and-latency.md",),
    ),
    claim(
        "latency-pipeline-p50",
        "Complete pipeline latency p50 in milliseconds",
        ABLATION,
        ("latency", "complete_pipeline", "p50"),
        "scripts/run_ablation.py",
        ("docs/ablation-and-latency.md",),
    ),
    claim(
        "release-extractor-version",
        "Extractor served by the release candidate",
        RELEASE,
        ("declared_versions", "extractor"),
        "scripts/build_release_manifest.py",
        ("docs/release-candidate.md", "docs/evaluation-results.md"),
        fmt="{}",
    ),
    claim(
        "release-frozen-file-count",
        "Files frozen in the release candidate",
        RELEASE,
        ("frozen_files",),
        "scripts/build_release_manifest.py",
        ("docs/release-candidate.md",),
        fmt="len",
    ),
)

#: Claims the project may want but cannot support yet. Recorded so a reader sees
#: the gap instead of an absence they might mistake for an oversight.
NOT_MEASURED = (
    {
        "id": "study-median-time",
        "statement": "Median seconds to decision, manual versus ALAMATIN",
        "status": "not_measured",
        "reason": "no user-study session has been run; see docs/user-study-protocol.md",
        "would_come_from": STUDY,
        "script": "scripts/analyze_user_study.py",
    },
    {
        "id": "study-critical-error-recall",
        "statement": "Recall of critical address errors, manual versus ALAMATIN",
        "status": "not_measured",
        "reason": "no user-study session has been run",
        "would_come_from": STUDY,
        "script": "scripts/analyze_user_study.py",
    },
    {
        "id": "study-false-corrections",
        "statement": "False corrections accepted by participants",
        "status": "not_measured",
        "reason": "no user-study session has been run",
        "would_come_from": STUDY,
        "script": "scripts/analyze_user_study.py",
    },
    {
        "id": "sealed-false-correction-rate",
        "statement": "False correction rate on the sealed set",
        "status": "not_measured",
        "reason": (
            "the release candidate emitted zero correction proposals, so the "
            "rate has no denominator; see docs/evaluation-results.md"
        ),
        "would_come_from": SEALED,
        "script": "scripts/run_sealed_evaluation.py",
    },
    {
        "id": "ner-head-to-head",
        "statement": "Fine-tuned NER versus the shipped baseline on one split",
        "status": "not_measured",
        "reason": (
            "model weights are a release asset excluded from the repository and "
            "not served; the recorded NER figures come from the selection split"
        ),
        "would_come_from": ABLATION,
        "script": "scripts/run_ablation.py",
    },
    {
        "id": "delivery-outcomes",
        "statement": "Any effect on delivery success, returns, or failed deliveries",
        "status": "out_of_scope",
        "reason": (
            "the frozen scope forbids the claim and nothing in this project "
            "measures a downstream outcome"
        ),
        "would_come_from": None,
        "script": None,
    },
)


class EvidenceError(RuntimeError):
    """Raised when a claim cannot be resolved to its evidence."""


def resolve(document: object, pointer: list[str]) -> object:
    value: object = document
    for key in pointer:
        if isinstance(value, dict):
            if key not in value:
                raise EvidenceError(f"missing key {key!r}")
            value = value[key]
        elif isinstance(value, list):
            value = value[int(key)]
        else:
            raise EvidenceError(f"cannot descend into {type(value).__name__}")
    return value


def format_value(value: object, fmt: str) -> str:
    if fmt == "len":
        return str(len(value))  # type: ignore[arg-type]
    if fmt == "{}":
        return str(value)
    return fmt.format(value)


def build() -> dict[str, object]:
    resolved: list[dict[str, object]] = []
    problems: list[str] = []

    for item in CLAIMS:
        artifact_path = ROOT / str(item["artifact"])
        if not artifact_path.is_file():
            problems.append(f"{item['id']}: artifact missing {item['artifact']}")
            continue
        document = json.loads(artifact_path.read_text(encoding="utf-8"))
        try:
            raw = resolve(document, list(item["pointer"]))
        except EvidenceError as exc:
            if item.get("default") is None:
                problems.append(f"{item['id']}: {exc}")
                continue
            raw = item["default"]
        display = format_value(raw, str(item["format"]))
        entry = {
            **{
                key: value
                for key, value in item.items()
                if key not in {"format", "default"}
            },
            "value": raw if not isinstance(raw, list) else len(raw),
            "display": display,
            "status": "measured",
        }
        resolved.append(entry)

        # Every citing document must contain the value the artifact holds.
        for doc in item["documents"]:  # type: ignore[union-attr]
            doc_path = ROOT / str(doc)
            if not doc_path.is_file():
                problems.append(f"{item['id']}: document missing {doc}")
                continue
            text = doc_path.read_text(encoding="utf-8")
            if display not in text:
                problems.append(
                    f"{item['id']}: {doc} does not contain the artifact value "
                    f"{display!r}"
                )

    return {
        "schema_version": "1.0.0",
        "claims": resolved,
        "not_measured": list(NOT_MEASURED),
        "problems": problems,
        "summary": {
            "measured": len(resolved),
            "not_measured": len(NOT_MEASURED),
            "problems": len(problems),
        },
        "policy": (
            "Values are read from artifacts at build time and never typed into "
            "this index. A document citing a claim must contain the artifact's "
            "value, so a stale number fails a check instead of looking "
            "authoritative."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    index = build()

    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}")

    print(
        f"measured {index['summary']['measured']}, "
        f"not measured {index['summary']['not_measured']}, "
        f"problems {index['summary']['problems']}"
    )
    for problem in index["problems"]:
        print(f"  - {problem}", file=sys.stderr)
    return 1 if index["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build the release-candidate freeze manifest (ALM-034).

Records every component that determines a result, each with its SHA-256, plus
the commit, the declared versions, the P1 in/out decision, and the sealed-test
authorization. The manifest is content-addressed so drift is detectable: a test
recomputes every digest and fails if the tree no longer matches.

Usage:
    python scripts/build_release_manifest.py            # print
    python scripts/build_release_manifest.py --write    # write the artifact
    python scripts/build_release_manifest.py --verify   # compare against the artifact
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MANIFEST_PATH = ROOT / "experiments" / "release-candidate" / "manifest.json"
SCHEMA_VERSION = "1.0.0"

#: Every file whose content can change a result. Anything not listed here must
#: not be able to alter an answer; that is what makes the freeze meaningful.
FROZEN_FILES = (
    # Extraction and normalization
    "src/alamatin/regex_baseline.py",
    "src/alamatin/tokenizer.py",
    "src/alamatin/label_schema.py",
    "src/alamatin/address_normalizer.py",
    # Validation and the decision rules
    "src/alamatin/reference_hierarchy.py",
    "src/alamatin/administrative_validator.py",
    "src/alamatin/quality_gate.py",
    # Privacy, assembly, transport
    "src/alamatin/pii.py",
    "src/alamatin/pipeline.py",
    "src/alamatin/output_contract.py",
    "src/alamatin/api.py",
    "src/alamatin/service.py",
    "src/alamatin/geocoding.py",
    # Contract and reference data
    "contracts/address-api.v1.schema.json",
    "data/processed/jabar-reference-v1-verified.json",
    # Dependency pin
    "requirements.lock",
)

#: P1 work and whether it is in the release candidate. Recorded explicitly so
#: "what shipped" is never inferred from the code.
P1_DECISIONS = {
    "ALM-029 consent-gated geocoding": {
        "in_release_candidate": False,
        "reason": (
            "implemented but disabled: no provider is configured, so no external "
            "call is possible and the parse path reports NOT_REQUESTED"
        ),
    },
    "ALM-030 map confirmation": {
        "in_release_candidate": False,
        "reason": "not implemented",
    },
    "ALM-031 batch CSV processing": {
        "in_release_candidate": False,
        "reason": "contract shape exists; the endpoint returns 501 FEATURE_NOT_ENABLED",
    },
    "ALM-016 libpostal comparison": {
        "in_release_candidate": False,
        "reason": "evidence only; not a runtime dependency",
    },
    "ALM-009 OSM street/landmark extraction": {
        "in_release_candidate": False,
        "reason": "evidence only; not a runtime dependency",
    },
}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def declared_versions() -> dict[str, str]:
    from alamatin.output_contract import CONTRACT_VERSION
    from alamatin.pipeline import NORMALIZER_VERSION, REGEX_EXTRACTOR_VERSION
    from alamatin.quality_gate import RULES_VERSION
    from alamatin.service import REFERENCE_VERSION

    return {
        "contract": CONTRACT_VERSION,
        "extractor": REGEX_EXTRACTOR_VERSION,
        "normalizer": NORMALIZER_VERSION,
        "validator": REFERENCE_VERSION,
        "reference_data": REFERENCE_VERSION,
        "quality_gate": RULES_VERSION,
    }


def decision_rules() -> dict[str, object]:
    """The frozen decision surface, recorded as data rather than prose."""

    from alamatin.administrative_validator import ADMINISTRATIVE_FIELDS
    from alamatin.label_schema import ENTITY_TYPES
    from alamatin.quality_gate import (
        QUALITY_REASON_CODES,
        QUALITY_STATUSES,
        SEVERITIES,
        STATUS_PRECEDENCE,
    )

    return {
        "entity_types": list(ENTITY_TYPES),
        "critical_validation_fields": list(ADMINISTRATIVE_FIELDS),
        "operational_statuses": list(QUALITY_STATUSES),
        "severities": list(SEVERITIES),
        "reason_codes": list(QUALITY_REASON_CODES),
        "status_precedence": [
            {"status": status, "when": condition} for status, condition in STATUS_PRECEDENCE
        ],
        # There is no score, threshold, or probability anywhere in the decision:
        # recorded so a reader does not go looking for one.
        "thresholds": None,
        "threshold_note": (
            "the gate is deterministic; no score, threshold, or probability "
            "participates in the operational status"
        ),
    }


def build() -> dict[str, object]:
    files = []
    missing = []
    for name in FROZEN_FILES:
        path = ROOT / name
        if not path.is_file():
            missing.append(name)
            continue
        files.append(
            {"path": name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        )
    if missing:
        raise SystemExit(f"cannot freeze: missing {', '.join(missing)}")

    return {
        "schema_version": SCHEMA_VERSION,
        "release_candidate": {
            # The parent of the commit that stores this manifest: the file cannot
            # contain the hash of the commit that adds it. The durable pointer is
            # the release tag, recorded in docs/release-candidate.md; identity is
            # established by the per-file digests below, which are stable.
            "built_from_commit": git("rev-parse", "HEAD"),
            "describe": git("describe", "--always"),
            "note": (
                "built_from_commit is the parent of the commit storing this "
                "manifest; verification compares file digests, not the commit"
            ),
        },
        "declared_versions": declared_versions(),
        "decision_rules": decision_rules(),
        "frozen_files": files,
        "model_checkpoint": {
            "served_in_release_candidate": False,
            "runtime_extractor": declared_versions()["extractor"],
            "note": (
                "The fine-tuned candidate ner-targeted-v2 is a release asset "
                "recorded in experiments/ner-final-candidate/release_manifest.json "
                "and is not served. versions.model reports the extractor that "
                "actually ran, so no response claims a model that did not."
            ),
        },
        "p1_features": P1_DECISIONS,
        "sealed_test": {
            "authorized_openings": 1,
            "opened": False,
            "authorization": (
                "The project owner authorized exactly one opening of the sealed "
                "test against this release candidate."
            ),
            "no_tuning_declaration": (
                "No model, rule, threshold, or reference change may be made in "
                "response to the sealed result. If the evaluator itself is found "
                "to be wrong, the correction is documented and both runs are "
                "reported; the better number is never quietly selected."
            ),
            "declaration_provenance": (
                "Recorded on the project owner's instruction. Per-member "
                "confirmations from the other collaborators are not recorded here."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="write the manifest")
    group.add_argument("--verify", action="store_true", help="compare with the artifact")
    args = parser.parse_args()

    manifest = build()

    if args.write:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {MANIFEST_PATH.relative_to(ROOT).as_posix()}")
        return 0

    if args.verify:
        if not MANIFEST_PATH.is_file():
            print("no manifest to verify", file=sys.stderr)
            return 1
        stored = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        drift = []
        stored_files = {item["path"]: item["sha256"] for item in stored["frozen_files"]}
        for item in manifest["frozen_files"]:
            if stored_files.get(item["path"]) != item["sha256"]:
                drift.append(item["path"])
        if stored["declared_versions"] != manifest["declared_versions"]:
            drift.append("declared_versions")
        if stored["decision_rules"] != manifest["decision_rules"]:
            drift.append("decision_rules")
        if drift:
            print("release candidate has drifted:", file=sys.stderr)
            for name in drift:
                print(f"- {name}", file=sys.stderr)
            return 1
        print("release candidate matches the manifest.")
        return 0

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verify ALM-014 split integrity: no base address crosses a split boundary.

Checks, in order:

1. Every synthetic split (train/val/test) confines each base_id's noised
   variants to that one split -- generate_synthetic_addresses.py already
   enforces this at generation time; this re-checks the committed files
   directly, since that is the actual release-time gate.
2. The human-noised `real_dev` and `sealed_real_test` splits never share a
   base_address_id. The sealed file lives only in the custodian's local,
   gitignored `data/private/` copy, so this check is skipped (not failed)
   when that file is absent -- most clones will never have it.
3. The synthetic and human-noised ID namespaces never collide (they use
   disjoint id shapes by construction, but this is asserted explicitly
   rather than assumed).
4. When the sealed file is present, its content hash matches the boundary
   manifest committed to the repo, so the two can never silently drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.evaluation_metrics import canonical_json_sha256  # noqa: E402

DEFAULT_SYNTHETIC_DIR = ROOT / "data" / "synthetic"
DEFAULT_SPLITS_DIR = ROOT / "data" / "interim" / "evaluation-splits"
DEFAULT_PRIVATE_SEALED = ROOT / "data" / "private" / "sealed-real-test" / "sealed_real_test.json"


class LeakageError(ValueError):
    """Raised when a leakage or integrity check fails."""


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _synthetic_base_id(example: dict[str, Any]) -> str:
    # Synthetic IDs are "SYN-{base_id:07d}-{variant_index:02d}"; the base_id
    # segment is what generate_synthetic_addresses.py actually confines to
    # one split, not the full per-variant id.
    return example["id"].rsplit("-", maxsplit=1)[0]


def check_synthetic_confinement(synthetic_dir: Path) -> None:
    base_ids_by_split: dict[str, set[str]] = {}
    for name in ("train", "val", "test"):
        payload = _load(synthetic_dir / f"{name}.json")
        base_ids_by_split[name] = {_synthetic_base_id(example) for example in payload["examples"]}

    names = list(base_ids_by_split)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            overlap = base_ids_by_split[left] & base_ids_by_split[right]
            if overlap:
                raise LeakageError(f"synthetic {left}/{right} share base_id(s): {sorted(overlap)[:5]}")


def check_human_noised_confinement(splits_dir: Path, sealed_path: Path) -> str:
    real_dev = _load(splits_dir / "real_dev.json")
    real_dev_ids = {example["base_address_id"] for example in real_dev["examples"]}

    if not sealed_path.exists():
        return "skipped (sealed file not present on this machine)"

    sealed = _load(sealed_path)
    sealed_ids = {example["base_address_id"] for example in sealed["examples"]}
    overlap = real_dev_ids & sealed_ids
    if overlap:
        raise LeakageError(f"real_dev/sealed_real_test share base_address_id(s): {sorted(overlap)[:5]}")
    return f"checked ({len(real_dev_ids)} real_dev vs {len(sealed_ids)} sealed, disjoint)"


def check_namespace_separation(synthetic_dir: Path, splits_dir: Path) -> None:
    synthetic_ids: set[str] = set()
    for name in ("train", "val", "test"):
        payload = _load(synthetic_dir / f"{name}.json")
        synthetic_ids.update(_synthetic_base_id(example) for example in payload["examples"])
    real_dev = _load(splits_dir / "real_dev.json")
    human_ids = {example["base_address_id"] for example in real_dev["examples"]}
    overlap = synthetic_ids & human_ids
    if overlap:
        raise LeakageError(f"synthetic and human-noised namespaces collide: {sorted(overlap)[:5]}")


def check_sealed_hash_matches_boundary_manifest(splits_dir: Path, sealed_path: Path) -> str:
    boundary = _load(splits_dir / "sealed-test-boundary-manifest.json")
    if not sealed_path.exists():
        return "skipped (sealed file not present on this machine)"
    sealed = _load(sealed_path)
    actual_hash = canonical_json_sha256(sealed)
    if actual_hash != boundary["content_sha256"]:
        raise LeakageError(
            f"sealed_real_test.json content hash {actual_hash} does not match "
            f"boundary manifest {boundary['content_sha256']}"
        )
    return "matched"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-dir", type=Path, default=DEFAULT_SYNTHETIC_DIR)
    parser.add_argument("--splits-dir", type=Path, default=DEFAULT_SPLITS_DIR)
    parser.add_argument("--sealed", type=Path, default=DEFAULT_PRIVATE_SEALED)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results: dict[str, str] = {}
    try:
        check_synthetic_confinement(args.synthetic_dir)
        results["synthetic_confinement"] = "passed"

        results["human_noised_confinement"] = check_human_noised_confinement(args.splits_dir, args.sealed)

        check_namespace_separation(args.synthetic_dir, args.splits_dir)
        results["namespace_separation"] = "passed"

        results["sealed_hash_matches_manifest"] = check_sealed_hash_matches_boundary_manifest(
            args.splits_dir, args.sealed
        )
    except (OSError, KeyError, LeakageError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

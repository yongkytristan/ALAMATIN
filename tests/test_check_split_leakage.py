from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location("check_split_leakage", ROOT / "scripts" / "check_split_leakage.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

from alamatin.evaluation_metrics import canonical_json_sha256  # noqa: E402


def _write_synthetic(directory: Path, splits: dict[str, list[int]]) -> None:
    for name, base_ids in splits.items():
        payload = {
            "examples": [
                {"id": f"SYN-{base_id:07d}-{variant:02d}", "tokens": ["x"], "labels": ["O"]}
                for base_id in base_ids
                for variant in range(3)
            ]
        }
        (directory / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


class SyntheticConfinementTest(unittest.TestCase):
    def test_passes_when_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            _write_synthetic(path, {"train": [1, 2], "val": [3], "test": [4]})
            MODULE.check_synthetic_confinement(path)  # should not raise

    def test_raises_when_a_base_id_leaks_across_splits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            _write_synthetic(path, {"train": [1, 2], "val": [2], "test": [4]})
            with self.assertRaises(MODULE.LeakageError):
                MODULE.check_synthetic_confinement(path)


class HumanNoisedConfinementTest(unittest.TestCase):
    def test_skips_when_sealed_file_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            splits_dir = Path(directory)
            (splits_dir / "real_dev.json").write_text(
                json.dumps({"examples": [{"base_address_id": "a"}]}), encoding="utf-8"
            )
            result = MODULE.check_human_noised_confinement(splits_dir, Path(directory) / "missing.json")
            self.assertIn("skipped", result)

    def test_raises_when_ids_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            splits_dir = Path(directory)
            (splits_dir / "real_dev.json").write_text(
                json.dumps({"examples": [{"base_address_id": "a"}, {"base_address_id": "b"}]}), encoding="utf-8"
            )
            sealed_path = splits_dir / "sealed.json"
            sealed_path.write_text(
                json.dumps({"examples": [{"base_address_id": "b"}, {"base_address_id": "c"}]}), encoding="utf-8"
            )
            with self.assertRaises(MODULE.LeakageError):
                MODULE.check_human_noised_confinement(splits_dir, sealed_path)

    def test_passes_when_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            splits_dir = Path(directory)
            (splits_dir / "real_dev.json").write_text(
                json.dumps({"examples": [{"base_address_id": "a"}]}), encoding="utf-8"
            )
            sealed_path = splits_dir / "sealed.json"
            sealed_path.write_text(
                json.dumps({"examples": [{"base_address_id": "b"}]}), encoding="utf-8"
            )
            result = MODULE.check_human_noised_confinement(splits_dir, sealed_path)
            self.assertIn("checked", result)


class HashMatchTest(unittest.TestCase):
    def test_matches_when_hash_is_correct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            splits_dir = Path(directory)
            sealed_payload = {"examples": [{"base_address_id": "a"}]}
            sealed_path = splits_dir / "sealed.json"
            sealed_path.write_text(json.dumps(sealed_payload), encoding="utf-8")
            boundary = {"content_sha256": canonical_json_sha256(sealed_payload)}
            (splits_dir / "sealed-test-boundary-manifest.json").write_text(json.dumps(boundary), encoding="utf-8")
            result = MODULE.check_sealed_hash_matches_boundary_manifest(splits_dir, sealed_path)
            self.assertEqual(result, "matched")

    def test_raises_when_hash_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            splits_dir = Path(directory)
            sealed_path = splits_dir / "sealed.json"
            sealed_path.write_text(json.dumps({"examples": []}), encoding="utf-8")
            (splits_dir / "sealed-test-boundary-manifest.json").write_text(
                json.dumps({"content_sha256": "deadbeef"}), encoding="utf-8"
            )
            with self.assertRaises(MODULE.LeakageError):
                MODULE.check_sealed_hash_matches_boundary_manifest(splits_dir, sealed_path)


if __name__ == "__main__":
    unittest.main()

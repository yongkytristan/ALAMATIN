"""Tests for the ALM-012 benchmark candidate selection tool."""

from __future__ import annotations

import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_address_benchmark_candidates",
    ROOT / "scripts" / "build_public_address_benchmark_candidates.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _raw_payload(source_id: str, rows: list[dict[str, str]]) -> dict[str, object]:
    return {"schema_version": "1.0.0", "source_id": source_id, "rows": rows}


def _row(npsn: str, kabupaten: str = "KABUPATEN BOGOR", address: str = "JL. CONTOH RT 01 RW 02") -> dict[str, str]:
    return {
        "npsn": npsn,
        "nama_sekolah": "SD N CONTOH",
        "status_sekolah": "NEGERI",
        "alamat_sekolah": address,
        "nama_kabupaten_kota": kabupaten,
        "kemendagri_nama_kecamatan": "CIBINONG",
        "tahun": "2023",
    }


class ExtractCandidatesTest(unittest.TestCase):
    def test_drops_rows_with_short_address_or_missing_hierarchy(self) -> None:
        payload = _raw_payload(
            "open_data_jabar_npsn_sd_2023",
            [
                _row("1"),
                _row("2", address="X"),
                {**_row("3"), "nama_kabupaten_kota": ""},
            ],
        )
        candidates = MODULE.extract_candidates("sd", payload)
        self.assertEqual([c["source_record_id"] for c in candidates], ["1"])

    def test_deduplicates_by_npsn(self) -> None:
        payload = _raw_payload("open_data_jabar_npsn_sd_2023", [_row("1"), _row("1")])
        candidates = MODULE.extract_candidates("sd", payload)
        self.assertEqual(len(candidates), 1)

    def test_base_address_id_encodes_level_and_npsn(self) -> None:
        payload = _raw_payload("open_data_jabar_npsn_sd_2023", [_row("42")])
        candidates = MODULE.extract_candidates("sd", payload)
        self.assertEqual(candidates[0]["base_address_id"], "npsn_sd_42")

    def test_never_carries_a_field_outside_the_public_facility_allowlist(self) -> None:
        payload = _raw_payload("open_data_jabar_npsn_sd_2023", [_row("1")])
        candidates = MODULE.extract_candidates("sd", payload)
        self.assertEqual(set(candidates[0]), set(MODULE.OUTPUT_FIELDS))


def _candidate(base_address_id: str, kabupaten: str, school_level: str = "SD") -> dict[str, str]:
    return {
        "base_address_id": base_address_id,
        "source_id": "open_data_jabar_npsn_sd_2023",
        "source_record_id": base_address_id,
        "school_level": school_level,
        "school_name": "SD N CONTOH",
        "status_sekolah": "NEGERI",
        "kabupaten_kota": kabupaten,
        "kecamatan": "CIBINONG",
        "reference_address": "JL. CONTOH RT 01 RW 02",
        "source_year": "2023",
    }


class StratifiedSelectTest(unittest.TestCase):
    def test_raises_on_empty_pool(self) -> None:
        with self.assertRaises(MODULE.CandidateSelectionError):
            MODULE.stratified_select([], target=5, rng=random.Random(1))

    def test_spreads_selection_across_kabupaten_before_repeating(self) -> None:
        candidates = [
            _candidate(f"npsn_sd_{kab}{i}", kab)
            for kab in ("A", "B", "C")
            for i in range(5)
        ]
        selected = MODULE.stratified_select(candidates, target=3, rng=random.Random(7))
        self.assertEqual(len({c["kabupaten_kota"] for c in selected}), 3)

    def test_is_deterministic_for_the_same_seed(self) -> None:
        candidates = [
            _candidate(f"npsn_sd_{kab}{i}", kab)
            for kab in ("A", "B")
            for i in range(10)
        ]
        first = MODULE.stratified_select(list(candidates), target=6, rng=random.Random(3))
        second = MODULE.stratified_select(list(candidates), target=6, rng=random.Random(3))
        self.assertEqual([c["base_address_id"] for c in first], [c["base_address_id"] for c in second])

    def test_never_selects_more_than_the_available_pool(self) -> None:
        candidates = [_candidate("npsn_sd_1", "KABUPATEN BOGOR")]
        selected = MODULE.stratified_select(candidates, target=50, rng=random.Random(1))
        self.assertEqual(len(selected), 1)


class CliTest(unittest.TestCase):
    def test_cli_writes_candidates_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_dir = Path(directory)
            rows = [_row(str(i), kabupaten=f"KAB{i % 3}") for i in range(20)]
            payload = _raw_payload("open_data_jabar_npsn_sd_2023", rows)
            (input_dir / "npsn-sd-raw.json").write_text(json.dumps(payload), encoding="utf-8")

            args = [
                sys.executable,
                "scripts/build_public_address_benchmark_candidates.py",
                "--input-dir", str(input_dir),
                "--levels", "sd",
                "--target", "9",
                "--seed", "5",
                "--output", str(input_dir / "candidates.csv"),
                "--summary", str(input_dir / "candidates-summary.json"),
            ]
            result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            summary = json.loads((input_dir / "candidates-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["selected_count"], 9)
            self.assertEqual(summary["pool_size_after_filtering"]["sd"], 20)


if __name__ == "__main__":
    unittest.main()

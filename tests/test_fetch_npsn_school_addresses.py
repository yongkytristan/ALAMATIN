"""Tests for the NPSN school-address fetch tool (ALM-012 acquisition step)."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_npsn_school_addresses",
    ROOT / "scripts" / "fetch_npsn_school_addresses.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _row(npsn: str) -> dict[str, str]:
    return {
        "npsn": npsn,
        "nama_sekolah": "SD N CONTOH",
        "status_sekolah": "NEGERI",
        "alamat_sekolah": "JL. CONTOH RT 01 RW 02",
        "nama_kabupaten_kota": "KABUPATEN BOGOR",
        "kemendagri_nama_kecamatan": "CIBINONG",
        "tahun": "2023",
    }


class FetchNpsnSchoolAddressesTest(unittest.TestCase):
    def test_fetch_level_paginates_until_total_record_is_reached(self) -> None:
        pages = [
            {"data": [_row("1"), _row("2")], "meta": {"total_record": 3}},
            {"data": [_row("3")], "meta": {"total_record": 3}},
        ]
        with mock.patch.object(MODULE, "_fetch_page", side_effect=pages) as fetch_page:
            payload = MODULE.fetch_level("sd", limit=2, delay=0, timeout=1, retries=1)
        self.assertEqual(fetch_page.call_count, 2)
        self.assertEqual(payload["row_count"], 3)
        self.assertEqual(payload["total_record_reported"], 3)
        self.assertEqual(payload["source_id"], "open_data_jabar_npsn_sd_2023")

    def test_fetch_level_raises_when_a_required_field_is_missing(self) -> None:
        broken_row = _row("1")
        del broken_row["alamat_sekolah"]
        pages = [{"data": [broken_row], "meta": {"total_record": 1}}]
        with mock.patch.object(MODULE, "_fetch_page", side_effect=pages):
            with self.assertRaises(MODULE.SchoolFetchError):
                MODULE.fetch_level("sd", limit=10, delay=0, timeout=1, retries=1)

    def test_fetch_level_raises_when_row_count_does_not_match_reported_total(self) -> None:
        pages = [{"data": [_row("1")], "meta": {"total_record": 5}}]
        with mock.patch.object(MODULE, "_fetch_page", side_effect=pages):
            with self.assertRaises(MODULE.SchoolFetchError):
                MODULE.fetch_level("sd", limit=10, delay=0, timeout=1, retries=1)

    def test_write_json_atomic_writes_readable_content_and_matching_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            checksum = MODULE.write_json_atomic(path, {"a": 1})
            content = path.read_text(encoding="utf-8")
            self.assertEqual(json.loads(content), {"a": 1})
            import hashlib

            self.assertEqual(hashlib.sha256(content.encode("utf-8")).hexdigest(), checksum)

    def test_main_refuses_to_overwrite_existing_output_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            existing = output_dir / "npsn-sd-raw.json"
            existing.write_text("{}", encoding="utf-8")
            exit_code = MODULE.main(["--levels", "sd", "--output-dir", str(output_dir)])
            self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()

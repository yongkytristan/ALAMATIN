from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_source_review_workbook import (  # noqa: E402
    _postal_decision,
    build_merged,
    parse_html_rows,
    validate_xlsx,
    write_xlsx,
)


class SourceReviewWorkbookTest(unittest.TestCase):
    def test_postal_decision_keeps_three_way_conflict_unresolved(self) -> None:
        self.assertEqual(
            _postal_decision("21156", "45468", "40377"),
            ("", "conflict_api_third_value", "yes"),
        )
        self.assertEqual(
            _postal_decision("40377", "45468", "40377"),
            ("40377", "conflict_api_supports_diskominfo", "yes"),
        )
        self.assertEqual(
            _postal_decision("40377", "40377", ""),
            ("40377", "agree", "no"),
        )

    def test_html_parser_preserves_leading_zero_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.xls"
            path.write_text(
                "<table><tr><td>1</td><td>ACEH</td><td>01</td>"
                "<td>ACEH</td><td>11</td></tr></table>",
                encoding="utf-8",
            )
            self.assertEqual(parse_html_rows(path)[0][2], "01")

    def test_xlsx_is_valid_and_writes_codes_as_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.xlsx"
            counts = write_xlsx(
                path,
                [("00_manifest", lambda: iter((("code",), ("00123",))))],
            )
            validate_xlsx(path, ["00_manifest"])
            self.assertEqual(counts["00_manifest"], (2, 1))
            with zipfile.ZipFile(path) as archive:
                worksheet = archive.read("xl/worksheets/sheet1.xml").decode()
            self.assertIn('t="inlineStr"', worksheet)
            self.assertIn(">00123<", worksheet)

    def test_xlsx_build_is_byte_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.xlsx"
            second = Path(directory) / "second.xlsx"
            sheets = [("00_manifest", lambda: iter((("code",), ("00123",))))]
            write_xlsx(first, sheets)
            write_xlsx(second, sheets)
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
            )

    def test_merged_candidate_does_not_guess_three_way_conflict(self) -> None:
        diskominfo = [{
            "kemendagri_kelurahan_kode": "32.04.13.2003",
            "kemendagri_provinsi_nama": "JAWA BARAT",
            "kemendagri_kota_nama": "KABUPATEN BANDUNG",
            "kemendagri_kecamatan_nama": "BANJARAN",
            "kemendagri_kelurahan_nama": "BANJARAN KULON",
            "kemendagri_kota_kode": "32.04",
            "kode_pos": "21156",
        }]
        odj = [{
            "kemendagri_kode_desa_kelurahan": "32.04.13.2003",
            "kode_pos": "45468",
        }]
        kodepos = [{
            "village_code": "32.04.13.2003",
            "postal_code": "40377",
            "snapshot": "2026-08-11",
        }]

        merged, conflicts, counts = build_merged(diskominfo, odj, kodepos)

        self.assertEqual(merged[0]["postal_candidate"], "")
        self.assertEqual(merged[0]["postal_accepted"], "")
        self.assertEqual(merged[0]["verification_status"], "review_required")
        self.assertEqual(merged[0]["postal_status"], "conflict_api_third_value")
        self.assertEqual(counts["conflict_api_third_value"], 1)
        self.assertTrue(
            any(row["issue_type"] == "conflict_api_third_value" for row in conflicts)
        )


if __name__ == "__main__":
    unittest.main()

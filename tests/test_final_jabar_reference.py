from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_final_jabar_reference import (  # noqa: E402
    FinalReferenceError,
    build_final_reference,
)


def consensus_row(code: str, name: str, status: str) -> dict[str, str]:
    diskominfo, odj, api = {
        "verified_consensus": ("16911", "16911", "16911"),
        "corroborated_candidate": ("16912", "16913", "16913"),
        "review_required": ("16914", "16915", "16916"),
    }[status]
    accepted = diskominfo if status == "verified_consensus" else ""
    candidate = odj if status == "corroborated_candidate" else ""
    return {
        "village_code": code,
        "province_code": "32",
        "province_name": "JAWA BARAT",
        "city_code": "32.01",
        "city_name": "KAB. BOGOR",
        "district_code": "32.01.01",
        "district_name": "CIBINONG",
        "village_name": name,
        "postal_code": accepted,
        "postal_code_candidate": candidate,
        "postal_code_diskominfo": diskominfo,
        "postal_code_open_data_jabar": odj,
        "postal_code_kodepos_dev": api,
        "postal_candidates": ";".join(sorted({diskominfo, odj, api})),
        "verification_status": status,
        "confidence": {
            "verified_consensus": "high",
            "corroborated_candidate": "medium",
            "review_required": "unresolved",
        }[status],
        "review_required": "no" if status == "verified_consensus" else "yes",
        "selected_reason": f"Fixture {status}.",
        "administrative_resolution_applied": "no",
        "former_village_code": "",
        "source_village_codes": (
            f"diskominfo:{code};open_data_jabar:{code};kodepos_dev:{code}"
        ),
        "source_ids": (
            "diskominfo_jabar_village_2024_unreviewed;"
            "open_data_jabar_postal_2023;kodepos_dev_rest_api"
        ),
        "source_rows": "diskominfo:2;open_data_jabar:2;kodepos_dev:2",
        "snapshot": "2026-08-11",
    }


def odj_row(code: str, name: str, bps_name: str = "") -> dict[str, str]:
    return {
        "kemendagri_kode_desa_kelurahan": code,
        "nama_bps_provinsi": "JAWA BARAT",
        "nama_kemendagri_provinsi": "JAWA BARAT",
        "kode_bps_provinsi": "32",
        "kode_kabupaten_kota": "3201",
        "nama_kabupaten_kota": "KABUPATEN BOGOR",
        "bps_kode_kecamatan": "3201010",
        "bps_nama_kecamatan": "CIBINONG",
        "kemendagri_nama_kecamatan": "CIBINONG",
        "bps_kode_desa_kelurahan": code.replace(".", ""),
        "bps_nama_desa_kelurahan": bps_name or name,
        "kemendagri_nama_desa_kelurahan": name,
    }


def diskominfo_row(code: str, name: str) -> dict[str, str]:
    return {
        "kemendagri_kelurahan_kode": code,
        "kemendagri_provinsi_nama": "JAWA BARAT",
        "kemendagri_kota_nama": "KAB. BOGOR",
        "kemendagri_kecamatan_nama": "CIBINONG",
        "kemendagri_kelurahan_nama": name,
        "bps_provinsi_kode": "32.0",
        "bps_kota_kode": "3201.0",
        "bps_kecamatan_kode": "3201010.0",
        "bps_kelurahan_kode": f"{code.replace('.', '')}.0",
        "bps_provinsi_nama": "JAWA BARAT",
        "bps_kota_nama": "KABUPATEN BOGOR",
        "bps_kecamatan_nama": "CIBINONG",
        "bps_kelurahan_nama": name,
    }


def observation(code: str, name: str) -> dict[str, str]:
    return {
        "source_id": "pos_indonesia_postcode_search",
        "snapshot": "2026-08-11",
        "village_code": code,
        "village_name": name,
        "postal_code": "16914",
        "evidence_url": "https://kodepos.posindonesia.co.id/CariKodepos",
        "note": "Selected fixture observation.",
    }


class FinalJabarReferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.consensus = [
            consensus_row("32.01.01.1001", "ALPHA", "verified_consensus"),
            consensus_row("32.01.01.1002", "BETA", "corroborated_candidate"),
            consensus_row("32.01.01.1003", "GAMMA", "review_required"),
        ]
        self.odj = [
            odj_row("32.01.01.1001", "ALPHA", "ALFA"),
            odj_row("32.01.01.1002", "BETA"),
            odj_row("32.01.01.1003", "GAMMA"),
        ]
        self.diskominfo = [
            diskominfo_row("32.01.01.1001", "ALPHA"),
            diskominfo_row("32.01.01.1002", "BETA"),
            diskominfo_row("32.01.01.1003", "GAMMA"),
        ]
        self.hashes = {
            "api": "a" * 64,
            "diskominfo": "b" * 64,
            "open_data_jabar": "c" * 64,
        }

    def test_final_package_keeps_nonverified_values_out_of_lookup(self) -> None:
        final, hierarchy, exceptions, summary = build_final_reference(
            self.consensus,
            self.odj,
            self.diskominfo,
            [observation("32.01.01.1003", "GAMMA")],
            source_hashes=self.hashes,
        )

        self.assertEqual(len(final), 3)
        self.assertEqual(len(hierarchy.rows), 1)
        self.assertEqual(len(exceptions), 2)
        self.assertEqual(hierarchy.lookup(village="ALFA").status, "exact")
        self.assertEqual(hierarchy.lookup(village="BETA").status, "not_found")
        unresolved = next(row for row in final if row["village_name"] == "GAMMA")
        self.assertEqual(unresolved["postal_code"], "")
        self.assertEqual(unresolved["postal_code_pos_indonesia_observed"], "16914")
        self.assertEqual(unresolved["pos_indonesia_match"], "diskominfo")
        self.assertEqual(unresolved["operational_status"], "unresolved_do_not_guess")
        self.assertEqual(summary["verified_lookup_rows"], 1)

    def test_duplicate_final_code_is_rejected(self) -> None:
        duplicated = [self.consensus[0], dict(self.consensus[0])]
        with self.assertRaises(FinalReferenceError):
            build_final_reference(
                duplicated,
                self.odj,
                self.diskominfo,
                [],
                source_hashes=self.hashes,
            )


if __name__ == "__main__":
    unittest.main()

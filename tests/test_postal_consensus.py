from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_postal_consensus import (  # noqa: E402
    build_consensus,
    load_resolutions,
)


RESOLUTIONS = ROOT / "data" / "kemendagri_code_resolutions.json"


class PostalConsensusTest(unittest.TestCase):
    def test_official_resolution_maps_retired_codes_to_active_codes(self) -> None:
        resolutions, document = load_resolutions(RESOLUTIONS)

        self.assertEqual(document["source_id"], "kemendagri_wilayah_2025")
        self.assertEqual(
            resolutions["32.09.39.2001"]["current_village_code"],
            "32.09.21.2016",
        )
        self.assertEqual(
            resolutions["32.09.39.2002"]["current_village_code"],
            "32.09.21.2017",
        )

    def test_only_three_source_consensus_is_accepted(self) -> None:
        resolutions, _ = load_resolutions(RESOLUTIONS)
        diskominfo = [
            {
                "kemendagri_kelurahan_kode": "32.09.39.2001",
                "kemendagri_kelurahan_nama": "SAMBENG",
                "kemendagri_kecamatan_nama": "SURANENGGALA",
                "kemendagri_kota_nama": "KAB. CIREBON",
                "kode_pos": "45659",
            },
            {
                "kemendagri_kelurahan_kode": "32.73.05.1002",
                "kemendagri_kelurahan_nama": "BRAGA",
                "kemendagri_kecamatan_nama": "SUMUR BANDUNG",
                "kemendagri_kota_nama": "KOTA BANDUNG",
                "kode_pos": "40111",
            },
            {
                "kemendagri_kelurahan_kode": "32.73.05.1001",
                "kemendagri_kelurahan_nama": "MERDEKA",
                "kemendagri_kecamatan_nama": "SUMUR BANDUNG",
                "kemendagri_kota_nama": "KOTA BANDUNG",
                "kode_pos": "40114",
            },
        ]
        odj = [
            {
                "kode_kemendagri_provinsi": "32",
                "kemendagri_kode_desa_kelurahan": "32.09.39.2001",
                "kemendagri_nama_desa_kelurahan": "SAMBENG",
                "kode_pos": "45151",
            },
            {
                "kode_kemendagri_provinsi": "32",
                "kemendagri_kode_desa_kelurahan": "32.73.05.1002",
                "kemendagri_nama_desa_kelurahan": "BRAGA",
                "kode_pos": "40111",
            },
            {
                "kode_kemendagri_provinsi": "32",
                "kemendagri_kode_desa_kelurahan": "32.73.05.1001",
                "kemendagri_nama_desa_kelurahan": "MERDEKA",
                "kode_pos": "40113",
            },
        ]
        api = [
            {
                "province_code": "32",
                "village_code": "32.09.21.2016",
                "village_name": "Sambeng",
                "postal_code": "45150",
            },
            {
                "province_code": "32",
                "village_code": "32.73.05.1002",
                "village_name": "Braga",
                "postal_code": "40111",
            },
            {
                "province_code": "32",
                "village_code": "32.73.05.1001",
                "village_name": "Merdeka",
                "postal_code": "40113",
            },
        ]

        rows, counts = build_consensus(
            diskominfo,
            odj,
            api,
            resolutions,
            snapshot="2026-08-11",
        )

        by_code = {row["village_code"]: row for row in rows}
        sambeng = by_code["32.09.21.2016"]
        self.assertEqual(sambeng["former_village_code"], "32.09.39.2001")
        self.assertEqual(sambeng["district_name"], "GUNUNG JATI")
        self.assertEqual(sambeng["postal_code"], "")
        self.assertEqual(sambeng["verification_status"], "review_required")

        braga = by_code["32.73.05.1002"]
        self.assertEqual(braga["postal_code"], "40111")
        self.assertEqual(braga["verification_status"], "verified_consensus")
        self.assertEqual(braga["review_required"], "no")
        merdeka = by_code["32.73.05.1001"]
        self.assertEqual(merdeka["postal_code"], "")
        self.assertEqual(merdeka["postal_code_candidate"], "40113")
        self.assertEqual(merdeka["verification_status"], "corroborated_candidate")
        self.assertEqual(merdeka["confidence"], "medium")
        self.assertEqual(merdeka["review_required"], "yes")
        self.assertEqual(counts, {
            "corroborated_candidate": 1,
            "review_required": 1,
            "verified_consensus": 1,
        })


if __name__ == "__main__":
    unittest.main()

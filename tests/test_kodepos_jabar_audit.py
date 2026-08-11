from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_kodepos_jabar import (  # noqa: E402
    build_comparison,
    fetch_all_jabar,
    fetch_search_page,
)


def api_data(code: str, name: str, postal_code: str) -> dict:
    return {
        "code": code,
        "name": name,
        "postalCode": postal_code,
        "district": {"code": "32.73.05", "name": "Sumur Bandung"},
        "city": {"code": "32.73", "name": "Kota Bandung"},
        "province": {"code": "32", "name": "Jawa Barat"},
    }


class KodeposJabarAuditTest(unittest.TestCase):
    def test_search_page_uses_pagination_and_bearer(self) -> None:
        observed = {}

        def opener(request, *, timeout):
            observed["authorization"] = request.get_header("Authorization")
            observed["url"] = request.full_url
            observed["timeout"] = timeout
            return io.BytesIO(
                json.dumps(
                    {
                        "success": True,
                        "data": [api_data("32.73.05.1002", "Braga", "40111")],
                        "pagination": {
                            "hasNextPage": False,
                            "endCursor": None,
                            "total": 1,
                        },
                    }
                ).encode()
            )

        rows, pagination, _ = fetch_search_page(
            api_key="test-secret",
            after="cursor value",
            opener=opener,
            retries=0,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(pagination["total"], 1)
        self.assertEqual(observed["authorization"], "Bearer test-secret")
        self.assertIn("q=Jawa+Barat", observed["url"])
        self.assertIn("first=100", observed["url"])
        self.assertIn("after=cursor+value", observed["url"])

    def test_full_fetch_checkpoints_and_resumes_completed_result(self) -> None:
        calls = []
        pages = [
            (
                [api_data("32.73.05.1001", "Merdeka", "40113")],
                {"hasNextPage": True, "endCursor": "next", "total": 2},
                "https://example.invalid/page1",
            ),
            (
                [api_data("32.73.05.1002", "Braga", "40111")],
                {"hasNextPage": False, "endCursor": None, "total": 1},
                "https://example.invalid/page2",
            ),
        ]

        def page_fetcher(**kwargs):
            calls.append(kwargs["after"])
            return pages[len(calls) - 1]

        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            rows = fetch_all_jabar(
                api_key="test-secret",
                snapshot="2026-08-11",
                checkpoint=checkpoint,
                page_size=100,
                max_pages=10,
                delay=0,
                timeout=5,
                retries=0,
                page_fetcher=page_fetcher,
            )
            resumed = fetch_all_jabar(
                api_key="test-secret",
                snapshot="2026-08-11",
                checkpoint=checkpoint,
                page_size=100,
                max_pages=10,
                delay=0,
                timeout=5,
                retries=0,
                page_fetcher=lambda **kwargs: self.fail("completed audit refetched"),
            )

        self.assertEqual(calls, [None, "next"])
        self.assertEqual([row["village_code"] for row in rows], [
            "32.73.05.1001",
            "32.73.05.1002",
        ])
        self.assertEqual(resumed, rows)

    def test_comparison_separates_match_and_review_categories(self) -> None:
        api_rows = [
            {
                "village_code": "32.73.05.1001",
                "village_name": "Merdeka",
                "postal_code": "40113",
            },
            {
                "village_code": "32.73.05.1002",
                "village_name": "Braga",
                "postal_code": "40111",
            },
        ]
        diskominfo = [
            {
                "kemendagri_kelurahan_kode": "32.73.05.1001",
                "kemendagri_kelurahan_nama": "MERDEKA",
                "kode_pos": "40113",
            },
            {
                "kemendagri_kelurahan_kode": "32.73.05.1002",
                "kemendagri_kelurahan_nama": "BRAGA",
                "kode_pos": "40112",
            },
        ]
        odj = [
            {
                "kode_kemendagri_provinsi": "32",
                "kemendagri_kode_desa_kelurahan": "32.73.05.1001",
                "kemendagri_nama_desa_kelurahan": "MERDEKA",
                "kode_pos": "40113",
            },
            {
                "kode_kemendagri_provinsi": "32",
                "kemendagri_kode_desa_kelurahan": "32.73.05.1002",
                "kemendagri_nama_desa_kelurahan": "BRAGA",
                "kode_pos": "40110",
            },
        ]

        rows, counts = build_comparison(api_rows, diskominfo, odj)

        self.assertEqual(rows[0]["comparison_status"], "all_match")
        self.assertEqual(rows[0]["diskominfo_vs_open_data_jabar"], "match")
        self.assertEqual(rows[0]["postal_review_required"], "no")
        self.assertEqual(rows[1]["comparison_status"], "api_differs_available_sources")
        self.assertEqual(rows[1]["diskominfo_vs_open_data_jabar"], "different")
        self.assertEqual(rows[1]["postal_review_required"], "yes")
        self.assertEqual(counts, {
            "all_match": 1,
            "api_differs_available_sources": 1,
        })


if __name__ == "__main__":
    unittest.main()

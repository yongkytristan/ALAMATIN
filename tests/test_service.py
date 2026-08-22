from __future__ import annotations

import io
import json
import logging
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from alamatin.output_contract import validate_contract_document  # noqa: E402
from alamatin.service import DEFAULT_REFERENCE_PATH, build_app  # noqa: E402
from test_api import asgi_request  # noqa: E402

READY = (
    "Jl. Asia Afrika No. 1, Kel. Braga, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 40111"
)
CONFLICT = (
    "Jl. Braga No. 5, Kel. Braga, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 99999"
)
MIXED_PII = f"Penerima: Budi Santoso 081234567890, {READY}"
RAW_NAME = "Budi Santoso"
RAW_PHONE = "081234567890"


def request_document(address_text: str, request_id: str) -> dict:
    return {
        "document_type": "address_parse_request",
        "schema_version": "1.0.0",
        "request_id": request_id,
        "input": {"address_text": address_text, "geocoding_consent": False},
    }


@unittest.skipUnless(
    DEFAULT_REFERENCE_PATH.exists(),
    "governed reference not present in this repository; see data/sources.md",
)
class ServiceIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """The served app must answer with real pipeline results, not stubs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = build_app()

    async def test_health_reports_a_ready_pipeline(self) -> None:
        status, _, body = await asgi_request(self.app, "GET", "/health")
        # Before the pipeline was wired this returned 503 with
        # pipeline: not_configured.
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "healthy")
        self.assertEqual(body["app"], "alive")
        self.assertEqual(body["dependencies"]["pipeline"]["status"], "ready")

    async def test_parse_returns_a_ready_contract_response(self) -> None:
        status, _, body = await asgi_request(
            self.app, "POST", "/parse", request_document(READY, "req_svc_ready1")
        )
        self.assertEqual(status, 200)
        validate_contract_document(body)
        self.assertEqual(body["document_type"], "address_parse_response")
        self.assertEqual(body["request_id"], "req_svc_ready1")
        self.assertEqual(body["quality_gate"]["status"], "SIAP_DIPROSES")

    async def test_parse_surfaces_a_high_severity_conflict(self) -> None:
        status, _, body = await asgi_request(
            self.app, "POST", "/parse", request_document(CONFLICT, "req_svc_bad001")
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["quality_gate"]["status"], "TIDAK_VALID")

    async def test_validate_uses_the_same_pipeline(self) -> None:
        status, _, body = await asgi_request(
            self.app, "POST", "/validate", request_document(READY, "req_svc_valid1")
        )
        self.assertEqual(status, 200)
        validate_contract_document(body)
        self.assertEqual(body["quality_gate"]["status"], "SIAP_DIPROSES")

    async def test_malformed_request_is_still_rejected_by_the_contract(self) -> None:
        status, _, body = await asgi_request(
            self.app, "POST", "/parse", {"address": READY}
        )
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], "REQUEST_VALIDATION_ERROR")

    async def test_no_raw_pii_in_response_or_logs(self) -> None:
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        root = logging.getLogger()
        root.addHandler(handler)
        previous = root.level
        root.setLevel(logging.DEBUG)
        try:
            status, _, body = await asgi_request(
                self.app, "POST", "/parse", request_document(MIXED_PII, "req_svc_pii01")
            )
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)

        self.assertEqual(status, 200)
        serialized = json.dumps(body, ensure_ascii=False)
        for secret in (RAW_NAME, RAW_PHONE):
            self.assertNotIn(secret, serialized)
            self.assertNotIn(secret, buffer.getvalue())

    async def test_geocode_and_batch_stay_disabled(self) -> None:
        for path, expected in (("/geocode", 403), ("/batch", 501)):
            with self.subTest(path=path):
                document = request_document(READY, "req_svc_geo001")
                if path == "/batch":
                    document = {
                        "document_type": "address_batch_request",
                        "schema_version": "1.0.0",
                        "request_id": "req_svc_batch1",
                        "items": [
                            {"address_text": READY, "geocoding_consent": False}
                        ],
                    }
                status, _, body = await asgi_request(self.app, "POST", path, document)
                self.assertEqual(status, expected)
                self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()

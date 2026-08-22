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


@unittest.skipUnless(
    DEFAULT_REFERENCE_PATH.exists(),
    "governed reference not present in this repository; see data/sources.md",
)
class ServiceRobustnessTest(unittest.IsolatedAsyncioTestCase):
    """Hostile and degenerate input must never crash or mislead the caller."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = build_app()

    async def parse(self, address_text: str, request_id: str = "req_rob_00001"):
        return await asgi_request(
            self.app, "POST", "/parse", request_document(address_text, request_id)
        )

    async def test_empty_address_is_a_client_error(self) -> None:
        status, _, body = await self.parse("")
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], "REQUEST_VALIDATION_ERROR")
        self.assertFalse(body["error"]["retryable"])

    async def test_whitespace_only_is_answered_not_failed(self) -> None:
        # Previously this returned 503 PIPELINE_FAILED with retryable=true, so a
        # client would retry forever over its own unusable input. It extracts no
        # components, so the frozen gate answers the same way punctuation-only
        # text is answered.
        for blank in ("     ", "\t\n  ", "\u00a0"):
            with self.subTest(blank=repr(blank)):
                status, _, body = await self.parse(blank, "req_rob_blank1")
                self.assertEqual(status, 200)
                self.assertEqual(body["quality_gate"]["status"], "PERLU_KONFIRMASI")

    async def test_degenerate_but_wellformed_input_is_answered(self) -> None:
        for label, text in (
            ("punctuation", ",,,...---"),
            ("digits", "40111"),
            ("emoji", "Jl. Braga \U0001f3e0 No. 1, Kota Bandung"),
            ("control chars", "Jl.\x00\x01 Braga No. 1"),
            ("many newlines", "Jl. Braga\n\n\n No. 1"),
            ("rtl text", "Jl. Braga \u202eNo. 1"),
        ):
            with self.subTest(case=label):
                status, _, body = await self.parse(text, "req_rob_degen1")
                self.assertEqual(status, 200)
                validate_contract_document(body)

    async def test_long_input_is_processed_without_error(self) -> None:
        status, _, body = await self.parse("Jl. " + "A" * 20000, "req_rob_long01")
        self.assertEqual(status, 200)
        validate_contract_document(body)

    async def test_oversized_body_is_refused_before_parsing(self) -> None:
        # The transport caps the body, so a huge payload cannot reach the
        # pipeline at all.
        app = build_app()
        app.max_request_bytes = 512
        status, _, body = await asgi_request(
            app, "POST", "/parse", request_document("Jl. " + "A" * 4000, "req_rob_big01")
        )
        self.assertEqual(status, 413)
        self.assertEqual(body["error"]["code"], "REQUEST_TOO_LARGE")

    async def test_wrong_document_type_is_rejected(self) -> None:
        document = request_document(READY, "req_rob_type01")
        document["document_type"] = "address_parse_response"
        status, _, body = await asgi_request(self.app, "POST", "/parse", document)
        self.assertEqual(status, 422)

    async def test_malformed_request_id_is_rejected(self) -> None:
        for bad in ("short", "has space", "x" * 80):
            with self.subTest(request_id=bad):
                status, _, _ = await asgi_request(
                    self.app, "POST", "/parse", request_document(READY, bad)
                )
                self.assertEqual(status, 422)

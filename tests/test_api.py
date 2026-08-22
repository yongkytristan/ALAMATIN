from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.api import (  # noqa: E402
    APIServiceError,
    DependencyCheck,
    create_app,
    error_document,
)
from alamatin.output_contract import validate_contract_document  # noqa: E402


EXAMPLES = ROOT / "contracts" / "examples"


def example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


async def asgi_request(
    app,
    method: str,
    path: str,
    document=None,
    *,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
):
    if raw_body is None:
        raw_body = b"" if document is None else json.dumps(document).encode("utf-8")
    sent = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"content-type", content_type.encode("ascii"))],
    }
    await app(scope, receive, send)
    start = next(item for item in sent if item["type"] == "http.response.start")
    body = b"".join(
        item.get("body", b"")
        for item in sent
        if item["type"] == "http.response.body"
    )
    return start["status"], dict(start["headers"]), json.loads(body)


def success_handler(request):
    response = example("success.response.json")
    response["request_id"] = request["request_id"]
    return response


async def ready_probe():
    return True, "ready"


class APIHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_alive_and_ready_dependencies(self):
        app = create_app(
            parse_handler=success_handler,
            validate_handler=success_handler,
            dependency_checks=(
                DependencyCheck("contract", ready_probe),
                DependencyCheck("model", ready_probe),
                DependencyCheck("reference", ready_probe),
            ),
        )
        status, headers, body = await asgi_request(app, "GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "healthy")
        self.assertEqual(body["app"], "alive")
        self.assertEqual(body["dependencies"]["model"]["status"], "ready")
        self.assertEqual(headers[b"cache-control"], b"no-store")

    async def test_health_distinguishes_alive_app_from_failed_dependency(self):
        async def failed_probe():
            return False, "model_missing"

        app = create_app(
            dependency_checks=(DependencyCheck("model", failed_probe),)
        )
        status, _, body = await asgi_request(app, "GET", "/health")
        self.assertEqual(status, 503)
        self.assertEqual(body["app"], "alive")
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["dependencies"]["model"]["detail"], "model_missing")

    async def test_noncritical_dependency_does_not_fail_readiness(self):
        async def failed_probe():
            return False, "optional_down"

        app = create_app(
            dependency_checks=(
                DependencyCheck("optional_geocoder", failed_probe, critical=False),
            )
        )
        status, _, body = await asgi_request(app, "GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "healthy")


class APIEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = create_app(
            parse_handler=success_handler,
            validate_handler=success_handler,
            dependency_checks=(DependencyCheck("pipeline", ready_probe),),
            timeout_seconds=0.05,
        )

    async def test_parse_and_validate_return_alm025_response(self):
        request = example("success.request.json")
        for path in ("/parse", "/validate"):
            with self.subTest(path=path):
                status, _, body = await asgi_request(self.app, "POST", path, request)
                self.assertEqual(status, 200)
                self.assertEqual(body["document_type"], "address_parse_response")
                self.assertEqual(body["request_id"], request["request_id"])
                validate_contract_document(body)

    async def test_invalid_input_returns_structured_422_without_calling_handler(self):
        calls = 0

        def handler(request):
            nonlocal calls
            calls += 1
            return success_handler(request)

        app = create_app(parse_handler=handler)
        request = example("success.request.json")
        request["input"]["address_text"] = ""
        status, _, body = await asgi_request(app, "POST", "/parse", request)
        self.assertEqual(status, 422)
        self.assertEqual(body["error"]["code"], "REQUEST_VALIDATION_ERROR")
        self.assertEqual(calls, 0)
        validate_contract_document(body)

    async def test_invalid_json_and_media_type_are_safe_errors(self):
        status, _, body = await asgi_request(
            self.app, "POST", "/parse", raw_body=b"{not-json"
        )
        self.assertEqual((status, body["error"]["code"]), (400, "INVALID_JSON"))
        status, _, body = await asgi_request(
            self.app,
            "POST",
            "/parse",
            raw_body=b"{}",
            content_type="text/plain",
        )
        self.assertEqual((status, body["error"]["code"]), (415, "UNSUPPORTED_MEDIA_TYPE"))

    async def test_internal_error_does_not_crash_process_or_leak_raw_address(self):
        secret_address = "RAW-ADDRESS-MUST-NOT-APPEAR-IN-LOGS"

        def failing_handler(request):
            raise RuntimeError(request["input"]["address_text"])

        app = create_app(parse_handler=failing_handler)
        request = example("success.request.json")
        request["input"]["address_text"] = secret_address
        with self.assertLogs("alamatin.api", level=logging.INFO) as captured:
            status, _, body = await asgi_request(app, "POST", "/parse", request)
        self.assertEqual(status, 500)
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn(secret_address, json.dumps(body))
        self.assertNotIn(secret_address, "\n".join(captured.output))
        healthy_status, _, _ = await asgi_request(app, "GET", "/health")
        self.assertIn(healthy_status, {200, 503})

    async def test_processing_timeout_returns_retryable_504(self):
        async def slow_handler(_):
            await asyncio.sleep(0.2)

        app = create_app(parse_handler=slow_handler, timeout_seconds=0.01)
        status, _, body = await asgi_request(
            app, "POST", "/parse", example("success.request.json")
        )
        self.assertEqual(status, 504)
        self.assertEqual(body["error"]["code"], "PROCESSING_TIMEOUT")
        self.assertTrue(body["error"]["retryable"])

    async def test_handler_contract_violation_becomes_internal_error(self):
        def invalid_handler(_):
            return {"unexpected": "shape"}

        app = create_app(parse_handler=invalid_handler)
        status, _, body = await asgi_request(
            app, "POST", "/parse", example("success.request.json")
        )
        self.assertEqual(status, 500)
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")

    async def test_unconfigured_pipeline_returns_structured_503(self):
        app = create_app()
        status, _, body = await asgi_request(
            app, "POST", "/parse", example("success.request.json")
        )
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "PIPELINE_UNAVAILABLE")
        self.assertTrue(body["error"]["retryable"])
        validate_contract_document(body)

    async def test_method_and_route_errors_use_shared_contract(self):
        for method, path, expected in (
            ("GET", "/parse", 405),
            ("POST", "/unknown", 404),
        ):
            with self.subTest(method=method, path=path):
                status, _, body = await asgi_request(self.app, method, path)
                self.assertEqual(status, expected)
                validate_contract_document(body)

    async def test_oversized_request_is_rejected_before_json_parsing(self):
        app = create_app(parse_handler=success_handler)
        app.max_request_bytes = 8
        status, _, body = await asgi_request(
            app, "POST", "/parse", raw_body=b"{" + b"x" * 20 + b"}"
        )
        self.assertEqual(status, 413)
        self.assertEqual(body["error"]["code"], "REQUEST_TOO_LARGE")

    async def test_geocode_contract_is_consent_gated_and_p1_disabled(self):
        request = example("success.request.json")
        request["input"]["geocoding_consent"] = False
        status, _, body = await asgi_request(self.app, "POST", "/geocode", request)
        self.assertEqual((status, body["error"]["code"]), (403, "CONSENT_REQUIRED"))
        request["input"]["geocoding_consent"] = True
        status, _, body = await asgi_request(self.app, "POST", "/geocode", request)
        self.assertEqual((status, body["error"]["code"]), (501, "FEATURE_NOT_ENABLED"))

    async def test_batch_contract_is_bounded_and_p1_disabled(self):
        batch = {
            "document_type": "address_batch_request",
            "schema_version": "1.0.0",
            "request_id": "req_batch_001",
            "items": [
                {"address_text": "Jalan Merdeka No. 1", "geocoding_consent": False}
            ],
        }
        status, _, body = await asgi_request(self.app, "POST", "/batch", batch)
        self.assertEqual((status, body["error"]["code"]), (501, "FEATURE_NOT_ENABLED"))
        batch["items"] = []
        status, _, body = await asgi_request(self.app, "POST", "/batch", batch)
        self.assertEqual((status, body["error"]["code"]), (422, "REQUEST_VALIDATION_ERROR"))


class APIErrorPathCannotCrashTests(unittest.IsolatedAsyncioTestCase):
    """The error path itself must satisfy "internal error does not crash".

    `error_document` validates what it builds, so an unusable code or message
    used to raise `ContractValidationError` from inside an `except` block and
    escape the application entirely. Handlers supply `APIServiceError` values,
    so the transport cannot assume they are contract-shaped.
    """

    def setUp(self):
        logging.getLogger("alamatin.api").addHandler(logging.NullHandler())

    async def _parse_with_error(self, error: APIServiceError):
        def handler(_request):
            raise error

        app = create_app(parse_handler=handler)
        return await asgi_request(
            app, "POST", "/parse", example("success.request.json")
        )

    async def test_unusable_error_code_or_message_still_yields_contract_error(self):
        for label, error in (
            ("empty message", APIServiceError("SOMETHING", "")),
            ("blank message", APIServiceError("SOMETHING", "   ")),
            ("empty code", APIServiceError("", "Something failed.")),
            ("non-string code", APIServiceError(None, "Something failed.")),
            ("non-string message", APIServiceError("SOMETHING", None)),
        ):
            with self.subTest(case=label):
                status, _, body = await self._parse_with_error(error)
                self.assertEqual(status, 503)
                validate_contract_document(body)
                self.assertTrue(body["error"]["code"].strip())
                self.assertTrue(body["error"]["message"].strip())

    async def test_usable_error_code_and_message_are_preserved(self):
        status, _, body = await self._parse_with_error(
            APIServiceError("UPSTREAM_UNAVAILABLE", "Reference service is down.")
        )
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "UPSTREAM_UNAVAILABLE")
        self.assertEqual(body["error"]["message"], "Reference service is down.")

    async def test_unusable_error_detail_is_replaced_not_raised(self):
        document = error_document(
            request_id=None,
            code="REQUEST_VALIDATION_ERROR",
            message="Broken.",
            retryable=False,
            details=({"field": "", "code": "", "message": None}, "not-a-mapping"),
        )
        validate_contract_document(document)
        details = document["error"]["details"]
        self.assertEqual(len(details), 2)
        for detail in details:
            self.assertIsNone(detail["field"])
            self.assertTrue(detail["code"].strip())
            self.assertTrue(detail["message"].strip())

    async def test_non_boolean_retryable_is_coerced(self):
        document = error_document(
            request_id="req_abc12345",
            code="INTERNAL_ERROR",
            message="Broken.",
            retryable="yes",
            details=(),
        )
        validate_contract_document(document)
        self.assertIs(document["error"]["retryable"], True)

    async def test_client_disconnect_is_not_reported_as_payload_too_large(self):
        app = create_app(parse_handler=success_handler)
        sent = []

        async def receive():
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/parse",
                "headers": [(b"content-type", b"application/json")],
            },
            receive,
            send,
        )
        starts = [item for item in sent if item["type"] == "http.response.start"]
        self.assertEqual(
            [item["status"] for item in starts],
            [],
            "a disconnected client must not be answered with 413",
        )


if __name__ == "__main__":
    unittest.main()

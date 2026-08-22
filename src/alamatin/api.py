"""Dependency-free ASGI transport for the ALAMATIN HTTP API contract."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
import inspect
import json
import logging
import re
from typing import Any

from .output_contract import (
    CONTRACT_VERSION,
    ContractValidationError,
    load_contract_schema,
    validate_contract_document,
)


LOGGER = logging.getLogger("alamatin.api")
MAX_REQUEST_BYTES = 64 * 1024
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]
DependencyProbe = Callable[[], Awaitable[tuple[bool, str]] | tuple[bool, str]]


FALLBACK_ERROR_CODE = "INTERNAL_ERROR"
FALLBACK_ERROR_MESSAGE = "The request could not be processed."


class _ClientDisconnected(Exception):
    """The peer went away before the body was fully read; nothing to answer."""


class APIServiceError(RuntimeError):
    """A safe service failure that may be exposed through the error contract."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    probe: DependencyProbe
    critical: bool = True


async def _invoke(callable_object, *args):
    if inspect.iscoroutinefunction(callable_object):
        return await callable_object(*args)
    value = await asyncio.to_thread(callable_object, *args)
    return await value if inspect.isawaitable(value) else value


async def _contract_probe() -> tuple[bool, str]:
    try:
        load_contract_schema()
    except (OSError, ValueError):
        return False, "contract_unavailable"
    return True, "ready"


async def _unconfigured_handler(_: dict[str, Any]) -> dict[str, Any]:
    raise APIServiceError(
        "PIPELINE_UNAVAILABLE",
        "The address-processing pipeline is not configured.",
        retryable=True,
    )


async def _unconfigured_probe() -> tuple[bool, str]:
    return False, "not_configured"


def _safe_request_id(document: object) -> str | None:
    if not isinstance(document, Mapping):
        return None
    value = document.get("request_id")
    return value if isinstance(value, str) and REQUEST_ID_RE.fullmatch(value) else None


def _usable_text(value: object, fallback: str) -> str:
    """Return contract-usable text, replacing anything blank or non-string."""

    return value if isinstance(value, str) and value.strip() else fallback


def _safe_detail(detail: object) -> dict[str, str | None]:
    if not isinstance(detail, Mapping):
        return {
            "field": None,
            "code": FALLBACK_ERROR_CODE,
            "message": FALLBACK_ERROR_MESSAGE,
        }
    field = detail.get("field")
    return {
        "field": field if isinstance(field, str) and field.strip() else None,
        "code": _usable_text(detail.get("code"), FALLBACK_ERROR_CODE),
        "message": _usable_text(detail.get("message"), FALLBACK_ERROR_MESSAGE),
    }


def error_document(
    *,
    request_id: str | None,
    code: str,
    message: str,
    retryable: bool,
    details: Sequence[dict[str, str | None]] = (),
) -> dict[str, Any]:
    """Build a contract-valid error document, never raising on bad inputs.

    Handlers choose their own ``APIServiceError`` code and message, so these
    values are untrusted here. This function is called from ``except`` blocks;
    if it raised, the failure would escape the application and defeat the
    guarantee that an internal error still produces a structured response.
    """

    document = {
        "document_type": "api_error",
        "schema_version": CONTRACT_VERSION,
        "request_id": request_id if isinstance(request_id, str) else None,
        "error": {
            "code": _usable_text(code, FALLBACK_ERROR_CODE),
            "message": _usable_text(message, FALLBACK_ERROR_MESSAGE),
            "retryable": bool(retryable),
            "details": [_safe_detail(detail) for detail in details],
        },
    }
    try:
        validate_contract_document(document)
    except ContractValidationError:
        # Last resort: emit a document built only from frozen constants rather
        # than letting the error path raise.
        LOGGER.error("api_error_document_rejected code=%s", document["error"]["code"])
        document = {
            "document_type": "api_error",
            "schema_version": CONTRACT_VERSION,
            "request_id": None,
            "error": {
                "code": FALLBACK_ERROR_CODE,
                "message": FALLBACK_ERROR_MESSAGE,
                "retryable": True,
                "details": [],
            },
        }
        validate_contract_document(document)
    return document


class AlamatinAPI:
    """Small ASGI application with explicit privacy and dependency boundaries."""

    def __init__(
        self,
        *,
        parse_handler: Handler = _unconfigured_handler,
        validate_handler: Handler = _unconfigured_handler,
        dependency_checks: Sequence[DependencyCheck] | None = None,
        timeout_seconds: float = 10.0,
        max_request_bytes: int = MAX_REQUEST_BYTES,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be positive")
        self.parse_handler = parse_handler
        self.validate_handler = validate_handler
        self.timeout_seconds = timeout_seconds
        self.max_request_bytes = max_request_bytes
        self.dependency_checks = tuple(
            dependency_checks
            if dependency_checks is not None
            else (
                DependencyCheck("contract", _contract_probe),
                DependencyCheck("pipeline", _unconfigured_probe),
            )
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            return
        method = scope.get("method", "").upper()
        path = scope.get("path", "")
        if path == "/health":
            if method != "GET":
                await self._send_error(send, 405, None, "METHOD_NOT_ALLOWED", "Method not allowed.", False, path)
                return
            await self._health(send)
            return
        if path not in {"/parse", "/validate", "/geocode", "/batch"}:
            await self._send_error(send, 404, None, "NOT_FOUND", "Endpoint not found.", False, path)
            return
        if method != "POST":
            await self._send_error(send, 405, None, "METHOD_NOT_ALLOWED", "Method not allowed.", False, path)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            await self._send_error(send, 415, None, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json.", False, path)
            return

        try:
            body = await asyncio.wait_for(
                self._read_body(receive), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            await self._send_error(send, 408, None, "REQUEST_TIMEOUT", "Request body timed out.", True, path)
            return
        except _ClientDisconnected:
            # No peer is listening, so answering would be misleading: the old
            # behaviour reported 413 Payload Too Large for a plain disconnect.
            LOGGER.info("api_client_disconnected route=%s", path)
            return
        except APIServiceError as exc:
            await self._send_error(send, 413, None, exc.code, exc.safe_message, exc.retryable, path)
            return
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            await self._send_error(send, 400, None, "INVALID_JSON", "Request body must contain valid UTF-8 JSON.", False, path)
            return
        request_id = _safe_request_id(document)
        try:
            validate_contract_document(document)
        except ContractValidationError:
            await self._send_error(
                send,
                422,
                request_id,
                "REQUEST_VALIDATION_ERROR",
                "Request does not match the address API contract.",
                False,
                path,
                details=({"field": None, "code": "SCHEMA_MISMATCH", "message": "Review the versioned request schema."},),
            )
            return

        if path == "/geocode":
            if not document["input"]["geocoding_consent"]:
                await self._send_error(send, 403, request_id, "CONSENT_REQUIRED", "Explicit geocoding consent is required.", False, path)
            else:
                await self._send_error(send, 501, request_id, "FEATURE_NOT_ENABLED", "Geocoding is defined but not enabled in this release.", False, path)
            return
        if path == "/batch":
            await self._send_error(send, 501, request_id, "FEATURE_NOT_ENABLED", "Batch processing is defined but not enabled in this release.", False, path)
            return
        handler = self.parse_handler if path == "/parse" else self.validate_handler
        try:
            response = await asyncio.wait_for(
                _invoke(handler, document), timeout=self.timeout_seconds
            )
            validate_contract_document(response)
            if response.get("document_type") != "address_parse_response":
                raise ContractValidationError("handler must return an address response")
            if response.get("request_id") != request_id:
                raise ContractValidationError("handler response request_id mismatch")
        except asyncio.TimeoutError:
            await self._send_error(send, 504, request_id, "PROCESSING_TIMEOUT", "Address processing timed out.", True, path)
            return
        except APIServiceError as exc:
            await self._send_error(send, 503, request_id, exc.code, exc.safe_message, exc.retryable, path)
            return
        except Exception:
            LOGGER.error(
                "api_internal_error route=%s request_id=%s",
                path,
                request_id or "none",
            )
            await self._send_error(send, 500, request_id, "INTERNAL_ERROR", "The request could not be processed.", True, path)
            return
        await self._send_json(send, 200, response, path=path, request_id=request_id)

    async def _read_body(self, receive) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                raise _ClientDisconnected
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_request_bytes:
                raise APIServiceError("REQUEST_TOO_LARGE", "Request body is too large.")
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)

    async def _health(self, send) -> None:
        dependencies: dict[str, dict[str, object]] = {}
        critical_failure = False
        for check in self.dependency_checks:
            try:
                ready, detail = await asyncio.wait_for(
                    _invoke(check.probe), timeout=self.timeout_seconds
                )
            except Exception:
                ready, detail = False, "probe_failed"
            dependencies[check.name] = {
                "status": "ready" if ready else "failed",
                "detail": detail,
                "critical": check.critical,
            }
            critical_failure = critical_failure or (check.critical and not ready)
        document = {
            "status": "degraded" if critical_failure else "healthy",
            "app": "alive",
            "dependencies": dependencies,
        }
        await self._send_json(
            send,
            503 if critical_failure else 200,
            document,
            path="/health",
            request_id=None,
        )

    async def _send_error(
        self,
        send,
        status: int,
        request_id: str | None,
        code: str,
        message: str,
        retryable: bool,
        path: str,
        *,
        details: Sequence[dict[str, str | None]] = (),
    ) -> None:
        await self._send_json(
            send,
            status,
            error_document(
                request_id=request_id,
                code=code,
                message=message,
                retryable=retryable,
                details=details,
            ),
            path=path,
            request_id=request_id,
            error_code=code,
        )

    @staticmethod
    async def _send_json(
        send,
        status: int,
        document: dict[str, Any],
        *,
        path: str,
        request_id: str | None,
        error_code: str | None = None,
    ) -> None:
        body = json.dumps(
            document, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
        LOGGER.info(
            "api_request route=%s status=%d request_id=%s error_code=%s",
            path,
            status,
            request_id or "none",
            error_code or "none",
        )


def create_app(
    *,
    parse_handler: Handler = _unconfigured_handler,
    validate_handler: Handler = _unconfigured_handler,
    dependency_checks: Sequence[DependencyCheck] | None = None,
    timeout_seconds: float = 10.0,
) -> AlamatinAPI:
    return AlamatinAPI(
        parse_handler=parse_handler,
        validate_handler=validate_handler,
        dependency_checks=dependency_checks,
        timeout_seconds=timeout_seconds,
    )


app = create_app()


__all__ = [
    "APIServiceError",
    "AlamatinAPI",
    "DependencyCheck",
    "FALLBACK_ERROR_CODE",
    "FALLBACK_ERROR_MESSAGE",
    "MAX_REQUEST_BYTES",
    "app",
    "create_app",
    "error_document",
]

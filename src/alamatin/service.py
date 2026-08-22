"""Wire the address pipeline into the HTTP API.

`api.py` is deliberately transport-only and ships with unconfigured handlers.
This module supplies the real ones, so the served application reports a healthy
pipeline instead of `PIPELINE_UNAVAILABLE`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .administrative_validator import (
    AdministrativeValidationError,
    AdministrativeValidator,
)
from .api import APIServiceError, AlamatinAPI, DependencyCheck, create_app
from .output_contract import ContractValidationError
from .pipeline import AddressPipeline, PipelineError
from .reference_hierarchy import ReferenceHierarchy, ReferenceValidationError

ROOT = Path(__file__).resolve().parents[2]

#: Governed reference published for the public release. Overridable so a
#: deployment can point at a newer verified artifact without a code change.
DEFAULT_REFERENCE_PATH = ROOT / "data" / "processed" / "jabar-reference-v1-verified.json"
REFERENCE_PATH_ENV = "ALAMATIN_REFERENCE_PATH"
REFERENCE_VERSION = "jabar-reference-v1"


def reference_path() -> Path:
    override = os.environ.get(REFERENCE_PATH_ENV, "").strip()
    return Path(override) if override else DEFAULT_REFERENCE_PATH


def load_pipeline(path: Path | None = None) -> AddressPipeline:
    """Build a pipeline from the governed reference on disk."""

    source = path or reference_path()
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PipelineError(f"reference not readable: {source}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"reference is not valid JSON: {source}") from exc

    try:
        reference = ReferenceHierarchy.from_document(document)
        validator = AdministrativeValidator(
            reference, reference_version=REFERENCE_VERSION
        )
    except (ReferenceValidationError, AdministrativeValidationError) as exc:
        raise PipelineError(f"reference rejected: {exc}") from exc
    return AddressPipeline(validator)


def build_handler(pipeline: AddressPipeline):
    """Return a request handler over the given pipeline.

    Both `/parse` and `/validate` take the same frozen request document, so both
    run the same pass. Re-validation is a fresh evaluation of the submitted text
    rather than a stored session, which keeps the result reproducible from its
    input alone.
    """

    def handle(document: dict[str, Any]) -> dict[str, Any]:
        request_id = document["request_id"]
        payload = document["input"]
        try:
            result = pipeline.process(
                payload["address_text"],
                request_id=request_id,
                geocoding_consent=bool(payload.get("geocoding_consent", False)),
            )
        except (PipelineError, ContractValidationError) as exc:
            # The message is built from stage names and codes, never from input,
            # so it is safe to expose. Raw address text must not reach a client
            # error or a log line.
            raise APIServiceError(
                "PIPELINE_FAILED", f"Address processing failed: {type(exc).__name__}."
            ) from exc
        return result.document

    return handle


def build_app(path: Path | None = None, *, timeout_seconds: float = 10.0) -> AlamatinAPI:
    """Create an app whose pipeline and dependency probe are both real."""

    pipeline = load_pipeline(path)
    handler = build_handler(pipeline)

    def probe() -> tuple[bool, str]:
        # A cheap end-to-end assertion: the reference is loaded and the frozen
        # gate answers. Reporting "ready" without exercising the pipeline would
        # defeat the point of the health contract.
        try:
            pipeline.process(
                "Jl. Asia Afrika No. 1, Kel. Braga, Kec. Sumur Bandung, "
                "Kota Bandung, Jawa Barat 40111",
                request_id="health_probe_001",
            )
        except Exception:
            return False, "pipeline_probe_failed"
        return True, "ready"

    return create_app(
        parse_handler=handler,
        validate_handler=handler,
        dependency_checks=(DependencyCheck("pipeline", probe),),
        timeout_seconds=timeout_seconds,
    )


#: Module-level app for `uvicorn alamatin.service:app`.
app = build_app()


__all__ = [
    "DEFAULT_REFERENCE_PATH",
    "REFERENCE_PATH_ENV",
    "REFERENCE_VERSION",
    "app",
    "build_app",
    "build_handler",
    "load_pipeline",
    "reference_path",
]

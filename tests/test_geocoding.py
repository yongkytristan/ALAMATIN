from __future__ import annotations

import io
import json
import logging
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.geocoding import (  # noqa: E402
    ADMIN_MISMATCH,
    GEOCODE_NOT_FOUND,
    GEOCODE_RATE_LIMITED,
    GEOCODE_TIMEOUT,
    GEOCODE_UNAVAILABLE,
    LOW_PRECISION,
    GeocodeCandidate,
    GeocodeError,
    GeocodeRateLimited,
    GeocodeTimeout,
    GeocodingService,
    cross_validate,
)
from alamatin.output_contract import validate_contract_document  # noqa: E402

ADDRESS = "Jl. Asia Afrika No. 1, Kel. Braga, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111"
OURS = {
    "KOTA_KABUPATEN": "Kota Bandung",
    "PROVINSI": "Jawa Barat",
    "KODEPOS": "40111",
}
SECRET_KEY = "super-secret-api-key-value"


class SpyProvider:
    """Records every call so an unconsented request cannot pass unnoticed."""

    name = "spy-provider"

    def __init__(self, candidate: GeocodeCandidate | None = None, error: Exception | None = None):
        self.candidate = candidate
        self.error = error
        self.calls: list[str] = []

    def lookup(self, address_text: str, *, timeout: float) -> GeocodeCandidate | None:
        self.calls.append(address_text)
        if self.error is not None:
            raise self.error
        return self.candidate


def rooftop(**overrides) -> GeocodeCandidate:
    values = {
        "latitude": -6.9219,
        "longitude": 107.6070,
        "precision": "rooftop",
        "provider": "spy-provider",
        "place_id": "place-123",
        "components": dict(OURS),
    }
    values.update(overrides)
    return GeocodeCandidate(**values)


class ConsentGateTest(unittest.TestCase):
    """Without consent there must be no external request at all."""

    def test_no_consent_makes_no_provider_call(self) -> None:
        provider = SpyProvider(rooftop())
        service = GeocodingService(provider)
        outcome = service.resolve(ADDRESS, consent=False, alamatin_values=OURS)
        self.assertEqual(provider.calls, [])
        self.assertEqual(outcome.block["status"], "NOT_REQUESTED")
        self.assertFalse(outcome.block["consent"])

    def test_disabled_service_makes_no_call_even_with_consent(self) -> None:
        # The default configuration has no provider: geocoding is P1 and off.
        service = GeocodingService()
        self.assertFalse(service.enabled)
        outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
        self.assertEqual(outcome.block["status"], "NOT_REQUESTED")

    def test_not_requested_block_satisfies_the_contract(self) -> None:
        block = GeocodingService().resolve(ADDRESS, consent=False).block
        self.assertIsNone(block["provider"])
        self.assertIsNone(block["latitude"])
        self.assertEqual(block["components"], [])
        self.assertIsNone(block["error_code"])


class PrecisionTest(unittest.TestCase):
    def test_rooftop_and_matching_admin_is_success(self) -> None:
        service = GeocodingService(SpyProvider(rooftop()))
        outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
        self.assertEqual(outcome.block["status"], "SUCCESS")
        self.assertEqual(outcome.findings, ())
        self.assertFalse(outcome.requires_confirmation)

    def test_rooftop_result_is_never_marked_confirmed(self) -> None:
        # A rooftop hit is not a verified location until a human confirms it.
        service = GeocodingService(SpyProvider(rooftop()))
        block = service.resolve(ADDRESS, consent=True, alamatin_values=OURS).block
        for component in block["components"]:
            self.assertFalse(component["result"]["confirmed"])
            self.assertEqual(component["result"]["source"], "returned_by_geocoder")

    def test_coarse_precision_requires_confirmation(self) -> None:
        for precision in ("street", "region", "locality", "approximate"):
            with self.subTest(precision=precision):
                service = GeocodingService(SpyProvider(rooftop(precision=precision)))
                outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
                self.assertEqual(outcome.block["status"], "AMBIGUOUS")
                self.assertIn(LOW_PRECISION, outcome.findings)
                self.assertTrue(outcome.requires_confirmation)

    def test_precision_is_always_reported(self) -> None:
        service = GeocodingService(SpyProvider(rooftop(precision="street")))
        block = service.resolve(ADDRESS, consent=True, alamatin_values=OURS).block
        self.assertEqual(block["precision"], "street")


class CrossValidationTest(unittest.TestCase):
    def test_disagreeing_admin_fields_require_confirmation(self) -> None:
        candidate = rooftop(
            components={**OURS, "KOTA_KABUPATEN": "Kabupaten Bandung"}
        )
        service = GeocodingService(SpyProvider(candidate))
        outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
        self.assertEqual(outcome.block["status"], "AMBIGUOUS")
        self.assertIn(ADMIN_MISMATCH, outcome.findings)
        self.assertEqual(outcome.mismatched_fields, ("KOTA_KABUPATEN",))

    def test_comparison_ignores_case_and_padding(self) -> None:
        candidate = rooftop(components={"KOTA_KABUPATEN": "  kota BANDUNG "})
        self.assertEqual(cross_validate(candidate, OURS), ())

    def test_missing_field_on_either_side_is_not_a_mismatch(self) -> None:
        # Absence is not evidence of conflict.
        self.assertEqual(cross_validate(rooftop(components={}), OURS), ())
        self.assertEqual(cross_validate(rooftop(), {}), ())

    def test_every_cross_checked_field_is_compared(self) -> None:
        candidate = rooftop(
            components={
                "KOTA_KABUPATEN": "Kota Cimahi",
                "PROVINSI": "Banten",
                "KODEPOS": "99999",
            }
        )
        self.assertEqual(
            cross_validate(candidate, OURS),
            ("KOTA_KABUPATEN", "PROVINSI", "KODEPOS"),
        )


class FailureHandlingTest(unittest.TestCase):
    """A provider fault must never crash the request or invalidate the address."""

    def test_not_found_is_reported_without_coordinates(self) -> None:
        service = GeocodingService(SpyProvider(None))
        outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
        self.assertEqual(outcome.block["status"], "EXTERNAL_FAILURE")
        self.assertEqual(outcome.block["error_code"], GEOCODE_NOT_FOUND)
        self.assertIsNone(outcome.block["latitude"])

    def test_timeout_and_rate_limit_are_distinguished(self) -> None:
        for error, expected in (
            (GeocodeTimeout("slow"), GEOCODE_TIMEOUT),
            (GeocodeRateLimited("quota"), GEOCODE_RATE_LIMITED),
        ):
            with self.subTest(expected=expected):
                service = GeocodingService(SpyProvider(error=error))
                outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
                self.assertEqual(outcome.block["error_code"], expected)

    def test_unexpected_provider_fault_does_not_propagate(self) -> None:
        service = GeocodingService(SpyProvider(error=ValueError("boom")))
        outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
        self.assertEqual(outcome.block["error_code"], GEOCODE_UNAVAILABLE)

    def test_provider_exception_text_is_never_exposed(self) -> None:
        # A provider may quote the address or its key in an exception message.
        service = GeocodingService(
            SpyProvider(error=RuntimeError(f"{SECRET_KEY} failed on {ADDRESS}"))
        )
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        root = logging.getLogger()
        root.addHandler(handler)
        level = root.level
        root.setLevel(logging.DEBUG)
        try:
            outcome = service.resolve(ADDRESS, consent=True, alamatin_values=OURS)
        finally:
            root.removeHandler(handler)
            root.setLevel(level)
        serialized = json.dumps(outcome.block)
        for secret in (SECRET_KEY, ADDRESS):
            self.assertNotIn(secret, serialized)
            self.assertNotIn(secret, buffer.getvalue())


class ContractComplianceTest(unittest.TestCase):
    """Every block this module produces must survive contract validation."""

    def base_document(self) -> dict:
        document = json.loads(
            (ROOT / "contracts" / "examples" / "success.response.json").read_text(
                encoding="utf-8"
            )
        )
        return document

    def assert_valid_with(self, block: dict) -> None:
        document = self.base_document()
        document["geocoding"] = block
        validate_contract_document(document)

    def test_every_outcome_shape_is_contract_valid(self) -> None:
        cases = {
            "not_requested": GeocodingService().resolve(ADDRESS, consent=True),
            "success": GeocodingService(SpyProvider(rooftop())).resolve(
                ADDRESS, consent=True, alamatin_values=OURS
            ),
            "ambiguous_precision": GeocodingService(
                SpyProvider(rooftop(precision="street"))
            ).resolve(ADDRESS, consent=True, alamatin_values=OURS),
            "ambiguous_mismatch": GeocodingService(
                SpyProvider(rooftop(components={**OURS, "PROVINSI": "Banten"}))
            ).resolve(ADDRESS, consent=True, alamatin_values=OURS),
            "not_found": GeocodingService(SpyProvider(None)).resolve(
                ADDRESS, consent=True, alamatin_values=OURS
            ),
            "timeout": GeocodingService(SpyProvider(error=GeocodeTimeout())).resolve(
                ADDRESS, consent=True, alamatin_values=OURS
            ),
        }
        for name, outcome in cases.items():
            with self.subTest(case=name):
                self.assert_valid_with(outcome.block)

    def test_external_failure_leaves_the_address_decision_alone(self) -> None:
        # The quality gate is untouched by a geocoder fault: a SIAP_DIPROSES
        # address stays ready.
        document = self.base_document()
        document["geocoding"] = (
            GeocodingService(SpyProvider(error=GeocodeTimeout()))
            .resolve(ADDRESS, consent=True, alamatin_values=OURS)
            .block
        )
        validate_contract_document(document)
        self.assertEqual(document["quality_gate"]["status"], "SIAP_DIPROSES")


class CandidateValidationTest(unittest.TestCase):
    def test_out_of_range_coordinates_are_rejected(self) -> None:
        for kwargs in ({"latitude": 91.0}, {"longitude": -181.0}):
            with self.subTest(**kwargs):
                with self.assertRaises(GeocodeError):
                    rooftop(**kwargs)

    def test_non_numeric_coordinates_are_rejected(self) -> None:
        with self.assertRaisesRegex(GeocodeError, "must be a number"):
            rooftop(latitude="-6.9")

    def test_blank_precision_or_provider_is_rejected(self) -> None:
        for kwargs in ({"precision": " "}, {"provider": ""}):
            with self.subTest(**kwargs):
                with self.assertRaises(GeocodeError):
                    rooftop(**kwargs)

    def test_non_positive_timeout_is_rejected(self) -> None:
        with self.assertRaisesRegex(GeocodeError, "timeout_seconds"):
            GeocodingService(SpyProvider(rooftop()), timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()

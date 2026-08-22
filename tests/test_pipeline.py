from __future__ import annotations

import io
import json
import logging
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.administrative_validator import AdministrativeValidator  # noqa: E402
from alamatin.output_contract import validate_contract_document  # noqa: E402
from alamatin.pipeline import (  # noqa: E402
    REGEX_EXTRACTOR_VERSION,
    AddressPipeline,
    PipelineError,
    decode_bio,
    regex_extractor,
)
from alamatin.reference_hierarchy import ReferenceHierarchy  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))

REFERENCE = ROOT / "data" / "processed" / "jabar-reference-v1-verified.json"

# Real Jawa Barat chain, verified present in the governed reference.
READY = (
    "Jl. Asia Afrika No. 1, Kel. Braga, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 40111"
)
POSTCODE_CONFLICT = (
    "Jl. Braga No. 5, Kel. Braga, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 99999"
)
INCOMPLETE = "Jl. Merdeka No. 10, Kel. Braga"
UNKNOWN_VILLAGE = (
    "Jl. X No. 1, Kel. Tidakadanamaini, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 40111"
)
MIXED_PII = (
    "Penerima: Budi Santoso 081234567890, Jl. Asia Afrika No. 1, "
    "Kel. Braga, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111"
)
RAW_NAME = "Budi Santoso"
RAW_PHONE = "081234567890"


def build_pipeline() -> AddressPipeline:
    document = json.loads(REFERENCE.read_text(encoding="utf-8"))
    reference = ReferenceHierarchy.from_document(document)
    validator = AdministrativeValidator(reference, reference_version="jabar-reference-v1")
    return AddressPipeline(validator)


@unittest.skipUnless(
    REFERENCE.exists(),
    "governed reference not present in this repository; see data/sources.md",
)
class PipelineStatusTest(unittest.TestCase):
    """Every operational status the frozen gate can return has a case here."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = build_pipeline()

    def run_case(self, text: str, request_id: str):
        result = self.pipeline.process(text, request_id=request_id)
        # Every document is validated inside process(); re-assert here so a
        # regression in that call cannot pass unnoticed.
        validate_contract_document(result.document)
        return result

    def test_complete_address_is_ready(self) -> None:
        result = self.run_case(READY, "req_ready_0001")
        self.assertEqual(result.status, "SIAP_DIPROSES")
        self.assertEqual(result.document["quality_gate"]["issues"], [])

    def test_postcode_conflict_is_invalid(self) -> None:
        result = self.run_case(POSTCODE_CONFLICT, "req_invalid_001")
        self.assertEqual(result.status, "TIDAK_VALID")
        codes = [issue["reason_code"] for issue in result.document["quality_gate"]["issues"]]
        self.assertIn("KODEPOS_TIDAK_COCOK", codes)

    def test_missing_administrative_context_needs_confirmation(self) -> None:
        result = self.run_case(INCOMPLETE, "req_missing_001")
        self.assertEqual(result.status, "PERLU_KONFIRMASI")
        codes = [issue["reason_code"] for issue in result.document["quality_gate"]["issues"]]
        self.assertIn("MISSING_ADMINISTRATIVE_FIELDS", codes)

    def test_reference_coverage_gap_needs_confirmation(self) -> None:
        result = self.run_case(UNKNOWN_VILLAGE, "req_gap_00001")
        # A village the reference does not know is not proof the address is wrong.
        self.assertEqual(result.status, "PERLU_KONFIRMASI")
        codes = [issue["reason_code"] for issue in result.document["quality_gate"]["issues"]]
        self.assertIn("KELURAHAN_TIDAK_DITEMUKAN", codes)

    def test_mixed_pii_is_redacted_and_still_processed(self) -> None:
        result = self.run_case(MIXED_PII, "req_pii_00001")
        pii = result.document["pii"]
        self.assertIn("PII_DETECTED", pii["reason_codes"])
        self.assertNotIn(RAW_PHONE, pii["redacted_text"]["value"])
        self.assertNotIn(RAW_NAME, pii["redacted_text"]["value"])
        # The address itself still resolves; PII is not an address defect.
        self.assertEqual(result.status, "SIAP_DIPROSES")
        for entity in pii["entities"]:
            self.assertIn(entity["redacted_value"], {"[PHONE_REDACTED]", "[NAME_REDACTED]"})


@unittest.skipUnless(
    REFERENCE.exists(),
    "governed reference not present in this repository; see data/sources.md",
)
class PipelineSafetyTest(unittest.TestCase):
    """No silent correction, no raw-PII leakage, versions always reported."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = build_pipeline()

    def test_no_raw_pii_anywhere_in_the_response(self) -> None:
        result = self.pipeline.process(MIXED_PII, request_id="req_leak_0001")
        serialized = json.dumps(result.document, ensure_ascii=False)
        self.assertNotIn(RAW_PHONE, serialized)
        self.assertNotIn(RAW_NAME, serialized)

    def test_no_raw_pii_reaches_logs(self) -> None:
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        root = logging.getLogger()
        root.addHandler(handler)
        previous = root.level
        root.setLevel(logging.DEBUG)
        try:
            self.pipeline.process(MIXED_PII, request_id="req_log_00001")
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)
        logs = buffer.getvalue()
        self.assertNotIn(RAW_PHONE, logs)
        self.assertNotIn(RAW_NAME, logs)

    def test_no_correction_is_applied_without_user_confirmation(self) -> None:
        for text, request_id in (
            (READY, "req_sc_ready01"),
            (POSTCODE_CONFLICT, "req_sc_inval01"),
            (INCOMPLETE, "req_sc_miss001"),
            (UNKNOWN_VILLAGE, "req_sc_gap0001"),
        ):
            with self.subTest(request_id=request_id):
                result = self.pipeline.process(text, request_id=request_id)
                for correction in result.document["corrections"]:
                    self.assertFalse(correction["applied"])
                    self.assertIsNone(correction["user_confirmation"])
                    self.assertNotEqual(correction["decision"], "confirmed")

    def test_no_component_claims_user_confirmation_the_user_never_gave(self) -> None:
        result = self.pipeline.process(READY, request_id="req_prov_0001")
        for component in result.document["components"]:
            self.assertFalse(component["result"]["confirmed"])
            self.assertNotEqual(component["result"]["source"], "confirmed_by_user")

    def test_versions_report_what_actually_ran(self) -> None:
        result = self.pipeline.process(READY, request_id="req_ver_00001")
        versions = result.document["versions"]
        # The rule baseline must not be reported as a fine-tuned model.
        self.assertEqual(versions["model"], REGEX_EXTRACTOR_VERSION)
        self.assertEqual(versions["quality_gate"], "quality-gate-v1")
        for key in ("contract", "model", "normalizer", "validator", "reference_data"):
            self.assertTrue(versions[key].strip())

    def test_geocoding_is_never_silently_invoked(self) -> None:
        for consent in (False, True):
            with self.subTest(consent=consent):
                result = self.pipeline.process(
                    READY, request_id="req_geo_00001", geocoding_consent=consent
                )
                geocoding = result.document["geocoding"]
                self.assertEqual(geocoding["status"], "NOT_REQUESTED")
                # Consent on the request does not become consent on the result:
                # the parse path performs no lookup, so nothing was consented to.
                self.assertFalse(geocoding["consent"])
                self.assertIsNone(geocoding["provider"])
                self.assertEqual(geocoding["components"], [])

    def test_audit_trail_covers_every_stage_in_order(self) -> None:
        result = self.pipeline.process(POSTCODE_CONFLICT, request_id="req_audit_001")
        trail = result.document["audit_trail"]
        self.assertEqual(
            [event["sequence"] for event in trail],
            list(range(1, len(trail) + 1)),
        )
        stages = [event["stage"] for event in trail]
        for stage in ("pii", "model", "validator", "quality_gate"):
            self.assertIn(stage, stages)
        self.assertTrue(all(event["actor"] == "system" for event in trail))

    def test_audit_trail_records_no_pii_values(self) -> None:
        result = self.pipeline.process(MIXED_PII, request_id="req_audit_002")
        serialized = json.dumps(result.document["audit_trail"], ensure_ascii=False)
        self.assertNotIn(RAW_PHONE, serialized)
        self.assertNotIn(RAW_NAME, serialized)


class PipelineUnitTest(unittest.TestCase):
    """Stage-level behaviour that needs no governed reference."""

    def test_decode_bio_keeps_the_first_span_of_each_type(self) -> None:
        tokens = ["Jl.", "A", "Kel.", "B", "Kel.", "C"]
        labels = ["B-JALAN", "I-JALAN", "B-KELURAHAN", "I-KELURAHAN", "B-KELURAHAN", "I-KELURAHAN"]
        self.assertEqual(
            decode_bio(tokens, labels),
            {"JALAN": "Jl. A", "KELURAHAN": "Kel. B"},
        )

    def test_decode_bio_returns_fields_in_canonical_order(self) -> None:
        tokens = ["40111", "Jl.", "A"]
        labels = ["B-KODEPOS", "B-JALAN", "I-JALAN"]
        self.assertEqual(list(decode_bio(tokens, labels)), ["JALAN", "KODEPOS"])

    def test_decode_bio_rejects_mismatched_lengths(self) -> None:
        with self.assertRaisesRegex(PipelineError, "equal length"):
            decode_bio(["a"], ["B-JALAN", "O"])

    def test_orphan_inside_tag_does_not_start_an_entity(self) -> None:
        self.assertEqual(decode_bio(["a"], ["I-JALAN"]), {})

    def test_regex_extractor_returns_only_known_fields(self) -> None:
        extracted = regex_extractor(READY)
        self.assertTrue(extracted)
        from alamatin.label_schema import ENTITY_TYPES

        self.assertFalse(set(extracted) - set(ENTITY_TYPES))

    def test_blank_input_is_rejected(self) -> None:
        class _Stub:
            reference_version = "x"

        pipeline = AddressPipeline.__new__(AddressPipeline)
        with self.assertRaisesRegex(PipelineError, "address_text is required"):
            AddressPipeline.process(pipeline, "   ", request_id="req_blank_001")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(
    REFERENCE.exists(),
    "governed reference not present in this repository; see data/sources.md",
)
class PipelineGeocodingTest(unittest.TestCase):
    """Geocoding is delegated, off by default, and never changes the status."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reference = ReferenceHierarchy.from_document(
            json.loads(REFERENCE.read_text(encoding="utf-8"))
        )

    def pipeline(self, geocoding=None) -> AddressPipeline:
        validator = AdministrativeValidator(
            self.reference, reference_version="jabar-reference-v1"
        )
        return AddressPipeline(validator, geocoding=geocoding)

    def test_default_pipeline_never_geocodes(self) -> None:
        from alamatin.geocoding import GeocodingService

        result = self.pipeline().process(READY, request_id="req_geo_off001")
        self.assertFalse(GeocodingService().enabled)
        self.assertEqual(result.document["geocoding"]["status"], "NOT_REQUESTED")

    def test_consent_and_a_provider_produce_a_real_result(self) -> None:
        from test_geocoding import SpyProvider, rooftop
        from alamatin.geocoding import GeocodingService

        provider = SpyProvider(rooftop())
        result = self.pipeline(GeocodingService(provider)).process(
            READY, request_id="req_geo_on0001", geocoding_consent=True
        )
        self.assertEqual(provider.calls and len(provider.calls), 1)
        self.assertEqual(result.document["geocoding"]["status"], "SUCCESS")
        validate_contract_document(result.document)

    def test_a_geocoder_failure_does_not_invalidate_a_ready_address(self) -> None:
        from test_geocoding import SpyProvider
        from alamatin.geocoding import GeocodeTimeout, GeocodingService

        result = self.pipeline(
            GeocodingService(SpyProvider(error=GeocodeTimeout()))
        ).process(READY, request_id="req_geo_fail01", geocoding_consent=True)
        self.assertEqual(result.document["geocoding"]["status"], "EXTERNAL_FAILURE")
        # The address decision is untouched.
        self.assertEqual(result.status, "SIAP_DIPROSES")
        validate_contract_document(result.document)

    def test_the_provider_receives_pii_safe_text_only(self) -> None:
        from test_geocoding import SpyProvider, rooftop
        from alamatin.geocoding import GeocodingService

        provider = SpyProvider(rooftop())
        self.pipeline(GeocodingService(provider)).process(
            MIXED_PII, request_id="req_geo_pii001", geocoding_consent=True
        )
        sent = provider.calls[0]
        # A third party must never receive the recipient's name or phone.
        self.assertNotIn(RAW_NAME, sent)
        self.assertNotIn(RAW_PHONE, sent)

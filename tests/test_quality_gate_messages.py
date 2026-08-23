"""Tests for issue prose that names the reference value (ALM-024 follow-up).

An issue that says only "KECAMATAN" tells a seller which field disagreed and
nothing they can act on. These tests pin the three properties that make the new
messages worth having, and the two that keep them honest:

* the reference's own value appears, so the reader can compare;
* the submitted value appears beside it, so the disagreement is visible;
* a value absent from the reference is described as not matching the Jawa Barat
  reference data -- never as proof the address is wrong, which the reference
  cannot support;
* prose never changes the status, which stays a function of reason codes and
  severities alone;
* the enrichment is optional, so a caller without submitted values still gets a
  valid, contract-conformant issue.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.administrative_validator import (  # noqa: E402
    ADMINISTRATIVE_CONFLICT as VALIDATOR_CONFLICT,
    MISSING_FIELDS,
    REFERENCE_COVERAGE_GAP,
    AdministrativeValidationResult,
    ValidationCandidate,
)
from alamatin.quality_gate import (  # noqa: E402
    PERLU_KONFIRMASI,
    TIDAK_VALID,
    evaluate_quality_gate,
)

BRAGA = ValidationCandidate(
    record_id="32.73.01.1001",
    village_code="3273011001",
    village_name="BRAGA",
    district_name="SUMUR BANDUNG",
    city_name="KOTA BANDUNG",
    province_name="JAWA BARAT",
    postal_codes=("40111",),
)


def conflict(fields: tuple[str, ...]) -> AdministrativeValidationResult:
    return AdministrativeValidationResult(
        status="invalid",
        reason_codes=(VALIDATOR_CONFLICT,),
        affected_fields=fields,
        missing_fields=(),
        candidates=(BRAGA,),
        reference_version="jabar-reference-v1",
    )


class ConflictMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.result = evaluate_quality_gate(
            conflict(("KECAMATAN",)),
            submitted={
                "KELURAHAN": "Kelurahan Braga",
                "KECAMATAN": "Kecamatan Coblong",
                "KOTA_KABUPATEN": "Kota Bandung",
            },
        )
        self.issue = self.result.issues[0]

    def test_the_reference_value_is_named(self) -> None:
        self.assertIn("Sumur Bandung", self.issue.message)

    def test_the_submitted_value_is_named(self) -> None:
        self.assertIn("Coblong", self.issue.message)

    def test_the_resolved_village_anchors_the_claim(self) -> None:
        # Without the anchor the reader cannot tell why Sumur Bandung is
        # expected, so the message would be an assertion rather than evidence.
        self.assertIn("Braga", self.issue.message)

    def test_the_field_name_is_not_repeated_inside_the_value(self) -> None:
        # The normalizer prepends "Kecamatan"; showing "Kecamatan Kecamatan
        # Coblong" hands the reader back the label instead of the place.
        self.assertNotIn("Kecamatan Kecamatan", self.issue.message)

    def test_the_question_offers_both_values(self) -> None:
        self.assertIn("Sumur Bandung", self.issue.clarification_question)
        self.assertIn("Coblong", self.issue.clarification_question)
        self.assertTrue(self.issue.clarification_question.endswith("?"))

    def test_status_and_severity_are_unchanged(self) -> None:
        self.assertEqual(self.result.status, TIDAK_VALID)
        self.assertEqual(self.issue.severity, "high")
        self.assertEqual(self.issue.affected_fields, ("KECAMATAN",))

    def test_city_value_does_not_repeat_its_own_designator(self) -> None:
        issue = evaluate_quality_gate(
            conflict(("KOTA_KABUPATEN",)),
            submitted={"KELURAHAN": "Kelurahan Braga", "KOTA_KABUPATEN": "Kota Bogor"},
        ).issues[0]
        self.assertIn("Kota Bandung", issue.message)
        self.assertIn("Kota Bogor", issue.message)
        self.assertNotIn("kota/kabupaten Kota", issue.message)


class KodeposMessageTest(unittest.TestCase):
    def test_the_expected_postal_code_is_named(self) -> None:
        issue = evaluate_quality_gate(
            conflict(("KODEPOS",)),
            submitted={"KELURAHAN": "Kelurahan Braga", "KODEPOS": "99999"},
        ).issues[0]
        self.assertIn("40111", issue.message)
        self.assertIn("99999", issue.message)
        self.assertIn("40111", issue.clarification_question)


class CoverageGapMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        validation = AdministrativeValidationResult(
            status="not_found",
            reason_codes=(REFERENCE_COVERAGE_GAP,),
            affected_fields=(),
            missing_fields=(),
            candidates=(),
            reference_version="jabar-reference-v1",
        )
        self.result = evaluate_quality_gate(
            validation, submitted={"KELURAHAN": "Kelurahan Tidakada"}
        )
        self.issue = self.result.issues[0]

    def test_it_names_the_value_that_did_not_match(self) -> None:
        self.assertIn("Tidakada", self.issue.message)

    def test_it_cites_the_reference_scope(self) -> None:
        self.assertIn("Jawa Barat", self.issue.message)

    def test_it_does_not_claim_the_address_is_wrong(self) -> None:
        # limitations.md: a coverage gap must never be presented as proof the
        # address is wrong. This is the sentence that enforces it.
        self.assertIn("bukan bahwa alamat salah", self.issue.message)
        self.assertEqual(self.issue.severity, "medium")
        self.assertEqual(self.result.status, PERLU_KONFIRMASI)


class OptionalEnrichmentTest(unittest.TestCase):
    def test_messages_are_still_valid_without_submitted_values(self) -> None:
        result = evaluate_quality_gate(conflict(("KECAMATAN",)))
        issue = result.issues[0]
        self.assertTrue(issue.message.strip())
        self.assertTrue(issue.clarification_question.endswith("?"))
        self.assertEqual(result.status, TIDAK_VALID)
        # The reference value is still available without the submitted side.
        self.assertIn("Sumur Bandung", issue.message)

    def test_a_non_mapping_submitted_value_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            evaluate_quality_gate(conflict(("KECAMATAN",)), submitted=["KECAMATAN"])

    def test_submitted_conflict_values_do_not_change_the_status(self) -> None:
        # Prose input must not reach the conflict decision. Both sides carry a
        # street locator so the MISSING_STREET_LOCATOR rule -- the one declared
        # place where submitted values do affect the status (DEC-010) -- is out
        # of the picture, leaving only the prose path under test.
        baseline = evaluate_quality_gate(
            conflict(("KECAMATAN",)), submitted={"JALAN": "Jalan Braga"}
        )
        enriched = evaluate_quality_gate(
            conflict(("KECAMATAN",)),
            submitted={
                "JALAN": "Jalan Braga",
                "KECAMATAN": "apa saja",
                "KODEPOS": "00000",
            },
        )
        self.assertEqual(baseline.status, enriched.status)
        self.assertEqual(
            [issue.severity for issue in baseline.issues],
            [issue.severity for issue in enriched.issues],
        )
        self.assertEqual(
            [issue.reason_code for issue in baseline.issues],
            [issue.reason_code for issue in enriched.issues],
        )


class MissingFieldsMessageTest(unittest.TestCase):
    def test_it_names_fields_in_readable_form(self) -> None:
        validation = AdministrativeValidationResult(
            status="incomplete",
            reason_codes=(MISSING_FIELDS,),
            affected_fields=(),
            missing_fields=("KELURAHAN", "KECAMATAN"),
            candidates=(),
            reference_version="jabar-reference-v1",
        )
        issue = evaluate_quality_gate(validation).issues[0]
        self.assertIn("kelurahan/desa", issue.message)
        self.assertIn("kecamatan", issue.message)
        self.assertEqual(issue.severity, "medium")


if __name__ == "__main__":
    unittest.main()

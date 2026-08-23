"""Tests for the street-locator completeness rule (DEC-010).

The rule exists because an address can validate perfectly against the
administrative reference and still be undeliverable: "Kel. Braga, Kec. Sumur
Bandung, Kota Bandung 40111" named no street, and the gate called it
SIAP_DIPROSES.

The hard part is not detecting that. It is not over-detecting. On the real_dev
split 71% of genuine addresses carry no house number and 53% carry no
house-level locator at all, so requiring NOMOR would have flagged half of all
valid addresses. These tests pin both directions: the gap is caught, and the
kampung addresses that dominate real Indonesian input are not.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.administrative_validator import (  # noqa: E402
    VALID_CHAIN,
    AdministrativeValidationResult,
    ValidationCandidate,
)
from alamatin.quality_gate import (  # noqa: E402
    ADMINISTRATIVE_FIELDS,
    MISSING_STREET_LOCATOR,
    PERLU_KONFIRMASI,
    SIAP_DIPROSES,
    STREET_LOCATOR_FIELDS,
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

CHAIN = {
    "KELURAHAN": "Kelurahan Braga",
    "KECAMATAN": "Kecamatan Sumur Bandung",
    "KOTA_KABUPATEN": "Kota Bandung",
    "PROVINSI": "Jawa Barat",
    "KODEPOS": "40111",
}


def valid_chain() -> AdministrativeValidationResult:
    return AdministrativeValidationResult(
        status="valid",
        reason_codes=(VALID_CHAIN,),
        affected_fields=(),
        missing_fields=(),
        candidates=(BRAGA,),
        reference_version="jabar-reference-v1",
    )


def gate(**submitted: str):
    return evaluate_quality_gate(valid_chain(), submitted={**CHAIN, **submitted})


class TheGapIsCaughtTest(unittest.TestCase):
    def test_an_administratively_perfect_chain_with_no_street_is_flagged(self) -> None:
        # The exact defect reported: valid chain, nothing to deliver to.
        result = gate()
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertEqual(
            [issue.reason_code for issue in result.issues], [MISSING_STREET_LOCATOR]
        )

    def test_the_issue_is_medium_and_asks_rather_than_declares(self) -> None:
        # product-scope.md forbids treating the absence of JALAN as proof an
        # address is invalid: the reference cannot check a street name. High
        # severity would be exactly that claim.
        issue = gate().issues[0]
        self.assertEqual(issue.severity, "medium")
        self.assertTrue(issue.clarification_question.endswith("?"))

    def test_the_affected_field_is_not_treated_as_administrative(self) -> None:
        issue = gate().issues[0]
        self.assertEqual(issue.affected_fields, ("JALAN",))
        self.assertNotIn("JALAN", ADMINISTRATIVE_FIELDS)

    def test_an_empty_or_whitespace_street_counts_as_absent(self) -> None:
        for value in ("", "   ", "\t"):
            with self.subTest(value=repr(value)):
                self.assertEqual(gate(JALAN=value).status, PERLU_KONFIRMASI)


class RealAddressesAreNotOverFlaggedTest(unittest.TestCase):
    def test_a_street_name_clears_the_rule(self) -> None:
        self.assertEqual(gate(JALAN="Jalan Braga").status, SIAP_DIPROSES)

    def test_a_kampung_name_clears_the_rule(self) -> None:
        # "KP. CIMANGGU, KECAMATAN CIBEBER, KAB CIANJUR" is a normal address.
        self.assertEqual(gate(JALAN="Kampung Cimanggu").status, SIAP_DIPROSES)

    def test_a_landmark_alone_clears_the_rule(self) -> None:
        self.assertEqual(gate(DETAIL_LOKASI="Belakang Masjid Agung").status, SIAP_DIPROSES)

    def test_a_missing_house_number_is_not_flagged(self) -> None:
        # The decision that keeps this rule usable: 71% of real_dev addresses
        # have no NOMOR. Requiring it would flag most valid input.
        result = gate(JALAN="Jalan Braga")
        self.assertEqual(result.status, SIAP_DIPROSES)
        self.assertEqual(result.issues, ())

    def test_a_missing_rt_rw_is_not_flagged(self) -> None:
        self.assertEqual(gate(JALAN="Jalan Braga", NOMOR="").status, SIAP_DIPROSES)

    def test_nomor_is_not_a_street_locator(self) -> None:
        # A number with no street is still nothing a courier can find.
        self.assertEqual(gate(NOMOR="No. 5").status, PERLU_KONFIRMASI)
        self.assertNotIn("NOMOR", STREET_LOCATOR_FIELDS)


class NoSubmittedValuesTest(unittest.TestCase):
    def test_the_rule_stays_silent_without_component_values(self) -> None:
        # A caller that supplies no components has not told us the street is
        # absent, only that it did not say. Inventing an issue there would flag
        # every such caller.
        result = evaluate_quality_gate(valid_chain())
        self.assertEqual(result.status, SIAP_DIPROSES)
        self.assertEqual(result.issues, ())


if __name__ == "__main__":
    unittest.main()

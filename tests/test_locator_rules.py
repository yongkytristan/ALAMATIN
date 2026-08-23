"""Tests for the two delivery-completeness rules (DEC-010 and its amendment).

An address can validate perfectly against the administrative reference and still
be undeliverable. Two things have to be present:

* a **street locator** -- a street, kampung, or landmark naming where in the
  village to go;
* a **house locator** -- a number, RT/RW, or block naming which door.

Both are medium, never high: `product-scope.md` forbids treating the absence of
either as proof an address is invalid, because the governed reference cannot
check a street name or a house number. Asking is allowed; declaring is not.

The house rule replaces an earlier decision that deliberately skipped it. That
decision rested on 71% of `real_dev` addresses having no `NOMOR` -- but
`real_dev` is 200 **school** addresses, and a school is a landmark in its own
right. The product serves sellers shipping to homes, and the target user (R01,
fulfillment) named this exact failure: a package returned after eight days
because the address was "hanya nama perumahan tanpa nomor rumah". These tests
pin the corrected behaviour, including the case that reversed it.
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
    HOUSE_LOCATOR_FIELDS,
    MISSING_HOUSE_LOCATOR,
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


def codes(result) -> list[str]:
    return [issue.reason_code for issue in result.issues]


class CompleteAddressTest(unittest.TestCase):
    def test_street_and_number_pass(self) -> None:
        result = gate(JALAN="Jalan Braga", NOMOR="No. 5")
        self.assertEqual(result.status, SIAP_DIPROSES)
        self.assertEqual(result.issues, ())

    def test_kampung_with_rt_rw_passes(self) -> None:
        # How a kampung address is normally written. Requiring NOMOR alone would
        # flag this, and a courier can work with it.
        result = gate(JALAN="Kampung Cimanggu", RT="03", RW="05")
        self.assertEqual(result.status, SIAP_DIPROSES)
        self.assertEqual(result.issues, ())

    def test_a_block_detail_satisfies_the_house_rule(self) -> None:
        result = gate(JALAN="Perum Griya Asri", DETAIL_LOKASI="Blok C2")
        self.assertEqual(result.status, SIAP_DIPROSES)


class StreetLocatorRuleTest(unittest.TestCase):
    def test_a_chain_with_no_street_is_flagged(self) -> None:
        # The original defect: perfect chain, nothing to deliver to.
        self.assertIn(MISSING_STREET_LOCATOR, codes(gate(NOMOR="No. 5")))

    def test_it_is_medium_and_asks(self) -> None:
        issue = next(
            i for i in gate(NOMOR="No. 5").issues
            if i.reason_code == MISSING_STREET_LOCATOR
        )
        self.assertEqual(issue.severity, "medium")
        self.assertTrue(issue.clarification_question.endswith("?"))
        self.assertEqual(issue.affected_fields, ("JALAN",))
        self.assertNotIn("JALAN", ADMINISTRATIVE_FIELDS)

    def test_a_landmark_alone_satisfies_it(self) -> None:
        self.assertNotIn(
            MISSING_STREET_LOCATOR, codes(gate(DETAIL_LOKASI="Belakang Masjid Agung"))
        )

    def test_a_number_alone_does_not_satisfy_it(self) -> None:
        self.assertIn(MISSING_STREET_LOCATOR, codes(gate(NOMOR="No. 5")))
        self.assertNotIn("NOMOR", STREET_LOCATOR_FIELDS)


class HouseLocatorRuleTest(unittest.TestCase):
    def test_the_case_that_reversed_the_earlier_decision(self) -> None:
        # R01: "hanya nama perumahan tanpa nomor rumah" -- a real returned
        # package. Previously SIAP_DIPROSES.
        result = gate(JALAN="Perum Griya Asri")
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertIn(MISSING_HOUSE_LOCATOR, codes(result))

    def test_a_street_with_no_door_is_flagged(self) -> None:
        self.assertIn(MISSING_HOUSE_LOCATOR, codes(gate(JALAN="Jalan Braga")))

    def test_it_is_medium_and_asks(self) -> None:
        issue = next(
            i for i in gate(JALAN="Jalan Braga").issues
            if i.reason_code == MISSING_HOUSE_LOCATOR
        )
        self.assertEqual(issue.severity, "medium")
        self.assertTrue(issue.clarification_question.endswith("?"))
        self.assertEqual(issue.affected_fields, ("NOMOR",))
        self.assertNotIn("NOMOR", ADMINISTRATIVE_FIELDS)

    def test_any_one_house_locator_is_enough(self) -> None:
        for field, value in (
            ("NOMOR", "No. 5"),
            ("RT", "03"),
            ("RW", "05"),
            ("DETAIL_LOKASI", "Blok C2"),
        ):
            with self.subTest(field=field):
                self.assertNotIn(
                    MISSING_HOUSE_LOCATOR,
                    codes(gate(JALAN="Jalan Braga", **{field: value})),
                )
        self.assertEqual(set(HOUSE_LOCATOR_FIELDS), {"NOMOR", "RT", "RW", "DETAIL_LOKASI"})

    def test_whitespace_does_not_count_as_a_locator(self) -> None:
        for value in ("", "   ", "\t"):
            with self.subTest(value=repr(value)):
                self.assertIn(
                    MISSING_HOUSE_LOCATOR, codes(gate(JALAN="Jalan Braga", NOMOR=value))
                )


class MessageAccuracyTest(unittest.TestCase):
    """The message must not describe input the address does not contain."""

    def _house_message(self, **submitted: str) -> str:
        issue = next(
            i for i in gate(**submitted).issues if i.reason_code == MISSING_HOUSE_LOCATOR
        )
        return issue.message

    def test_it_mentions_the_street_only_when_one_was_named(self) -> None:
        with_street = self._house_message(JALAN="Jalan Braga")
        self.assertIn("menyebut jalan atau kampung", with_street)

    def test_it_does_not_claim_a_street_that_is_absent(self) -> None:
        # Previously both cases shared one sentence, so an address naming no
        # street was told it named one.
        without_street = self._house_message()
        self.assertNotIn("menyebut jalan atau kampung", without_street)
        self.assertNotIn("sepanjang jalan tersebut", without_street)

    def test_both_wordings_still_name_what_is_missing(self) -> None:
        for message in (self._house_message(JALAN="Jalan Braga"), self._house_message()):
            with self.subTest(message=message[:40]):
                self.assertIn("nomor rumah", message)
                self.assertIn("RT/RW", message)
                self.assertIn("blok", message)


class BothRulesTogetherTest(unittest.TestCase):
    def test_an_address_missing_both_reports_both(self) -> None:
        # One line per missing part is what the target user asked for, rather
        # than a single vague "incomplete".
        reported = codes(gate())
        self.assertIn(MISSING_STREET_LOCATOR, reported)
        self.assertIn(MISSING_HOUSE_LOCATOR, reported)

    def test_neither_rule_can_reach_tidak_valid(self) -> None:
        result = gate()
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertTrue(all(issue.severity == "medium" for issue in result.issues))

    def test_both_stay_silent_without_component_values(self) -> None:
        # A caller that supplied no components has not said the fields are
        # absent, only that it did not say. Flagging there would flag everyone.
        result = evaluate_quality_gate(valid_chain())
        self.assertEqual(result.status, SIAP_DIPROSES)
        self.assertEqual(result.issues, ())


if __name__ == "__main__":
    unittest.main()

"""Tests for three false-rejection bugs found by hand-testing the UI (DEC-012).

All three shared a shape: a **correct** address was declared `TIDAK_VALID`, or a
complete one was flagged incomplete. That is the most damaging output this
system has, so each fix is pinned from both sides -- the false rejection stops,
and the true rejection it resembles still happens.

1. An address outside Jawa Barat was declared invalid, because a village named
   Menteng exists in Bogor. The reference holds no rows for Jakarta at all, so
   its verdict there is not evidence.
2. Nine designator spellings the extractor recognises -- `kcmtn`, `kta`, `kc`
   and friends -- were not canonicalised by the normalizer, so the validator
   compared `Kcmtn Sumur Bandung` with `SUMUR BANDUNG` and reported a conflict.
3. `Perum Griya Asri Blok C2` was flagged `MISSING_HOUSE_LOCATOR` even though it
   names its block.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.address_normalizer import normalize_address  # noqa: E402
from alamatin.administrative_validator import (  # noqa: E402
    ADMINISTRATIVE_CONFLICT as VALIDATOR_CONFLICT,
    VALID_CHAIN,
    AdministrativeValidationResult,
    ValidationCandidate,
    within_reference_coverage,
)
from alamatin.quality_gate import (  # noqa: E402
    ADMINISTRATIVE_CONFLICT,
    MISSING_HOUSE_LOCATOR,
    OUTSIDE_REFERENCE_COVERAGE,
    PERLU_KONFIRMASI,
    SIAP_DIPROSES,
    TIDAK_VALID,
    evaluate_quality_gate,
)
from alamatin.regex_baseline import (  # noqa: E402
    KECAMATAN_DESIGNATORS,
    KOTA_KABUPATEN_DESIGNATORS,
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


def conflict() -> AdministrativeValidationResult:
    return AdministrativeValidationResult(
        status="invalid",
        reason_codes=(VALIDATOR_CONFLICT,),
        affected_fields=("KECAMATAN",),
        missing_fields=(),
        candidates=(BRAGA,),
        reference_version="jabar-reference-v1",
    )


def valid() -> AdministrativeValidationResult:
    return AdministrativeValidationResult(
        status="valid",
        reason_codes=(VALID_CHAIN,),
        affected_fields=(),
        missing_fields=(),
        candidates=(BRAGA,),
        reference_version="jabar-reference-v1",
    )


COMPLETE = {"JALAN": "Jalan Braga", "NOMOR": "No. 5"}


class OutsideCoverageTest(unittest.TestCase):
    """Bug 1: the reference cannot contradict what it has no rows for."""

    def test_a_province_outside_coverage_downgrades_a_conflict(self) -> None:
        result = evaluate_quality_gate(
            conflict(), submitted={**COMPLETE, "PROVINSI": "DKI Jakarta"}
        )
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertEqual(
            [issue.reason_code for issue in result.issues],
            [OUTSIDE_REFERENCE_COVERAGE],
        )

    def test_it_does_not_claim_the_address_is_wrong(self) -> None:
        # limitations.md: a coverage gap must never be presented as proof the
        # address is wrong. This was the worst violation of it, at high severity.
        issue = evaluate_quality_gate(
            conflict(), submitted={**COMPLETE, "PROVINSI": "DKI Jakarta"}
        ).issues[0]
        self.assertEqual(issue.severity, "medium")
        self.assertIn("bukan bahwa alamat salah", issue.message)
        self.assertIn("Dki Jakarta", issue.message)

    def test_a_jawa_barat_conflict_is_still_a_conflict(self) -> None:
        # The other half. Downgrading everything would make the gate useless.
        result = evaluate_quality_gate(
            conflict(), submitted={**COMPLETE, "PROVINSI": "Jawa Barat"}
        )
        self.assertEqual(result.status, TIDAK_VALID)
        self.assertIn(
            ADMINISTRATIVE_CONFLICT, [issue.reason_code for issue in result.issues]
        )

    def test_an_absent_province_is_treated_as_inside_coverage(self) -> None:
        # Silence is not a claim to be elsewhere, and most Jawa Barat addresses
        # omit the province entirely.
        result = evaluate_quality_gate(conflict(), submitted=COMPLETE)
        self.assertEqual(result.status, TIDAK_VALID)

    def test_coverage_recognises_the_provinces_it_should(self) -> None:
        for inside in ("Jawa Barat", "JAWA BARAT", "Jabar", "Provinsi Jawa Barat"):
            with self.subTest(value=inside):
                self.assertTrue(within_reference_coverage(inside))
        for outside in ("DKI Jakarta", "Jawa Tengah", "Banten", "Bali"):
            with self.subTest(value=outside):
                self.assertFalse(within_reference_coverage(outside))
        for empty in (None, "", "   "):
            with self.subTest(value=repr(empty)):
                self.assertTrue(within_reference_coverage(empty))


class DesignatorCanonicalisationTest(unittest.TestCase):
    """Bug 2: every spelling the extractor knows must canonicalise."""

    def test_every_kecamatan_spelling_canonicalises(self) -> None:
        for designator in KECAMATAN_DESIGNATORS:
            with self.subTest(designator=designator):
                value = normalize_address(
                    {"KECAMATAN": f"{designator} Sumur Bandung"}
                ).values()["KECAMATAN"]
                self.assertEqual(value, "Kecamatan Sumur Bandung")

    def test_every_kota_kabupaten_spelling_canonicalises(self) -> None:
        for designator in KOTA_KABUPATEN_DESIGNATORS:
            with self.subTest(designator=designator):
                value = normalize_address(
                    {"KOTA_KABUPATEN": f"{designator} Bandung"}
                ).values()["KOTA_KABUPATEN"]
                # Kota and Kabupaten are different kinds and must not merge.
                expected = (
                    "Kabupaten Bandung"
                    if designator.startswith(("kab", "kb"))
                    else "Kota Bandung"
                )
                self.assertEqual(value, expected)

    def test_kabupaten_is_not_rewritten_to_kota(self) -> None:
        # The distinction the fix must preserve: Kabupaten Bandung is a
        # different place from Kota Bandung, and conflating them would turn a
        # true rejection into a false pass.
        self.assertEqual(
            normalize_address({"KOTA_KABUPATEN": "kab Bandung"}).values()[
                "KOTA_KABUPATEN"
            ],
            "Kabupaten Bandung",
        )


class BlockLocatorTest(unittest.TestCase):
    """Bug 3: a named block pins a door wherever the label puts it."""

    def test_a_block_inside_the_street_value_satisfies_the_rule(self) -> None:
        result = evaluate_quality_gate(
            valid(), submitted={"JALAN": "Perum Griya Asri Blok C2"}
        )
        self.assertEqual(result.status, SIAP_DIPROSES)

    def test_other_unit_words_count_too(self) -> None:
        for value in ("Jalan Braga Kav 14", "Jalan Braga Blk. A1", "Jalan Braga Unit 3"):
            with self.subTest(value=value):
                self.assertEqual(
                    evaluate_quality_gate(valid(), submitted={"JALAN": value}).status,
                    SIAP_DIPROSES,
                )

    def test_a_street_with_no_block_is_still_flagged(self) -> None:
        # Non-vacuous: the pattern must not match any street at all.
        result = evaluate_quality_gate(valid(), submitted={"JALAN": "Jalan Braga"})
        self.assertIn(
            MISSING_HOUSE_LOCATOR, [issue.reason_code for issue in result.issues]
        )

    def test_a_word_merely_containing_blok_does_not_count(self) -> None:
        result = evaluate_quality_gate(valid(), submitted={"JALAN": "Jalan Unblokir"})
        self.assertIn(
            MISSING_HOUSE_LOCATOR, [issue.reason_code for issue in result.issues]
        )

    def test_the_pattern_is_a_real_regex_not_a_control_character(self) -> None:
        # A heredoc once wrote the word-boundary escape as a literal backspace
        # (0x08) into this pattern, which is invisible in an editor and silently
        # matched nothing. This asserts the boundary works.
        from alamatin.quality_gate import _BLOCK_PATTERN

        self.assertNotIn("\x08", _BLOCK_PATTERN.pattern)
        self.assertTrue(_BLOCK_PATTERN.search("Perum Griya Asri Blok C2"))
        self.assertFalse(_BLOCK_PATTERN.search("Jalan Unblokir"))


if __name__ == "__main__":
    unittest.main()

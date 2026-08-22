from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.address_normalizer import ProvenancedValue, ValueSource  # noqa: E402
from alamatin.administrative_validator import (  # noqa: E402
    ADMINISTRATIVE_CONFLICT,
    AMBIGUOUS_CANDIDATES,
    MISSING_FIELDS,
    REFERENCE_COVERAGE_GAP,
    VALID_CHAIN,
    AdministrativeValidationError,
    AdministrativeValidator,
)
from alamatin.reference_hierarchy import (  # noqa: E402
    ReferenceHierarchy,
    ReferenceRow,
    SourceReference,
)


def reference_row(
    *,
    village_code: str = "32.73.05.1002",
    village_name: str = "BRAGA",
    district_code: str = "32.73.05",
    district_name: str = "SUMUR BANDUNG",
    city_code: str = "32.73",
    city_name: str = "KOTA BANDUNG",
    province_code: str = "32",
    province_name: str = "JAWA BARAT",
    postal_codes: tuple[str, ...] = ("40111",),
    village_aliases: tuple[str, ...] = (),
) -> ReferenceRow:
    return ReferenceRow(
        province_code=province_code,
        province_name=province_name,
        city_code=city_code,
        city_name=city_name,
        district_code=district_code,
        district_name=district_name,
        village_code=village_code,
        village_name=village_name,
        village_aliases=village_aliases,
        postal_codes=postal_codes,
        sources=(SourceReference("synthetic_reference", "fixture-v1"),),
    )


def complete_components(**overrides):
    values = {
        "KELURAHAN": "Kelurahan Braga",
        "KECAMATAN": "Kecamatan Sumur Bandung",
        "KOTA_KABUPATEN": "Kota Bandung",
        "PROVINSI": "Provinsi Jawa Barat",
        "KODEPOS": "40111",
    }
    values.update(overrides)
    return values


class AdministrativeValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = ReferenceHierarchy(
            [reference_row(village_aliases=("BRAGA KULON",))]
        )
        self.validator = AdministrativeValidator(
            self.reference,
            reference_version="synthetic-fixture-v1",
        )

    def test_complete_valid_chain_returns_exact_match(self):
        result = self.validator.validate(complete_components())
        self.assertEqual(result.status, "valid")
        self.assertEqual(result.reason_codes, (VALID_CHAIN,))
        self.assertEqual(result.match.village_code, "32.73.05.1002")
        self.assertFalse(result.affected_fields)
        self.assertFalse(result.missing_fields)

    def test_normalized_values_with_provenance_are_accepted(self):
        components = {
            field: ProvenancedValue(value, ValueSource.NORMALIZED_BY_DICTIONARY)
            for field, value in complete_components().items()
        }
        self.assertEqual(self.validator.validate(components).status, "valid")

    def test_alias_and_designator_variants_are_valid(self):
        result = self.validator.validate(
            complete_components(
                KELURAHAN="Kel. Braga Kulon",
                KECAMATAN="Kec. Sumur Bandung",
                KOTA_KABUPATEN="Bandung",
                PROVINSI="Jawa Barat",
            )
        )
        self.assertEqual(result.status, "valid")

    def test_city_type_mismatch_is_a_confirmed_conflict(self):
        result = self.validator.validate(
            complete_components(KOTA_KABUPATEN="Kabupaten Bandung")
        )
        self.assertEqual(result.status, "invalid")
        self.assertTrue(result.is_invalid)
        self.assertEqual(result.reason_codes, (ADMINISTRATIVE_CONFLICT,))
        self.assertEqual(result.affected_fields, ("KOTA_KABUPATEN",))
        self.assertEqual(len(result.candidates), 1)

    def test_postcode_conflict_has_affected_field_and_candidate(self):
        result = self.validator.validate(complete_components(KODEPOS="40112"))
        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.affected_fields, ("KODEPOS",))
        self.assertEqual(result.candidates[0].postal_codes, ("40111",))

    def test_unknown_village_is_coverage_gap_not_invalid(self):
        result = self.validator.validate(
            complete_components(KELURAHAN="Kelurahan Tidak Ada di Fixture")
        )
        self.assertEqual(result.status, "not_found")
        self.assertFalse(result.is_invalid)
        self.assertEqual(result.reason_codes, (REFERENCE_COVERAGE_GAP,))
        self.assertFalse(result.affected_fields)
        self.assertFalse(result.candidates)

    def test_missing_fields_are_reported_without_inventing_values(self):
        result = self.validator.validate({"KELURAHAN": "Braga"})
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.reason_codes, (MISSING_FIELDS,))
        self.assertEqual(
            result.missing_fields,
            ("KECAMATAN", "KOTA_KABUPATEN", "PROVINSI", "KODEPOS"),
        )
        self.assertIsNone(result.match)
        self.assertEqual(len(result.candidates), 1)

    def test_missing_village_is_incomplete_not_coverage_gap(self):
        result = self.validator.validate({"KECAMATAN": "Sumur Bandung"})
        self.assertEqual(result.status, "incomplete")
        self.assertIn("KELURAHAN", result.missing_fields)
        self.assertEqual(result.reason_codes, (MISSING_FIELDS,))

    def test_blank_values_count_as_missing(self):
        result = self.validator.validate(complete_components(KODEPOS="   "))
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.missing_fields, ("KODEPOS",))

    def test_non_administrative_canonical_fields_are_ignored(self):
        result = self.validator.validate(
            complete_components(JALAN="Jalan Asia Afrika", NOMOR="No. 7")
        )
        self.assertEqual(result.status, "valid")

    def test_unknown_field_is_rejected(self):
        with self.assertRaisesRegex(AdministrativeValidationError, "unknown address fields"):
            self.validator.validate({"NEGARA": "Indonesia"})

    def test_result_is_deterministic_and_json_serializable(self):
        first = self.validator.validate(complete_components()).to_response_dict()
        reversed_input = dict(reversed(list(complete_components().items())))
        second = self.validator.validate(reversed_input).to_response_dict()
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first)), first)
        self.assertEqual(first["reference_version"], "synthetic-fixture-v1")


class AmbiguityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = ReferenceHierarchy(
            [
                reference_row(
                    village_code="32.73.09.1001",
                    village_name="SUKAMAJU",
                    district_code="32.73.09",
                    district_name="CIBEUNYING KIDUL",
                    postal_codes=("40122",),
                ),
                reference_row(
                    village_code="32.73.05.1002",
                    village_name="SUKAMAJU",
                    district_code="32.73.05",
                    district_name="SUMUR BANDUNG",
                    postal_codes=("40111",),
                ),
            ]
        )
        self.validator = AdministrativeValidator(self.reference)

    def test_ambiguous_name_returns_all_sorted_candidates_without_match(self):
        result = self.validator.validate({"KELURAHAN": "Sukamaju"})
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.reason_codes, (AMBIGUOUS_CANDIDATES,))
        self.assertIsNone(result.match)
        self.assertEqual(
            [candidate.village_code for candidate in result.candidates],
            ["32.73.05.1002", "32.73.09.1001"],
        )

    def test_parent_context_narrows_candidate_but_missing_chain_stays_incomplete(self):
        result = self.validator.validate(
            {"KELURAHAN": "Sukamaju", "KECAMATAN": "Cibeunying Kidul"}
        )
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(result.candidates[0].village_code, "32.73.09.1001")

    def test_complete_context_resolves_ambiguity(self):
        result = self.validator.validate(
            complete_components(
                KELURAHAN="Sukamaju",
                KECAMATAN="Cibeunying Kidul",
                KODEPOS="40122",
            )
        )
        self.assertEqual(result.status, "valid")
        self.assertEqual(result.match.village_code, "32.73.09.1001")

    def test_cross_candidate_constraints_report_both_affected_fields(self):
        result = self.validator.validate(
            {
                "KELURAHAN": "Sukamaju",
                "KECAMATAN": "Sumur Bandung",
                "KODEPOS": "40122",
            }
        )
        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.affected_fields, ("KECAMATAN", "KODEPOS"))
        self.assertEqual(len(result.candidates), 2)


if __name__ == "__main__":
    unittest.main()

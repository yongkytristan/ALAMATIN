import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.address_normalizer import (
    ALLOWED_SOURCES,
    NormalizationError,
    ProvenancedValue,
    ValueSource,
    confirm_correction,
    normalize_address,
    propose_correction,
)


class DeterministicNormalizationTests(unittest.TestCase):
    def test_normalizes_abbreviations_capitalization_rt_rw_and_number(self):
        result = normalize_address(
            {
                "JALAN": "  jl. asia   afrika ",
                "NOMOR": "nomor 7A",
                "RT": "rt. 1",
                "RW": "RW 02",
                "KELURAHAN": "kel. braga",
                "KECAMATAN": "kec sumur bandung",
                "KOTA_KABUPATEN": "kota bandung",
                "PROVINSI": "prov. jawa barat",
            }
        )
        self.assertEqual(
            result.values(),
            {
                "JALAN": "Jalan Asia Afrika",
                "NOMOR": "No. 7A",
                "RT": "RT 001",
                "RW": "RW 002",
                "KELURAHAN": "Kelurahan Braga",
                "KECAMATAN": "Kecamatan Sumur Bandung",
                "KOTA_KABUPATEN": "Kota Bandung",
                "PROVINSI": "Provinsi Jawa Barat",
            },
        )

    def test_village_and_road_designators_keep_their_meaning(self):
        result = normalize_address({"JALAN": "gg melati", "KELURAHAN": "ds sukajadi"})
        self.assertEqual(result.values()["JALAN"], "Gang Melati")
        self.assertEqual(result.values()["KELURAHAN"], "Desa Sukajadi")

    def test_postcode_spacing_and_unicode_whitespace_are_normalized(self):
        result = normalize_address({"KODEPOS": " 40\u00a0111 "})
        self.assertEqual(result.values()["KODEPOS"], "40111")
        self.assertEqual(len(result.changes), 2)

    def test_roman_numeral_and_connectors_have_stable_capitalization(self):
        result = normalize_address({"JALAN": "jalan veteran ii dan sekitarnya"})
        self.assertEqual(result.values()["JALAN"], "Jalan Veteran II dan Sekitarnya")

    def test_unknown_or_ambiguous_format_is_preserved(self):
        values = {"RT": "RT A", "RW": "RW 1/2", "KODEPOS": "4011A", "NOMOR": "7-9"}
        result = normalize_address(values)
        self.assertEqual(result.values(), values)
        self.assertFalse(result.changes)

    def test_empty_component_is_only_trimmed_and_not_invented(self):
        result = normalize_address({"JALAN": "   "})
        self.assertEqual(result.values(), {"JALAN": ""})
        self.assertEqual(result.changes[0].before.value, "   ")
        self.assertEqual(result.changes[0].after.value, "")

    def test_normalizer_is_idempotent_for_all_main_formats(self):
        first = normalize_address(
            {
                "JALAN": "jl merdeka",
                "NOMOR": "no 10",
                "RT": "1",
                "RW": "2",
                "KELURAHAN": "kel sukajadi",
                "KECAMATAN": "kec coblong",
                "KOTA_KABUPATEN": "kab bandung",
                "PROVINSI": "jawa barat",
                "KODEPOS": "40 111",
                "DETAIL_LOKASI": "depan pasar baru",
            },
            default_source=ValueSource.EXTRACTED_BY_MODEL,
        )
        second = normalize_address(
            {
                component.field: component.value
                for component in first.components
            }
        )
        self.assertEqual(second.values(), first.values())
        self.assertFalse(second.changes)

    def test_component_order_is_canonical_not_mapping_insertion_order(self):
        result = normalize_address({"PROVINSI": "Jawa Barat", "JALAN": "Jalan Mawar"})
        self.assertEqual([item.field for item in result.components], ["JALAN", "PROVINSI"])


class ProvenanceAndConfirmationTests(unittest.TestCase):
    def test_allowed_sources_match_issue_contract_exactly(self):
        self.assertEqual(
            set(ALLOWED_SOURCES),
            {
                "user_input",
                "rule_extracted",
                "extracted_by_model",
                "normalized_by_dictionary",
                "inferred_from_hierarchy",
                "returned_by_geocoder",
                "confirmed_by_user",
            },
        )

    def test_every_applied_change_keeps_before_after_source_and_rule(self):
        original = ProvenancedValue("jl. merdeka", ValueSource.EXTRACTED_BY_MODEL)
        result = normalize_address({"JALAN": original})
        self.assertGreaterEqual(len(result.changes), 2)
        for change in result.changes:
            self.assertTrue(change.before.value or change.rule_id == "unicode_whitespace_v1")
            self.assertTrue(change.after.value)
            self.assertIn(change.before.source.value, ALLOWED_SOURCES)
            self.assertIn(change.after.source.value, ALLOWED_SOURCES)
            self.assertTrue(change.rule_id)
            self.assertEqual(change.decision, "deterministic")
            self.assertTrue(change.applied)
            self.assertFalse(change.after.confirmed)

    def test_json_response_contains_complete_audit_values(self):
        result = normalize_address({"RT": "rt 4"})
        payload = json.loads(json.dumps(result.to_response_dict()))
        self.assertEqual(payload["components"][0]["value"], "RT 004")
        audit = payload["changes"][0]
        self.assertEqual(audit["before"]["value"], "rt 4")
        self.assertEqual(audit["after"]["value"], "RT 004")
        self.assertEqual(audit["after"]["source"], "rule_extracted")

    def test_unchanged_component_retains_original_source(self):
        original = ProvenancedValue("40111", ValueSource.EXTRACTED_BY_MODEL)
        result = normalize_address({"KODEPOS": original})
        self.assertEqual(result.components[0].value, original)
        self.assertFalse(result.changes)

    def test_semantic_correction_is_only_a_non_applied_suggestion(self):
        current = ProvenancedValue("Bandun", ValueSource.EXTRACTED_BY_MODEL)
        suggestion = propose_correction(
            "KOTA_KABUPATEN",
            current,
            "Bandung",
            evidence_source=ValueSource.INFERRED_FROM_HIERARCHY,
            rule_id="exact_parent_chain_v1",
        )
        self.assertEqual(suggestion.decision, "requires_confirmation")
        self.assertFalse(suggestion.applied)
        self.assertFalse(suggestion.after.confirmed)
        self.assertEqual(suggestion.before.value, "Bandun")
        self.assertEqual(suggestion.after.value, "Bandung")

    def test_important_correction_cannot_be_confirmed_without_user_action(self):
        suggestion = propose_correction(
            "KODEPOS",
            ProvenancedValue("40112", ValueSource.USER_INPUT),
            "40111",
            evidence_source=ValueSource.RETURNED_BY_GEOCODER,
            rule_id="geocoder_postcode_conflict_v1",
        )
        with self.assertRaisesRegex(NormalizationError, "explicit user confirmation"):
            confirm_correction(suggestion, user_confirmed=False)

    def test_explicit_confirmation_changes_source_and_audit_status(self):
        suggestion = propose_correction(
            "KODEPOS",
            ProvenancedValue("40112", ValueSource.USER_INPUT),
            "40111",
            evidence_source=ValueSource.INFERRED_FROM_HIERARCHY,
            rule_id="hierarchy_postcode_v1",
        )
        confirmed = confirm_correction(suggestion, user_confirmed=True)
        self.assertTrue(confirmed.applied)
        self.assertEqual(confirmed.decision, "confirmed")
        self.assertTrue(confirmed.after.confirmed)
        self.assertEqual(confirmed.after.source, ValueSource.CONFIRMED_BY_USER)

    def test_confirmed_flag_and_source_cannot_be_forged(self):
        invalid_cases = (
            ("Bandung", ValueSource.INFERRED_FROM_HIERARCHY, True),
            ("Bandung", ValueSource.CONFIRMED_BY_USER, False),
        )
        for value, source, confirmed in invalid_cases:
            with self.subTest(source=source):
                with self.assertRaises(NormalizationError):
                    ProvenancedValue(value, source, confirmed)

    def test_invalid_sources_and_fields_are_rejected(self):
        with self.assertRaises(NormalizationError):
            normalize_address({"EMAIL": "hidden"})
        with self.assertRaises(NormalizationError):
            normalize_address({"JALAN": "Jalan Mawar"}, default_source="unknown")
        with self.assertRaises(NormalizationError):
            propose_correction(
                "JALAN",
                ProvenancedValue("Mawar", ValueSource.USER_INPUT),
                "Melati",
                evidence_source=ValueSource.USER_INPUT,
                rule_id="invalid_evidence",
            )


if __name__ == "__main__":
    unittest.main()

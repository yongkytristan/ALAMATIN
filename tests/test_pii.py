import json
import unittest

from alamatin.pii import (
    NAME_REDACTED,
    PHONE_REDACTED,
    PII_DETECTED,
    process_pii,
    redact_for_logging,
)


# Deliberately assembled synthetic values: no real person's contact data is used.
MOBILE_LOCAL = "".join(("08", "12", "0000", "0000"))
MOBILE_LOCAL_SHORT = "".join(("08", "13", "000", "0000"))
MOBILE_INTL = "".join(("+62", " 812", "-0000", "-0000"))
MOBILE_INTL_NO_PLUS = "".join(("62", "812", "0000", "0000"))
LANDLINE = "".join(("(021)", " 500", " 0000"))


class PIIPhoneDetectionTests(unittest.TestCase):
    def test_indonesian_mobile_formats_are_detected(self):
        cases = (
            MOBILE_LOCAL,
            MOBILE_LOCAL_SHORT,
            MOBILE_INTL,
            MOBILE_INTL_NO_PLUS,
            MOBILE_LOCAL[:4] + " " + MOBILE_LOCAL[4:8] + " " + MOBILE_LOCAL[8:],
        )
        for phone in cases:
            with self.subTest(phone_format=phone[:4]):
                result = process_pii(f"Jl. Merdeka 10, HP: {phone}")
                self.assertEqual([entity.type for entity in result.entities], ["PHONE"])
                self.assertNotIn(phone, result.redacted_text)
                self.assertNotIn(phone, result.address_text)
                self.assertIn(PHONE_REDACTED, result.redacted_text)
                self.assertEqual(result.reason_codes, (PII_DETECTED,))

    def test_labelled_landline_is_detected(self):
        result = process_pii(f"Jalan Asia Afrika 8, Tel. {LANDLINE}")
        self.assertEqual([entity.type for entity in result.entities], ["PHONE"])
        self.assertNotIn(LANDLINE, result.redacted_text)

    def test_unlabelled_landline_is_not_guessed(self):
        result = process_pii(f"Jalan Asia Afrika No. {LANDLINE}")
        self.assertFalse(result.entities)
        self.assertEqual(result.address_text, f"Jalan Asia Afrika No. {LANDLINE}")

    def test_multiple_phones_are_all_redacted(self):
        second = "".join(("08", "57", "0000", "0000"))
        result = process_pii(f"WA {MOBILE_LOCAL}; cadangan {second}")
        self.assertEqual(len(result.entities), 2)
        self.assertNotIn(MOBILE_LOCAL, result.redacted_text)
        self.assertNotIn(second, result.redacted_text)

    def test_common_address_numbers_are_not_false_positives(self):
        cases = (
            "Jl. Melati No. 12, Bandung 40111",
            "RT 001/RW 002 Blok 08",
            "Kode wilayah 32.73.05.1001",
            "Patokan KM 12 tahun 2026",
            "Koordinat -6.9175, 107.6191",
        )
        for address in cases:
            with self.subTest(address=address):
                result = process_pii(address)
                self.assertFalse(result.entities)
                self.assertEqual(result.address_text, address)

    def test_mobile_shaped_identifiers_with_explicit_labels_are_ignored(self):
        for label in ("NPSN", "order", "resi", "invoice", "rekening", "kode"):
            text = f"{label}: {MOBILE_LOCAL}"
            with self.subTest(label=label):
                self.assertFalse(process_pii(text).entities)

    def test_too_short_or_too_long_mobile_is_ignored(self):
        cases = ("0812000", "08120000000000")
        for value in cases:
            with self.subTest(length=len(value)):
                self.assertFalse(process_pii(value).entities)


class PIIRecipientAndSafetyTests(unittest.TestCase):
    def test_explicit_recipient_is_removed_before_downstream(self):
        result = process_pii("Penerima: Ibu Siti Aminah, Jl. Mawar No. 7")
        self.assertEqual(result.address_text, "Jl. Mawar No. 7")
        self.assertEqual(result.entities[0].type, "RECIPIENT_NAME")
        self.assertIn(NAME_REDACTED, result.redacted_text)
        self.assertEqual(result.reason_codes, (PII_DETECTED,))

    def test_recipient_before_address_without_comma_is_detected(self):
        result = process_pii("Nama Penerima: Budi Santoso Jalan Merdeka 5")
        self.assertEqual(result.address_text, "Jalan Merdeka 5")
        self.assertEqual(result.entities[0].type, "RECIPIENT_NAME")

    def test_unmarked_name_is_preserved(self):
        text = "Toko Siti Jaya, Jalan Melati 4"
        result = process_pii(text)
        self.assertFalse(result.entities)
        self.assertEqual(result.address_text, text)

    def test_malformed_recipient_field_is_preserved(self):
        text = "Penerima: 12345, Jalan Mawar 7"
        result = process_pii(text)
        self.assertFalse(result.entities)
        self.assertEqual(result.address_text, text)

    def test_name_detector_failure_does_not_damage_address_or_phone_redaction(self):
        def failing_detector(_text):
            raise RuntimeError("synthetic failure")

        text = f"Penerima: Budi, Jalan Mawar 7, HP {MOBILE_LOCAL}"
        result = process_pii(text, _name_detector=failing_detector)
        self.assertIn("Penerima: Budi, Jalan Mawar 7", result.address_text)
        self.assertNotIn(MOBILE_LOCAL, result.address_text)
        self.assertNotIn(MOBILE_LOCAL, result.redacted_text)
        self.assertEqual(result.warnings, ("RECIPIENT_NAME_EXTRACTION_FAILED",))

    def test_response_repr_and_json_never_contain_detected_phone(self):
        result = process_pii(f"Penerima: Budi, Jl. Mawar 7, WA {MOBILE_LOCAL}")
        serializations = (
            result.redacted_text,
            result.address_text,
            repr(result),
            json.dumps(result.to_response_dict()),
            redact_for_logging(f"request={MOBILE_LOCAL}"),
        )
        for safe_output in serializations:
            self.assertNotIn(MOBILE_LOCAL, safe_output)

    def test_response_entities_expose_metadata_not_raw_values(self):
        result = process_pii(f"HP: {MOBILE_LOCAL}")
        entity = result.to_response_dict()["entities"][0]
        self.assertEqual(entity["redacted_value"], PHONE_REDACTED)
        self.assertNotIn("value", entity)

    def test_empty_and_whitespace_input_are_unchanged(self):
        for text in ("", "   ", "\n\t"):
            with self.subTest(repr=repr(text)):
                result = process_pii(text)
                self.assertEqual(result.address_text, text.strip())
                self.assertFalse(result.entities)
                self.assertFalse(result.reason_codes)

    def test_non_string_input_is_rejected_without_coercion(self):
        with self.assertRaises(TypeError):
            process_pii(None)


if __name__ == "__main__":
    unittest.main()

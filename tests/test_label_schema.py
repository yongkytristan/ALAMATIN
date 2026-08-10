from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.label_schema import (  # noqa: E402
    BIO_LABELS,
    ENTITY_TYPES,
    ID_TO_LABEL,
    LABEL_TO_ID,
    SCHEMA_VERSION,
    validate_bio_sequence,
)


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "ner_gold_examples.json"


class LabelSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_entity_types_are_exact_and_stable(self) -> None:
        self.assertEqual(
            ENTITY_TYPES,
            (
                "JALAN",
                "NOMOR",
                "RT",
                "RW",
                "KELURAHAN",
                "KECAMATAN",
                "KOTA_KABUPATEN",
                "PROVINSI",
                "KODEPOS",
                "DETAIL_LOKASI",
            ),
        )

    def test_bio_label_count_and_mapping(self) -> None:
        self.assertEqual(len(BIO_LABELS), 21)
        self.assertEqual(BIO_LABELS[0], "O")
        self.assertEqual(len(LABEL_TO_ID), len(ID_TO_LABEL))
        for index, label in enumerate(BIO_LABELS):
            self.assertEqual(LABEL_TO_ID[label], index)
            self.assertEqual(ID_TO_LABEL[index], label)

    def test_fixture_uses_canonical_version_and_label_order(self) -> None:
        self.assertEqual(self.fixture["schema_version"], SCHEMA_VERSION)
        self.assertEqual(tuple(self.fixture["label_order"]), BIO_LABELS)

    def test_fixture_has_twenty_unique_review_examples(self) -> None:
        examples = self.fixture["examples"]
        self.assertEqual(len(examples), 20)
        self.assertEqual(len({example["id"] for example in examples}), 20)

    def test_gold_examples_have_valid_bio_sequences(self) -> None:
        for example in self.fixture["examples"]:
            with self.subTest(example=example["id"]):
                if example["status"] == "needs_adjudication":
                    self.assertIsNone(example["labels"])
                    self.assertGreaterEqual(len(example["candidate_labels"]), 2)
                    continue
                self.assertEqual(example["status"], "gold")
                self.assertEqual(len(example["tokens"]), len(example["labels"]))
                valid, reason = validate_bio_sequence(example["labels"])
                self.assertTrue(valid, reason)

    def test_fixture_covers_required_review_categories(self) -> None:
        categories = {
            category
            for example in self.fixture["examples"]
            for category in example["categories"]
        }
        self.assertTrue(
            {
                "positive",
                "negative",
                "abbreviation",
                "typo",
                "ambiguous",
                "pii",
                "conflict",
            }.issubset(categories)
        )

    def test_validator_rejects_unknown_and_orphan_i_tags(self) -> None:
        self.assertEqual(validate_bio_sequence(["B-JALAN", "I-JALAN"]), (True, None))
        self.assertFalse(validate_bio_sequence(["I-JALAN"])[0])
        self.assertFalse(validate_bio_sequence(["B-JALAN", "I-NOMOR"])[0])
        self.assertFalse(validate_bio_sequence(["B-UNKNOWN"])[0])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class PostalAdjudicatedArtifactsTest(unittest.TestCase):
    def test_sections_map_exactly_to_final_lookup_and_exceptions(self) -> None:
        section_one = read_csv(
            ROOT / "data" / "processed" / "jabar-postal-consensus-accepted.csv"
        )
        section_two = read_csv(
            ROOT
            / "data"
            / "interim"
            / "postal-review"
            / "jabar-postal-corroborated-review.csv"
        )
        section_three = read_csv(
            ROOT
            / "data"
            / "interim"
            / "postal-review"
            / "jabar-postal-unresolved-review.csv"
        )
        final = read_csv(ROOT / "data" / "processed" / "jabar-reference-v1.csv")
        exceptions = read_csv(
            ROOT / "data" / "processed" / "jabar-reference-v1-exceptions.csv"
        )
        lookup = json.loads(
            (ROOT / "data" / "processed" / "jabar-reference-v1-verified.json")
            .read_text(encoding="utf-8")
        )["rows"]

        promoted_three = [
            row
            for row in section_three
            if row["review_decision"] in {"accept_suggested", "accept_other"}
        ]
        retained_three = [
            row for row in section_three if row["review_decision"] == "remain_unresolved"
        ]
        expected_usable = {
            row["village_code"] for row in section_one + section_two + promoted_three
        }
        expected_unresolved = {row["village_code"] for row in retained_three}
        actual_usable = {
            row["village_code"]
            for row in final
            if row["operational_status"] == "usable_verified"
        }
        actual_unresolved = {
            row["village_code"]
            for row in final
            if row["operational_status"] == "unresolved_do_not_guess"
        }
        lookup_codes = {row["village"]["code"] for row in lookup}

        self.assertEqual((len(section_one), len(section_two), len(section_three)), (2876, 1974, 1107))
        self.assertEqual((len(promoted_three), len(retained_three)), (1107, 0))
        self.assertEqual(len(expected_usable), 5957)
        self.assertEqual(actual_usable, expected_usable)
        self.assertEqual(lookup_codes, expected_usable)
        self.assertEqual(actual_unresolved, expected_unresolved)
        self.assertEqual({row["village_code"] for row in exceptions}, expected_unresolved)

    def test_every_promoted_review_satisfies_adjudication_contract(self) -> None:
        section_two = read_csv(
            ROOT
            / "data"
            / "interim"
            / "postal-review"
            / "jabar-postal-corroborated-review.csv"
        )
        section_three = read_csv(
            ROOT
            / "data"
            / "interim"
            / "postal-review"
            / "jabar-postal-unresolved-review.csv"
        )
        promoted_three = [
            row
            for row in section_three
            if row["review_decision"] in {"accept_suggested", "accept_other"}
        ]
        self.assertEqual((len(section_two), len(promoted_three)), (1974, 1107))
        for row in [*section_two, *promoted_three]:
            self.assertIn(row["review_decision"], {"accept_suggested", "accept_other"})
            self.assertEqual(row["review_status"], "completed")
            self.assertEqual(row["evidence_scope"], "exact_village")
            self.assertEqual(row["second_review_status"], "approved")
            self.assertNotEqual(row["reviewer"], row["second_reviewer"])
            self.assertRegex(row["reviewed_postal_code"], r"^\d{5}$")
            self.assertEqual(row["postal_code"], row["reviewed_postal_code"])

        retained = [row for row in section_three if row["review_decision"] == "remain_unresolved"]
        self.assertEqual(len(retained), 0)
        for row in retained:
            self.assertEqual(row["review_status"], "blocked")
            self.assertEqual(row["postal_code"], "")
            self.assertEqual(row["reviewed_postal_code"], "")


if __name__ == "__main__":
    unittest.main()

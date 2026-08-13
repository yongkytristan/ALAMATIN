from __future__ import annotations

import sys
import unittest
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stage_final_postal_sections import FinalSectionError, stage_sections  # noqa: E402


def row(code: str, status: str) -> dict[str, str]:
    return {
        "village_code": code,
        "postal_code": "16911",
        "verification_status": status,
        "review_required": "no",
    }


class StageFinalPostalSectionsTest(unittest.TestCase):
    def test_rejects_unexpected_incomplete_fixture_counts(self) -> None:
        with self.assertRaises(FinalSectionError):
            stage_sections(
                [row("32.01.01.1001", "verified_consensus")],
                [row("32.01.01.1002", "verified_adjudicated")],
                {"32.01.01.1002"},
                {"32.01.01.1003"},
            )

    def test_staged_repository_outputs_are_schema_compatible_and_disjoint(self) -> None:
        paths = [
            ROOT / "data" / "final" / "section-1-verified-consensus.csv",
            ROOT / "data" / "final" / "section-2-verified-adjudicated.csv",
            ROOT / "data" / "final" / "section-3-verified-adjudicated.csv",
        ]
        sections: list[list[dict[str, str]]] = []
        headers: list[list[str]] = []
        for path in paths:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                headers.append(list(reader.fieldnames or ()))
                sections.append(list(reader))
        self.assertEqual(headers[0], headers[1])
        self.assertEqual(
            (len(sections[0]), len(sections[1]), len(sections[2])),
            (2876, 1974, 1107),
        )
        one = {item["village_code"] for item in sections[0]}
        two = {item["village_code"] for item in sections[1]}
        three = {item["village_code"] for item in sections[2]}
        self.assertFalse(one & two or one & three or two & three)
        self.assertEqual(len(one | two | three), 5957)

        merged_path = ROOT / "data" / "final" / "jabar-postal-final-merged.csv"
        with merged_path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(list(reader.fieldnames or ()), headers[0])
            merged_rows = list(reader)
        self.assertEqual(len(merged_rows), 5957)
        merged_codes = [item["village_code"] for item in merged_rows]
        self.assertEqual(set(merged_codes), one | two | three)
        self.assertEqual(len(set(merged_codes)), len(merged_codes))
        self.assertEqual(merged_codes, sorted(merged_codes))


if __name__ == "__main__":
    unittest.main()

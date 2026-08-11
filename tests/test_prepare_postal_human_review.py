from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_postal_human_review import (  # noqa: E402
    HumanReviewError,
    prepare_review_rows,
)


def base(code: str, status: str) -> dict[str, str]:
    return {
        "village_code": code,
        "postal_code": "",
        "postal_code_candidate": "16911" if status == "corroborated_candidate" else "",
        "candidate_sources": "source_a;source_b",
        "postal_code_diskominfo": "16912",
        "postal_code_open_data_jabar": "16911",
        "postal_code_kodepos_dev": "16911",
        "verification_status": status,
    }


class PreparePostalHumanReviewTest(unittest.TestCase):
    def test_prepares_candidate_and_both_unresolved_case_types(self) -> None:
        candidate = base("32.01.01.1001", "corroborated_candidate")
        unresolved_a = base("32.01.01.1002", "review_required")
        unresolved_b = base("32.01.01.1003", "review_required")
        disagreement = {
            **unresolved_a,
            "unresolved_pattern": "all_three_different",
            "district_cluster_id": "DIST-A",
            "triplet_cluster_id": "TRIP-A",
            "triplet_cluster_size": "3",
        }
        government = {
            **unresolved_b,
            "postal_code_open_data_jabar": "16912",
            "unresolved_pattern": "government_sources_agree_api_differs",
        }
        observation = {
            "village_code": "32.01.01.1002",
            "postal_code": "16912",
            "evidence_url": "https://example.invalid/official",
        }

        candidates, unresolved, summary = prepare_review_rows(
            [candidate],
            [unresolved_a, unresolved_b],
            [disagreement],
            [government],
            [observation],
        )

        self.assertEqual(candidates[0]["suggested_postal_code"], "16911")
        self.assertEqual(candidates[0]["review_status"], "pending")
        by_code = {row["village_code"]: row for row in unresolved}
        self.assertEqual(by_code["32.01.01.1002"]["existing_pos_match"], "diskominfo")
        self.assertEqual(by_code["32.01.01.1003"]["suggested_postal_code"], "16912")
        self.assertEqual(summary["total_review_rows"], 3)

    def test_rejects_unresolved_row_missing_group(self) -> None:
        unresolved = base("32.01.01.1002", "review_required")
        with self.assertRaises(HumanReviewError):
            prepare_review_rows([], [unresolved], [], [], [])


if __name__ == "__main__":
    unittest.main()

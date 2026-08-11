from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from group_postal_unresolved import (  # noqa: E402
    classify_unresolved,
    group_unresolved,
)


def unresolved_row(
    code: str,
    diskominfo: str,
    open_data_jabar: str,
    api: str,
) -> dict[str, str]:
    return {
        "village_code": code,
        "village_name": f"Village {code}",
        "city_code": "32.01",
        "city_name": "KABUPATEN BOGOR",
        "district_code": "32.01.01",
        "district_name": "CIBINONG",
        "postal_code": "",
        "postal_code_candidate": "",
        "postal_code_diskominfo": diskominfo,
        "postal_code_open_data_jabar": open_data_jabar,
        "postal_code_kodepos_dev": api,
        "verification_status": "review_required",
        "review_required": "yes",
    }


class PostalUnresolvedGroupTest(unittest.TestCase):
    def test_patterns_are_explicit(self) -> None:
        self.assertEqual(
            classify_unresolved(
                unresolved_row("32.01.01.2001", "16911", "16912", "16913")
            ),
            "all_three_different",
        )
        self.assertEqual(
            classify_unresolved(
                unresolved_row("32.01.01.2001", "", "16912", "16913")
            ),
            "diskominfo_missing_api_odj_different",
        )
        self.assertEqual(
            classify_unresolved(
                unresolved_row("32.01.01.2001", "16911", "16911", "16913")
            ),
            "government_sources_agree_api_differs",
        )

    def test_grouping_separates_government_consensus_and_counts_clusters(self) -> None:
        rows = [
            unresolved_row("32.01.01.2001", "16911", "16912", "16913"),
            unresolved_row("32.01.01.2002", "16911", "16912", "16913"),
            unresolved_row("32.01.01.2003", "16911", "", "16913"),
            unresolved_row("32.01.01.2004", "16911", "16911", "16913"),
        ]

        detail, clusters, government, summary = group_unresolved(rows)

        self.assertEqual(len(detail), 3)
        self.assertEqual(len(government), 1)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0]["row_count"], "2")
        same_triplet = [
            row for row in detail if row["unresolved_pattern"] == "all_three_different"
        ]
        self.assertEqual({row["district_cluster_size"] for row in same_triplet}, {"2"})
        self.assertEqual({row["triplet_cluster_size"] for row in same_triplet}, {"2"})
        self.assertEqual(summary["source_disagreement_rows"], 3)
        self.assertEqual(summary["government_consensus_api_conflict_rows"], 1)


if __name__ == "__main__":
    unittest.main()

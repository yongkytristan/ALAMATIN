from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_postal_spotcheck_queue import (  # noqa: E402
    SpotcheckQueueError,
    build_spotcheck_queue,
)


def unresolved_row(
    code: str,
    triplet_id: str,
    triplet_size: int,
    pattern: str = "all_three_different",
) -> dict[str, str]:
    return {
        "village_code": code,
        "village_name": f"Village {code}",
        "province_code": "32",
        "province_name": "JAWA BARAT",
        "city_code": "32.01",
        "city_name": "KAB. BOGOR",
        "district_code": "32.01.01",
        "district_name": "CIBINONG",
        "postal_code_diskominfo": "16911",
        "postal_code_open_data_jabar": "16912",
        "postal_code_kodepos_dev": "16913",
        "unresolved_pattern": pattern,
        "district_cluster_id": "DIST-ONE",
        "district_cluster_size": str(triplet_size),
        "triplet_cluster_id": triplet_id,
        "triplet_cluster_size": str(triplet_size),
    }


def observation(code: str, postal: str) -> dict[str, str]:
    return {
        "source_id": "pos_indonesia_postcode_search",
        "snapshot": "2026-08-11",
        "province_code": "32",
        "province_name": "JAWA BARAT",
        "city_code": "32.01",
        "city_name": "KAB. BOGOR",
        "district_code": "32.01.01",
        "district_name": "CIBINONG",
        "village_code": code,
        "village_name": f"Village {code}",
        "postal_code": postal,
        "evidence_url": "https://kodepos.posindonesia.co.id/CariKodepos",
        "note": "Selected fixture observation.",
    }


class PostalSpotcheckQueueTest(unittest.TestCase):
    def test_selects_one_representative_per_triplet_and_ranks_missing_first(self) -> None:
        rows = [
            unresolved_row("32.01.01.2002", "TRIP-A", 2),
            unresolved_row("32.01.01.2001", "TRIP-A", 2),
            unresolved_row(
                "32.01.01.2003",
                "TRIP-B",
                1,
                "diskominfo_missing_api_odj_different",
            ),
        ]

        queue, summary = build_spotcheck_queue(rows)

        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["triplet_cluster_id"], "TRIP-B")
        self.assertEqual(queue[1]["village_code"], "32.01.01.2001")
        self.assertEqual(summary["represented_unresolved_rows"], 3)
        self.assertEqual(summary["pending_queue_rows"], 2)

    def test_records_official_observation_without_selecting_canonical_value(self) -> None:
        rows = [unresolved_row("32.01.01.2001", "TRIP-A", 1)]

        queue, summary = build_spotcheck_queue(
            rows, [observation("32.01.01.2001", "16911")]
        )

        self.assertEqual(queue[0]["review_status"], "observed_matches_source")
        self.assertEqual(queue[0]["official_postal_code"], "16911")
        self.assertEqual(queue[0]["matched_sources"], "diskominfo")
        self.assertNotIn("postal_code", queue[0])
        self.assertEqual(summary["observed_queue_rows"], 1)

    def test_rejects_duplicate_observations(self) -> None:
        rows = [unresolved_row("32.01.01.2001", "TRIP-A", 1)]
        observations = [
            observation("32.01.01.2001", "16911"),
            observation("32.01.01.2001", "16912"),
        ]

        with self.assertRaises(SpotcheckQueueError):
            build_spotcheck_queue(rows, observations)

    def test_rejects_observation_for_non_representative(self) -> None:
        rows = [
            unresolved_row("32.01.01.2001", "TRIP-A", 2),
            unresolved_row("32.01.01.2002", "TRIP-A", 2),
        ]

        with self.assertRaises(SpotcheckQueueError):
            build_spotcheck_queue(
                rows, [observation("32.01.01.2002", "16911")]
            )


if __name__ == "__main__":
    unittest.main()

"""Tests for the bounded Pos Indonesia candidate observation tool."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_pos_indonesia_candidates",
    ROOT / "scripts" / "fetch_pos_indonesia_candidates.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


HTML = """
<table id="list-data">
  <thead><tr><th>No</th><th>Kodepos</th></tr></thead>
  <tbody>
    <tr>
      <td>1</td><td>43217</td><td>Babakan Karet</td><td>Cianjur</td>
      <td>KAB. CIANJUR</td><td>JAWA BARAT</td>
    </tr>
    <tr>
      <td>2</td><td>99999</td><td>Babakan Karet</td><td>Other</td>
      <td>KAB. CIANJUR</td><td>JAWA BARAT</td>
    </tr>
  </tbody>
</table>
"""


class PosCandidateFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = {
            "province_code": "32",
            "province_name": "JAWA BARAT",
            "city_code": "32.03",
            "city_name": "KAB. CIANJUR",
            "district_code": "32.03.01",
            "district_name": "CIANJUR",
            "village_code": "32.03.01.2001",
            "village_name": "BABAKAN KARET",
            "postal_code_diskominfo": "43217",
            "suggested_postal_code": "43211",
        }

    def test_parses_result_rows(self) -> None:
        results = MODULE.parse_results(HTML)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["postal_code"], "43217")
        self.assertEqual(results[0]["village_name"], "Babakan Karet")

    def test_exact_match_uses_full_administrative_chain(self) -> None:
        exact = MODULE.exact_results(self.row, MODULE.parse_results(HTML))
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0]["postal_code"], "43217")

    def test_observation_is_not_automatically_promoted(self) -> None:
        cache = {
            "queries": {
                MODULE.query_key("BABAKAN KARET"): {
                    "results": MODULE.parse_results(HTML)
                }
            }
        }
        result = MODULE.build_observations([self.row], cache, "2026-08-11")[0]
        self.assertEqual(result["observation_status"], "exact_match")
        self.assertEqual(result["official_postal_code"], "43217")
        self.assertEqual(result["matches_diskominfo"], "true")
        self.assertEqual(result["matches_candidate"], "false")
        self.assertNotIn("review_decision", result)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "extract_osm_streets_landmarks", ROOT / "scripts" / "extract_osm_streets_landmarks.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

from alamatin.osm_pbf import OsmNode, OsmWay  # noqa: E402

BBOX = {"min_lat": -7.0, "max_lat": -6.0, "min_lon": 107.0, "max_lon": 108.0}


class ExtractFromBlocksTest(unittest.TestCase):
    def test_way_inside_bbox_via_referenced_node_is_kept(self) -> None:
        node = OsmNode(id=1, lat=-6.9, lon=107.6, tags={})
        way = OsmWay(id=10, node_ids=(1,), tags={"highway": "primary", "name": "Jl. Test"})
        blocks = [([node], [way])]
        streets, landmarks, counts = MODULE.extract_from_blocks(blocks, blocks, BBOX)
        self.assertEqual(len(streets), 1)
        self.assertEqual(streets[0]["name"], "Jl. Test")
        self.assertEqual(counts["street_way_candidates"], 1)

    def test_way_outside_bbox_is_dropped(self) -> None:
        node = OsmNode(id=1, lat=0.0, lon=0.0, tags={})  # far outside BBOX
        way = OsmWay(id=10, node_ids=(1,), tags={"highway": "primary", "name": "Jl. Jauh"})
        blocks = [([node], [way])]
        streets, landmarks, counts = MODULE.extract_from_blocks(blocks, blocks, BBOX)
        self.assertEqual(streets, [])

    def test_way_with_no_relevant_tags_is_dropped_even_if_in_bbox(self) -> None:
        node = OsmNode(id=1, lat=-6.9, lon=107.6, tags={})
        way = OsmWay(id=10, node_ids=(1,), tags={"surface": "asphalt"})  # no highway/addr
        blocks = [([node], [way])]
        streets, _, counts = MODULE.extract_from_blocks(blocks, blocks, BBOX)
        self.assertEqual(streets, [])
        self.assertEqual(counts["ways_seen"], 1)

    def test_landmark_node_in_bbox_is_kept(self) -> None:
        node = OsmNode(id=1, lat=-6.9, lon=107.6, tags={"amenity": "school", "name": "SDN Contoh"})
        blocks = [([node], [])]
        streets, landmarks, counts = MODULE.extract_from_blocks(blocks, blocks, BBOX)
        self.assertEqual(len(landmarks), 1)
        self.assertEqual(landmarks[0]["category"], "school")
        self.assertEqual(counts["nodes_in_bbox"], 1)

    def test_addr_tags_are_captured_on_both_nodes_and_ways(self) -> None:
        node = OsmNode(id=1, lat=-6.9, lon=107.6, tags={"addr:housenumber": "12", "amenity": "cafe", "name": "Kafe X"})
        blocks = [([node], [])]
        streets, landmarks, _ = MODULE.extract_from_blocks(blocks, blocks, BBOX)
        self.assertEqual(landmarks[0]["addr_tags"], {"addr:housenumber": "12"})

    def test_way_with_no_seen_node_coordinate_is_dropped(self) -> None:
        way = OsmWay(id=10, node_ids=(999,), tags={"highway": "primary", "name": "Jl. Hilang"})
        blocks = [([], [way])]
        streets, _, _ = MODULE.extract_from_blocks(blocks, blocks, BBOX)
        self.assertEqual(streets, [])

    def test_way_representative_uses_second_in_bbox_node_when_first_is_outside(self) -> None:
        # Regression test: a way can start outside the bbox and cross into it.
        # The representative lookup must find that in-bbox node even though
        # it isn't the way's first referenced node.
        outside = OsmNode(id=1, lat=0.0, lon=0.0, tags={})
        inside = OsmNode(id=2, lat=-6.9, lon=107.6, tags={})
        way = OsmWay(id=10, node_ids=(1, 2), tags={"highway": "primary", "name": "Jl. Lintas"})
        blocks = [([outside, inside], [way])]
        streets, _, _ = MODULE.extract_from_blocks(blocks, blocks, BBOX)
        self.assertEqual(len(streets), 1)
        self.assertEqual(streets[0]["lat"], -6.9)


class TagAllowlistTest(unittest.TestCase):
    def test_addr_tag_names_are_not_double_prefixed(self) -> None:
        # Regression test: _addr_tags keeps the full "addr:*" key, so the
        # allowlist must append addr_tag_names as-is -- previously this
        # re-prepended "addr:" and produced entries like "addr:addr:rt".
        allowlist = MODULE._build_tag_allowlist(["addr:rt", "addr:rw"])
        self.assertIn("addr:rt", allowlist)
        self.assertIn("addr:rw", allowlist)
        self.assertNotIn("addr:addr:rt", allowlist)


class DedupeTest(unittest.TestCase):
    def test_collapses_repeated_way_segments_of_the_same_named_road(self) -> None:
        rows = [
            {"osm_type": "way", "osm_id": 1, "name": "Jl. Asia Afrika", "highway": "primary", "lat": -6.9, "lon": 107.6, "addr_tags": {}},
            {"osm_type": "way", "osm_id": 2, "name": "Jl. Asia Afrika", "highway": "primary", "lat": -6.91, "lon": 107.61, "addr_tags": {}},
            {"osm_type": "way", "osm_id": 3, "name": "jl. asia afrika", "highway": "primary", "lat": -6.92, "lon": 107.62, "addr_tags": {}},
        ]
        deduped = MODULE.dedupe_streets(rows)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["segment_count"], 3)

    def test_different_highway_types_are_not_merged(self) -> None:
        rows = [
            {"osm_type": "way", "osm_id": 1, "name": "Jl. X", "highway": "primary", "lat": 0, "lon": 0, "addr_tags": {}},
            {"osm_type": "way", "osm_id": 2, "name": "Jl. X", "highway": "residential", "lat": 0, "lon": 0, "addr_tags": {}},
        ]
        deduped = MODULE.dedupe_streets(rows)
        self.assertEqual(len(deduped), 2)

    def test_unnamed_ways_are_excluded_from_deduped_output(self) -> None:
        rows = [{"osm_type": "way", "osm_id": 1, "name": "", "highway": "primary", "lat": 0, "lon": 0, "addr_tags": {}}]
        self.assertEqual(MODULE.dedupe_streets(rows), [])

    def test_landmark_dedup_keeps_occurrence_count(self) -> None:
        rows = [
            {"osm_type": "node", "osm_id": 1, "name": "Puskesmas Sukajadi", "category": "clinic", "lat": 0, "lon": 0, "addr_tags": {}},
            {"osm_type": "node", "osm_id": 2, "name": "Puskesmas Sukajadi", "category": "clinic", "lat": 0.01, "lon": 0.01, "addr_tags": {}},
        ]
        deduped = MODULE.dedupe_landmarks(rows)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["occurrence_count"], 2)


if __name__ == "__main__":
    unittest.main()

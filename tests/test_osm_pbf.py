"""Tests for the stdlib-only OSM PBF reader.

Builds tiny hand-encoded protobuf fixtures (there is no real .osm.pbf file in
the repository -- the actual Geofabrik snapshot is a gitignored raw
download) so the parser can be verified without any external file or
third-party protobuf library.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin import osm_pbf  # noqa: E402


# --- minimal protobuf encoder, test-fixture use only ------------------------

def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _encode_zigzag(value: int) -> int:
    return 2 * value if value >= 0 else (-2 * value - 1)


def _tag(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _field_varint(field_number: int, value: int) -> bytes:
    return _tag(field_number, 0) + _encode_varint(value)


def _field_bytes(field_number: int, payload: bytes) -> bytes:
    return _tag(field_number, 2) + _encode_varint(len(payload)) + payload


def _field_packed_signed(field_number: int, values: list[int]) -> bytes:
    payload = b"".join(_encode_varint(_encode_zigzag(v)) for v in values)
    return _field_bytes(field_number, payload)


def _field_packed(field_number: int, values: list[int]) -> bytes:
    payload = b"".join(_encode_varint(v) for v in values)
    return _field_bytes(field_number, payload)


def _build_stringtable(strings: list[str]) -> bytes:
    payload = b"".join(_field_bytes(1, s.encode("utf-8")) for s in strings)
    return payload


def _build_dense_nodes(ids: list[int], lats: list[int], lons: list[int], keys_vals: list[int]) -> bytes:
    # ids/lats/lons here are already the *values to sum* (deltas); tests pass
    # absolute values with a single entry, or explicit deltas for multiple.
    payload = (
        _field_packed_signed(1, ids)
        + _field_packed_signed(8, lats)
        + _field_packed_signed(9, lons)
    )
    if keys_vals:
        payload += _field_packed(10, keys_vals)
    return payload


def _build_way(way_id: int, keys: list[int], vals: list[int], refs_delta: list[int]) -> bytes:
    payload = _field_varint(1, way_id)
    if keys:
        payload += _field_packed(2, keys)
    if vals:
        payload += _field_packed(3, vals)
    if refs_delta:
        payload += _field_packed_signed(8, refs_delta)
    return payload


def _build_primitive_block(stringtable: list[str], dense_bytes: bytes | None, way_bytes: list[bytes]) -> bytes:
    payload = _field_bytes(1, _build_stringtable(stringtable))
    group_payload = b""
    if dense_bytes is not None:
        group_payload += _field_bytes(2, dense_bytes)
    for way in way_bytes:
        group_payload += _field_bytes(3, way)
    payload += _field_bytes(2, group_payload)
    return payload


class ParsePrimitiveBlockTest(unittest.TestCase):
    def test_parses_dense_nodes_with_tags(self) -> None:
        # Real Geofabrik files leave stringtable index 0 unused/blank so it is
        # safe to reuse as the DenseNodes keys_vals terminator; this fixture
        # follows that convention explicitly rather than relying on the
        # reader to invent it (see _parse_stringtable's docstring).
        stringtable = ["", "amenity", "school", "name", "SDN Contoh"]
        # Two nodes: first tagged (amenity=school, name=SDN Contoh), second untagged.
        dense = _build_dense_nodes(
            ids=[100, 1],  # id0=100 (delta from 0), id1=101 (delta +1)
            lats=[-6_900_000, 0],  # scaled later by granularity
            lons=[107_600_000, 0],
            keys_vals=[1, 2, 3, 4, 0, 0],  # node0 tags, then 0 terminator, node1 no tags (empty then terminator)
        )
        block = _build_primitive_block(stringtable, dense, [])
        nodes, ways = osm_pbf.parse_primitive_block(block)

        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0].id, 100)
        self.assertEqual(nodes[0].tags, {"amenity": "school", "name": "SDN Contoh"})
        self.assertEqual(nodes[1].id, 101)
        self.assertEqual(nodes[1].tags, {})
        self.assertEqual(ways, [])

    def test_decodes_lat_lon_with_granularity_and_offset(self) -> None:
        stringtable: list[str] = []
        dense = _build_dense_nodes(ids=[1], lats=[100], lons=[200], keys_vals=[])
        payload = (
            _field_bytes(1, _build_stringtable(stringtable))
            + _field_bytes(2, _field_bytes(2, dense))
            + _field_varint(17, 1000)  # granularity
            + _field_varint(19, _encode_zigzag(5))  # lat_offset
            + _field_varint(20, _encode_zigzag(7))  # lon_offset
        )
        nodes, _ = osm_pbf.parse_primitive_block(payload)
        self.assertEqual(len(nodes), 1)
        self.assertAlmostEqual(nodes[0].lat, 1e-9 * (5 + 1000 * 100))
        self.assertAlmostEqual(nodes[0].lon, 1e-9 * (7 + 1000 * 200))

    def test_parses_a_way_with_tags_and_node_refs(self) -> None:
        stringtable = ["", "highway", "primary", "name", "Jalan Test"]
        way = _build_way(way_id=55, keys=[1, 3], vals=[2, 4], refs_delta=[100, 1, 1])
        block = _build_primitive_block(stringtable, None, [way])
        nodes, ways = osm_pbf.parse_primitive_block(block)

        self.assertEqual(nodes, [])
        self.assertEqual(len(ways), 1)
        self.assertEqual(ways[0].id, 55)
        self.assertEqual(ways[0].tags, {"highway": "primary", "name": "Jalan Test"})
        self.assertEqual(ways[0].node_ids, (100, 101, 102))

    def test_way_with_no_tags_has_empty_tag_dict(self) -> None:
        way = _build_way(way_id=1, keys=[], vals=[], refs_delta=[5])
        block = _build_primitive_block([], None, [way])
        _, ways = osm_pbf.parse_primitive_block(block)
        self.assertEqual(ways[0].tags, {})

    def test_stringtable_index_0_is_not_artificially_reserved(self) -> None:
        # Regression test: the reader must not prepend its own blank entry --
        # a file's string table is 0-indexed exactly as encoded. Getting this
        # wrong shifts every tag lookup off by one against real data.
        stringtable = ["highway", "primary", "name", "Jalan Test"]
        way = _build_way(way_id=1, keys=[0, 2], vals=[1, 3], refs_delta=[5])
        block = _build_primitive_block(stringtable, None, [way])
        _, ways = osm_pbf.parse_primitive_block(block)
        self.assertEqual(ways[0].tags, {"highway": "primary", "name": "Jalan Test"})


class BlobAndFileLevelTest(unittest.TestCase):
    def _write_pbf(self, path: Path, blocks: list[tuple[str, bytes, bool]]) -> None:
        with path.open("wb") as stream:
            for blob_type, data, compress in blocks:
                if compress:
                    blob = _field_bytes(3, zlib.compress(data))
                else:
                    blob = _field_bytes(1, data)
                header = _field_bytes(1, blob_type.encode("utf-8")) + _field_varint(3, len(blob))
                stream.write(struct.pack(">I", len(header)))
                stream.write(header)
                stream.write(blob)

    def test_reads_a_raw_uncompressed_block(self) -> None:
        block = _build_primitive_block(["", "highway", "residential"], None, [_build_way(1, [1], [2], [10])])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.osm.pbf"
            self._write_pbf(path, [("OSMHeader", b"", False), ("OSMData", block, False)])
            blocks = list(osm_pbf.iter_primitive_blocks(path))
            self.assertEqual(len(blocks), 1)
            nodes, ways = osm_pbf.parse_primitive_block(blocks[0])
            self.assertEqual(ways[0].tags, {"highway": "residential"})

    def test_reads_a_zlib_compressed_block(self) -> None:
        dense = _build_dense_nodes(ids=[1], lats=[1], lons=[1], keys_vals=[1, 2, 0])
        block = _build_primitive_block(["", "amenity", "hospital"], dense, [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.osm.pbf"
            self._write_pbf(path, [("OSMHeader", b"", False), ("OSMData", block, True)])
            results = list(osm_pbf.iter_nodes_and_ways(path))
            self.assertEqual(len(results), 1)
            nodes, ways = results[0]
            self.assertEqual(nodes[0].tags, {"amenity": "hospital"})

    def test_raises_on_unrecognized_blob_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.osm.pbf"
            self._write_pbf(path, [("OSMSomethingElse", b"", False)])
            with self.assertRaises(osm_pbf.OsmPbfError):
                list(osm_pbf.iter_primitive_blocks(path))

    def test_multiple_blocks_are_all_yielded(self) -> None:
        block_a = _build_primitive_block(["", "highway", "primary"], None, [_build_way(1, [1], [2], [5])])
        block_b = _build_primitive_block(["", "highway", "secondary"], None, [_build_way(2, [1], [2], [6])])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.osm.pbf"
            self._write_pbf(
                path,
                [("OSMHeader", b"", False), ("OSMData", block_a, False), ("OSMData", block_b, False)],
            )
            results = list(osm_pbf.iter_nodes_and_ways(path))
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0][1][0].tags["highway"], "primary")
            self.assertEqual(results[1][1][0].tags["highway"], "secondary")


if __name__ == "__main__":
    unittest.main()

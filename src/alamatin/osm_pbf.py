"""Minimal stdlib-only OSM PBF reader (ALM-009).

Implements just enough of the protobuf wire format and the OSM PBF schema
(``fileformat.proto``'s BlobHeader/Blob and ``osmformat.proto``'s
PrimitiveBlock/PrimitiveGroup/DenseNodes/Way/StringTable) to stream nodes
and ways with their tags out of a ``.osm.pbf`` file, with no third-party
protobuf or OSM library -- per the project's standing stdlib-only decision
(``docs/decision-log.md`` DEC-002).

Relations and changesets are not parsed. ALM-009 only needs point/way
features (roads via `highway`, landmarks via `amenity`/`place`, and
`addr:*` tags), which are carried entirely by nodes and ways.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class OsmPbfError(ValueError):
    """Raised when the PBF stream is malformed or uses an unsupported feature."""


@dataclass(frozen=True)
class OsmNode:
    id: int
    lat: float
    lon: float
    tags: dict[str, str]


@dataclass(frozen=True)
class OsmWay:
    id: int
    node_ids: tuple[int, ...]
    tags: dict[str, str]


# ---------------------------------------------------------------------------
# Low-level protobuf wire format (generic, not schema-specific).
# ---------------------------------------------------------------------------

def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise OsmPbfError("truncated varint")
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if not (byte & 0x80):
            return result, pos
        shift += 7


def _zigzag_decode(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _iter_fields(data: bytes) -> Iterator[tuple[int, int, int, int]]:
    """Yield ``(field_number, wire_type, start, end)`` for each top-level field.

    ``start``/``end`` bound the field's payload bytes: the varint itself for
    wire type 0, or the length-delimited content (header excluded) for wire
    type 2. Wire types 1 and 5 are only supported enough to skip correctly.
    """

    pos = 0
    n = len(data)
    while pos < n:
        tag, pos = _read_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x7
        if wire_type == 0:
            start = pos
            _, pos = _read_varint(data, pos)
            yield field_number, wire_type, start, pos
        elif wire_type == 2:
            length, pos = _read_varint(data, pos)
            start = pos
            pos += length
            if pos > n:
                raise OsmPbfError("length-delimited field exceeds buffer")
            yield field_number, wire_type, start, pos
        elif wire_type == 1:
            yield field_number, wire_type, pos, pos + 8
            pos += 8
        elif wire_type == 5:
            yield field_number, wire_type, pos, pos + 4
            pos += 4
        else:
            raise OsmPbfError(f"unsupported wire type {wire_type}")


def _varint_value(data: bytes, start: int, end: int) -> int:
    value, _ = _read_varint(data, start)
    return value


def _packed_varints(data: bytes, start: int, end: int) -> list[int]:
    values = []
    pos = start
    while pos < end:
        value, pos = _read_varint(data, pos)
        values.append(value)
    return values


def _packed_signed_varints(data: bytes, start: int, end: int) -> list[int]:
    return [_zigzag_decode(value) for value in _packed_varints(data, start, end)]


# ---------------------------------------------------------------------------
# fileformat.proto: BlobHeader / Blob
# ---------------------------------------------------------------------------

def _read_blob_pairs(stream: BinaryIO) -> Iterator[tuple[str, bytes]]:
    while True:
        length_bytes = stream.read(4)
        if not length_bytes:
            return
        if len(length_bytes) < 4:
            raise OsmPbfError("truncated blob header length")
        (header_length,) = struct.unpack(">I", length_bytes)
        header_bytes = stream.read(header_length)
        if len(header_bytes) < header_length:
            raise OsmPbfError("truncated blob header")

        blob_type = None
        datasize = None
        for field_number, wire_type, start, end in _iter_fields(header_bytes):
            if field_number == 1 and wire_type == 2:
                blob_type = header_bytes[start:end].decode("utf-8")
            elif field_number == 3 and wire_type == 0:
                datasize = _varint_value(header_bytes, start, end)
        if blob_type is None or datasize is None:
            raise OsmPbfError("BlobHeader missing type or datasize")

        blob_bytes = stream.read(datasize)
        if len(blob_bytes) < datasize:
            raise OsmPbfError("truncated blob")
        yield blob_type, blob_bytes


def _decode_blob(blob_bytes: bytes) -> bytes:
    raw: bytes | None = None
    zlib_data: bytes | None = None
    for field_number, wire_type, start, end in _iter_fields(blob_bytes):
        if field_number == 1 and wire_type == 2:
            raw = blob_bytes[start:end]
        elif field_number == 3 and wire_type == 2:
            zlib_data = blob_bytes[start:end]
        elif field_number == 4 and wire_type == 2:
            raise OsmPbfError("lzma-compressed blob is not supported")
    if raw is not None:
        return raw
    if zlib_data is not None:
        return zlib.decompress(zlib_data)
    raise OsmPbfError("Blob has neither raw nor zlib_data")


# ---------------------------------------------------------------------------
# osmformat.proto: StringTable / PrimitiveBlock / DenseNodes / Way
# ---------------------------------------------------------------------------

def _parse_stringtable(data: bytes) -> list[str]:
    """Parse ``StringTable.s`` as-is: index 0 is whatever the file encodes as
    its first entry, not an artificial reserved blank. Writers conventionally
    leave that first entry unused so 0 is safe to use as the DenseNodes
    keys_vals terminator, but that is a convention of well-formed files, not
    something this reader should impose itself -- doing so previously shifted
    every string-table lookup off by one against real Geofabrik data.
    """

    strings: list[str] = []
    for field_number, wire_type, start, end in _iter_fields(data):
        if field_number == 1 and wire_type == 2:
            strings.append(data[start:end].decode("utf-8", errors="replace"))
    return strings


def _decode_lat_lon(value: int, offset: int, granularity: int) -> float:
    return 1e-9 * (offset + (granularity * value))


def _parse_dense_nodes(
    data: bytes, stringtable: list[str], granularity: int, lat_offset: int, lon_offset: int
) -> list[OsmNode]:
    ids: list[int] = []
    lats: list[int] = []
    lons: list[int] = []
    keys_vals: list[int] = []
    for field_number, wire_type, start, end in _iter_fields(data):
        if field_number == 1:
            ids = _packed_signed_varints(data, start, end)
        elif field_number == 8:
            lats = _packed_signed_varints(data, start, end)
        elif field_number == 9:
            lons = _packed_signed_varints(data, start, end)
        elif field_number == 10:
            keys_vals = _packed_varints(data, start, end)
        # field 5 = denseinfo (timestamps/changesets/users): skip, not needed.

    nodes: list[OsmNode] = []
    current_id = current_lat = current_lon = 0
    kv_index = 0
    for index in range(len(ids)):
        current_id += ids[index]
        current_lat += lats[index]
        current_lon += lons[index]
        tags: dict[str, str] = {}
        if keys_vals:
            while kv_index < len(keys_vals) and keys_vals[kv_index] != 0:
                key = stringtable[keys_vals[kv_index]]
                value = stringtable[keys_vals[kv_index + 1]]
                tags[key] = value
                kv_index += 2
            kv_index += 1  # skip the 0 terminator between nodes
        nodes.append(
            OsmNode(
                id=current_id,
                lat=_decode_lat_lon(current_lat, lat_offset, granularity),
                lon=_decode_lat_lon(current_lon, lon_offset, granularity),
                tags=tags,
            )
        )
    return nodes


def _parse_plain_node(
    data: bytes, stringtable: list[str], granularity: int, lat_offset: int, lon_offset: int
) -> OsmNode:
    node_id = None
    keys: list[int] = []
    vals: list[int] = []
    lat = lon = None
    for field_number, wire_type, start, end in _iter_fields(data):
        if field_number == 1 and wire_type == 0:
            node_id = _varint_value(data, start, end)
        elif field_number == 2:
            keys = _packed_varints(data, start, end)
        elif field_number == 3:
            vals = _packed_varints(data, start, end)
        elif field_number == 8 and wire_type == 0:
            lat = _zigzag_decode(_varint_value(data, start, end))
        elif field_number == 9 and wire_type == 0:
            lon = _zigzag_decode(_varint_value(data, start, end))
    if node_id is None or lat is None or lon is None:
        raise OsmPbfError("Node missing id/lat/lon")
    tags = {stringtable[k]: stringtable[v] for k, v in zip(keys, vals)}
    return OsmNode(
        id=node_id,
        lat=_decode_lat_lon(lat, lat_offset, granularity),
        lon=_decode_lat_lon(lon, lon_offset, granularity),
        tags=tags,
    )


def _parse_way(data: bytes, stringtable: list[str]) -> OsmWay:
    way_id = None
    keys: list[int] = []
    vals: list[int] = []
    refs_delta: list[int] = []
    for field_number, wire_type, start, end in _iter_fields(data):
        if field_number == 1 and wire_type == 0:
            way_id = _varint_value(data, start, end)
        elif field_number == 2:
            keys = _packed_varints(data, start, end)
        elif field_number == 3:
            vals = _packed_varints(data, start, end)
        elif field_number == 8:
            refs_delta = _packed_signed_varints(data, start, end)
        # field 4 = info: skip, not needed.
    if way_id is None:
        raise OsmPbfError("Way missing id")
    tags = {stringtable[k]: stringtable[v] for k, v in zip(keys, vals)}
    node_ids = []
    current = 0
    for delta in refs_delta:
        current += delta
        node_ids.append(current)
    return OsmWay(id=way_id, node_ids=tuple(node_ids), tags=tags)


def parse_primitive_block(data: bytes) -> tuple[list[OsmNode], list[OsmWay]]:
    stringtable: list[str] = [""]
    granularity = 100
    lat_offset = 0
    lon_offset = 0
    group_spans: list[tuple[int, int]] = []

    for field_number, wire_type, start, end in _iter_fields(data):
        if field_number == 1:
            stringtable = _parse_stringtable(data[start:end])
        elif field_number == 2:
            group_spans.append((start, end))
        elif field_number == 17:
            granularity = _varint_value(data, start, end)
        elif field_number == 19:
            lat_offset = _zigzag_decode(_varint_value(data, start, end))
        elif field_number == 20:
            lon_offset = _zigzag_decode(_varint_value(data, start, end))

    nodes: list[OsmNode] = []
    ways: list[OsmWay] = []
    for group_start, group_end in group_spans:
        group_bytes = data[group_start:group_end]
        for field_number, wire_type, start, end in _iter_fields(group_bytes):
            if field_number == 1:
                nodes.append(_parse_plain_node(group_bytes[start:end], stringtable, granularity, lat_offset, lon_offset))
            elif field_number == 2:
                nodes.extend(_parse_dense_nodes(group_bytes[start:end], stringtable, granularity, lat_offset, lon_offset))
            elif field_number == 3:
                ways.append(_parse_way(group_bytes[start:end], stringtable))
            # field 4 = relations, field 5 = changesets: skip, not needed.
    return nodes, ways


def iter_primitive_blocks(pbf_path: Path) -> Iterator[bytes]:
    """Yield each ``OSMData`` blob's decompressed ``PrimitiveBlock`` bytes."""

    with pbf_path.open("rb") as stream:
        for blob_type, blob_bytes in _read_blob_pairs(stream):
            if blob_type == "OSMHeader":
                continue
            if blob_type == "OSMData":
                yield _decode_blob(blob_bytes)
                continue
            raise OsmPbfError(f"unrecognized blob type {blob_type!r}")


def iter_nodes_and_ways(pbf_path: Path) -> Iterator[tuple[list[OsmNode], list[OsmWay]]]:
    """Stream ``(nodes, ways)`` per ``PrimitiveBlock`` in ``pbf_path``."""

    for block_data in iter_primitive_blocks(pbf_path):
        yield parse_primitive_block(block_data)

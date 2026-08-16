#!/usr/bin/env python3
"""Stage OSM street/landmark candidates for Jawa Barat/Bandung Raya (ALM-009).

Reads a Geofabrik Java ``.osm.pbf`` snapshot with the stdlib-only reader in
``alamatin.osm_pbf``, clips to a Jawa Barat/Bandung Raya bounding box (the
MVP scope -- this is not Java-wide or national coverage), and writes
deduplicated street (way `highway`/`name`) and landmark (node
`amenity`/`place`/`name`) candidate tables plus a governance manifest.

This script only stages candidates. It does not integrate them into
scripts/generate_synthetic_addresses.py or regenerate data/synthetic/*.json
-- see data/sources.md's entry for osm_geofabrik_java_2026_08_14 for why.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.osm_pbf import OsmNode, OsmWay, iter_nodes_and_ways  # noqa: E402

SOURCE_ID = "osm_geofabrik_java_2026_08_14"
SNAPSHOT = "Geofabrik java-260814.osm.pbf, produced 2026-08-14"
ATTRIBUTION = "Copyright OpenStreetMap contributors; data available under ODbL 1.0 (https://www.openstreetmap.org/copyright)"

# Jawa Barat/Bandung Raya MVP bounding box (a superset of the province's
# administrative boundary, not a precise polygon clip -- documented as a
# limitation, not overclaimed as exact or as Java-wide/national coverage).
JAWA_BARAT_BBOX = {"min_lat": -7.85, "max_lat": -5.85, "min_lon": 106.30, "max_lon": 108.90}

ADDR_TAG_PREFIX = "addr:"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "interim" / "osm-extraction"


def _in_bbox(lat: float, lon: float, bbox: dict[str, float]) -> bool:
    return bbox["min_lat"] <= lat <= bbox["max_lat"] and bbox["min_lon"] <= lon <= bbox["max_lon"]


def _addr_tags(tags: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in tags.items() if key.startswith(ADDR_TAG_PREFIX)}


def _scan_landmarks_and_candidate_ways(
    blocks: Iterable[tuple[list[OsmNode], list[OsmWay]]], bbox: dict[str, float]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Pass 1: collect landmark rows and *candidate* way rows (no coordinates yet).

    Landmarks are emitted immediately from node tags, same as before. For
    ways, only each candidate's referenced node ids are recorded -- not every
    in-bbox node's coordinates -- so this pass holds at most "node ids
    referenced by highway/addr-tagged ways" in memory, instead of one entry
    per in-bbox node of any kind. That distinction is what made the
    single-pass version OOM against the full Java extract: most of the
    file's blocks are plain nodes, so a dict keyed by every in-bbox node grew
    to tens of millions of entries before a single way was ever read, while
    the ways that actually need those coordinates are a much smaller subset.
    Bounding-box filtering for ways is deferred to pass 2, once at least one
    referenced node's actual coordinates are known.
    """

    landmark_rows: list[dict[str, Any]] = []
    candidate_ways: list[dict[str, Any]] = []
    counts = {
        "nodes_seen": 0,
        "nodes_in_bbox": 0,
        "landmark_node_candidates": 0,
        "ways_seen": 0,
    }

    for nodes, ways in blocks:
        for node in nodes:
            counts["nodes_seen"] += 1
            if not _in_bbox(node.lat, node.lon, bbox):
                continue
            counts["nodes_in_bbox"] += 1

            category = node.tags.get("amenity") or node.tags.get("place")
            name = node.tags.get("name", "")
            addr = _addr_tags(node.tags)
            if category or addr:
                counts["landmark_node_candidates"] += 1
                landmark_rows.append(
                    {
                        "osm_type": "node",
                        "osm_id": node.id,
                        "name": name,
                        "category": category or "",
                        "lat": node.lat,
                        "lon": node.lon,
                        "addr_tags": addr,
                    }
                )

        for way in ways:
            counts["ways_seen"] += 1
            highway = way.tags.get("highway", "")
            name = way.tags.get("name", "")
            addr = _addr_tags(way.tags)
            if not (highway or addr) or not way.node_ids:
                continue
            candidate_ways.append(
                {
                    "osm_id": way.id,
                    "name": name,
                    "highway": highway,
                    "addr_tags": addr,
                    "node_ids": way.node_ids,
                }
            )

    return landmark_rows, candidate_ways, counts


def _resolve_way_coordinates(
    blocks: Iterable[tuple[list[OsmNode], list[OsmWay]]],
    needed_node_ids: set[int],
    bbox: dict[str, float],
) -> dict[int, tuple[float, float]]:
    """Pass 2: look up in-bbox coordinates only for the node ids pass 1 needs.

    Only in-bbox coordinates are kept (matching the single-pass version's
    implicit filtering, where a node's coordinates were only ever recorded if
    it was in-bbox) so a way's representative is guaranteed in-bbox once
    resolved, with no extra bbox check needed at the call site.
    """

    resolved: dict[int, tuple[float, float]] = {}
    for nodes, _ways in blocks:
        for node in nodes:
            if node.id in needed_node_ids and node.id not in resolved and _in_bbox(node.lat, node.lon, bbox):
                resolved[node.id] = (node.lat, node.lon)
    return resolved


def extract_from_blocks(
    first_pass_blocks: Iterable[tuple[list[OsmNode], list[OsmWay]]],
    second_pass_blocks: Iterable[tuple[list[OsmNode], list[OsmWay]]],
    bbox: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Extract street/landmark candidate rows using two streaming passes.

    Two independent block iterables are required (typically two separate
    calls to ``iter_nodes_and_ways`` over the same file) because pass 2 needs
    to re-read the node section after pass 1 has already determined which
    node ids are actually needed as way representatives.
    """

    landmark_rows, candidate_ways, counts = _scan_landmarks_and_candidate_ways(first_pass_blocks, bbox)
    needed_node_ids: set[int] = set()
    for way in candidate_ways:
        needed_node_ids.update(way["node_ids"])
    node_coords = _resolve_way_coordinates(second_pass_blocks, needed_node_ids, bbox)

    street_rows: list[dict[str, Any]] = []
    counts["street_way_candidates"] = 0
    for way in candidate_ways:
        representative = next(
            (node_coords[ref] for ref in way["node_ids"] if ref in node_coords), None
        )
        if representative is None:
            continue
        lat, lon = representative
        counts["street_way_candidates"] += 1
        street_rows.append(
            {
                "osm_type": "way",
                "osm_id": way["osm_id"],
                "name": way["name"],
                "highway": way["highway"],
                "lat": lat,
                "lon": lon,
                "addr_tags": way["addr_tags"],
            }
        )

    return street_rows, landmark_rows, counts


def dedupe_streets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated way segments of the same named road into one row.

    A single named road is typically split into many way segments at
    intersections in OSM -- these are not meaningful duplicates, so the
    segment count is kept (not discarded) rather than silently dropped.
    Unnamed ways are excluded here (they carry no reusable street name) but
    are still counted in the pre-cleaning totals for transparency.
    """

    named = [row for row in rows if row["name"].strip()]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in named:
        key = (row["name"].strip().casefold(), row["highway"])
        groups.setdefault(key, []).append(row)
    deduped = [{**group[0], "segment_count": len(group)} for group in groups.values()]
    return sorted(deduped, key=lambda row: (row["name"].casefold(), row["highway"]))


def dedupe_landmarks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    named = [row for row in rows if row["name"].strip()]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in named:
        key = (row["name"].strip().casefold(), row["category"])
        groups.setdefault(key, []).append(row)
    deduped = [{**group[0], "occurrence_count": len(group)} for group in groups.values()]
    return sorted(deduped, key=lambda row: (row["name"].casefold(), row["category"]))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = {key: value for key, value in row.items() if key != "addr_tags"}
            flat.update({f"tag_{key}": value for key, value in row.get("addr_tags", {}).items()})
            writer.writerow({name: flat.get(name, "") for name in fieldnames})
    temporary.replace(path)


def _with_progress(
    blocks: Iterable[tuple[list[OsmNode], list[OsmWay]]], label: str, every: int = 500
) -> Iterable[tuple[list[OsmNode], list[OsmWay]]]:
    """Print a running block count to stderr so a long run can be monitored."""

    started_at = time.perf_counter()
    count = 0
    for nodes, ways in blocks:
        count += 1
        if count % every == 0:
            elapsed = time.perf_counter() - started_at
            print(f"{label}: {count} blocks ({elapsed:.0f}s elapsed)", file=sys.stderr, flush=True)
        yield nodes, ways
    print(f"{label}: done, {count} blocks total ({time.perf_counter() - started_at:.0f}s elapsed)", file=sys.stderr, flush=True)


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_tag_allowlist(addr_tag_names: list[str]) -> list[str]:
    """Build the governance manifest's declared tag allowlist.

    ``addr_tag_names`` already carries the full ``addr:*`` key (see
    ``_addr_tags``, which does not strip the prefix) -- it must be appended
    as-is, not re-prefixed with ``addr:`` again.
    """

    return ["name", "highway", "amenity", "place"] + addr_tag_names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.pbf.exists():
            raise FileNotFoundError(f"PBF snapshot not found: {args.pbf}")

        started_at = time.perf_counter()
        first_pass = _with_progress(iter_nodes_and_ways(args.pbf), "pass 1/2 (scan)")
        second_pass = _with_progress(iter_nodes_and_ways(args.pbf), "pass 2/2 (resolve)")
        street_raw, landmark_raw, counts = extract_from_blocks(
            first_pass, second_pass, JAWA_BARAT_BBOX
        )
        streets = dedupe_streets(street_raw)
        landmarks = dedupe_landmarks(landmark_raw)
        elapsed_seconds = time.perf_counter() - started_at

        addr_tag_names = sorted(
            {key for row in street_raw + landmark_raw for key in row["addr_tags"]}
        )
        street_fields = ("osm_type", "osm_id", "name", "highway", "lat", "lon", "segment_count") + tuple(
            f"tag_{name}" for name in addr_tag_names
        )
        landmark_fields = (
            "osm_type", "osm_id", "name", "category", "lat", "lon", "occurrence_count",
        ) + tuple(f"tag_{name}" for name in addr_tag_names)

        args.output_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(args.output_dir / "streets.csv", streets, street_fields)
        _write_csv(args.output_dir / "landmarks.csv", landmarks, landmark_fields)

        pbf_sha256 = _sha256_file(args.pbf)
        summary = {
            "source_id": SOURCE_ID,
            "snapshot": SNAPSHOT,
            "attribution": ATTRIBUTION,
            "pbf_path": str(args.pbf),
            "pbf_sha256": pbf_sha256,
            "bounding_box": JAWA_BARAT_BBOX,
            "coverage_note": (
                "Bounding box covers Jawa Barat/Bandung Raya (MVP scope) only. "
                "It is a rectangular superset of the province, not an exact "
                "administrative-boundary clip, and does not claim Java-wide or "
                "national coverage."
            ),
            "tag_allowlist": _build_tag_allowlist(addr_tag_names),
            "counts_before_cleaning": counts,
            "counts_after_cleaning": {
                "streets_named_unique": len(streets),
                "landmarks_named_unique": len(landmarks),
            },
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed_seconds, 1),
            "integration_status": (
                "staged_only -- not integrated into scripts/generate_synthetic_addresses.py "
                "or data/synthetic/*.json in this pass"
            ),
        }
        summary_path = args.output_dir / "extraction-summary.json"
        temporary = summary_path.with_name(f".{summary_path.name}.part")
        temporary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(summary_path)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in summary.items() if k != "pbf_path"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# OSM street/landmark extraction (ALM-009)

- Source catalog: `data/sources.json` version `1.7.0`, `source_id`
  `osm_geofabrik_java_2026_08_14`
- Canonical PBF reader: `src/alamatin/osm_pbf.py`
- Extraction script: `scripts/extract_osm_streets_landmarks.py`
- Status: **staged only, not integrated into the synthetic generator** --
  see "Why this is staged, not integrated" below.

## What this is

A reproducible extraction of OpenStreetMap street names (`highway` ways)
and landmark candidates (`amenity`/`place` nodes), including any `addr:*`
tags, clipped to a Jawa Barat/Bandung Raya bounding box -- this project's
MVP scope. It exists to eventually replace the synthetic generator's
generic, placeholder street/landmark pool (`scripts/generate_synthetic_addresses.py`)
with real Jawa Barat names, per the limitation already recorded in
`docs/synthetic_generator.md` and `data/sources.md`.

## Why a stdlib-only PBF reader

The project's standing dependency-free decision (`docs/decision-log.md`
DEC-002) means no third-party protobuf or OSM library (e.g. `osmium`,
`pyosmium`) is used. `.osm.pbf` is protobuf-encoded and zlib-compressed;
`src/alamatin/osm_pbf.py` implements only the specific subset of
`fileformat.proto` (BlobHeader/Blob) and `osmformat.proto`
(PrimitiveBlock/PrimitiveGroup/DenseNodes/Way/StringTable) this task needs,
using Python's stdlib `zlib` and a small hand-written protobuf wire-format
reader -- no relation/changeset parsing, since roads and point landmarks are
carried entirely by nodes and ways.

## Why Java, not the cataloged Indonesia-wide extract

`data/sources.json` already had an `osm_geofabrik_indonesia_2026_07_01`
entry from an earlier review, but it was never fetched. Since this project's
MVP scope is Jawa Barat/Bandung Raya (`docs/decision-log.md`), downloading
the much smaller Java-only Geofabrik sub-extract instead of the
whole-Indonesia file is both faster and a better scope match. See
`osm_geofabrik_java_2026_08_14` in `data/sources.json`/`data/sources.md` for
the full governance record; it supersedes the Indonesia-wide entry for this
acquisition only.

## Geographic scope and its limits

`JAWA_BARAT_BBOX` in `extract_osm_streets_landmarks.py` is a **rectangular
bounding box**, not an exact administrative-boundary polygon clip. It is a
superset of the province (it can include slivers of neighboring
provinces) and is never reported as Java-wide or national coverage --
`extraction-summary.json`'s `coverage_note` field says this explicitly on
every run, so the limitation travels with the data rather than needing to be
remembered separately.

A way is included if **at least one** of its referenced nodes was already
seen inside the bounding box (nodes are assumed to precede ways in the file,
the standard OSM PBF/Geofabrik convention) -- a way's full geometry may
extend outside the box.

## Cleaning: what "deduplicated" means here

A single named road is typically split into many way segments at
intersections in OSM -- collapsing those into one row is not the same as
removing genuine variation. `dedupe_streets`/`dedupe_landmarks` group by
`(name, highway_type)` or `(name, category)` and record a `segment_count`/
`occurrence_count` rather than silently discarding the repetition -- per the
task's own instruction ("bersihkan duplikasi tanpa menghapus variasi
penting"). Unnamed ways/nodes are dropped from the final tables (a street
pool needs names to be useful) but are still counted in
`counts_before_cleaning` for transparency.

## Reproducing

```bash
python scripts/acquire_sources.py fetch osm_geofabrik_java_2026_08_14
python scripts/extract_osm_streets_landmarks.py \
  --pbf data/raw/osm_geofabrik_java_2026_08_14/java-260814.osm.pbf
```

Output goes to `data/interim/osm-extraction/` (internal only): `streets.csv`,
`landmarks.csv`, and `extraction-summary.json` (source/version/coverage
metadata, tag allowlist, and before/after-cleaning record counts). The raw
`.osm.pbf` file itself (~895 MB) is never committed to Git -- it lives only
under the local, untracked `data/raw/` acquisition path, consistent with
every other source in `data/sources.json`.

Note: parsing an ~895 MB file in pure Python is slow and memory-hungry
compared to a native tool like `osmium`; this is an accepted, documented
tradeoff of staying dependency-free (DEC-002), not an oversight.

## Why this is staged, not integrated

Integrating this into `scripts/generate_synthetic_addresses.py` would mean
regenerating `data/synthetic/train.json`/`val.json`/`test.json` with a new
street/landmark pool -- exactly the kind of dataset change that would
invalidate the ML lead's in-progress fine-tuning if done mid-flight (the
same reasoning already applied when ALM-009 was first deferred). This pass
therefore only produces the governed candidate tables; wiring them into the
generator and regenerating the synthetic corpus is a separate, later step,
to be done between training iterations, not during one.

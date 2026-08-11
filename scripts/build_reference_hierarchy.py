#!/usr/bin/env python3
"""Build the deterministic ALAMATIN hierarchy/postal-code reference.

The primary input is the CSV published by Open Data Jabar. Optional cross-check
files use the documented normalized CSV contract so Kemendagri, BPS SIG, and
manual Pos Indonesia observations can be compared without scraping.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from acquire_sources import load_catalog, source_by_id  # noqa: E402
from alamatin.reference_hierarchy import (  # noqa: E402
    ReferenceHierarchy,
    ReferenceRow,
    ReferenceValidationError,
    SourceReference,
    normalize_name,
    normalize_region_code,
)


PRIMARY_SOURCE_ID = "open_data_jabar_postal_2023"
PRIMARY_FIELDS = {
    "kode_kemendagri_provinsi",
    "nama_kemendagri_provinsi",
    "kode_kabupaten_kota",
    "nama_kabupaten_kota",
    "kemendagri_kode_kecamatan",
    "kemendagri_nama_kecamatan",
    "kemendagri_kode_desa_kelurahan",
    "kemendagri_nama_desa_kelurahan",
    "kode_pos",
    "tahun",
}
NORMALIZED_CROSSCHECK_FIELDS = {
    "source_id",
    "snapshot",
    "province_code",
    "province_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "village_code",
    "village_name",
    "postal_code",
    "evidence_url",
    "note",
}


class BuildError(ValueError):
    """Raised when an input cannot produce a valid canonical reference."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, required_fields: set[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(8192)
            stream.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(stream, dialect=dialect)
            fieldnames = set(reader.fieldnames or ())
            missing = required_fields - fieldnames
            if missing:
                raise BuildError(
                    f"{path} is missing columns: {', '.join(sorted(missing))}"
                )
            return [
                {key: (value or "").strip() for key, value in row.items() if key}
                for row in reader
            ]
    except FileNotFoundError as error:
        raise BuildError(f"input file not found: {path}") from error


def _source_snapshot(catalog: Mapping[str, Any], source_id: str) -> str:
    return str(source_by_id(dict(catalog), source_id)["snapshot"])


def _exception(
    *,
    kind: str,
    village_code: str,
    field: str,
    values: Mapping[str, str],
    note: str,
    evidence_url: str = "",
) -> dict[str, Any]:
    identity = json.dumps(
        [kind, village_code, field, sorted(values.items())],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    result: dict[str, Any] = {
        "exception_id": f"REF-{hashlib.sha256(identity.encode()).hexdigest()[:12].upper()}",
        "kind": kind,
        "status": "documented",
        "village_code": village_code,
        "field": field,
        "values": dict(sorted(values.items())),
        "note": note,
    }
    if evidence_url:
        result["evidence_url"] = evidence_url
    return result


def _aliases(canonical: str, alternatives: Iterable[str]) -> tuple[str, ...]:
    canonical_key = normalize_name(canonical)
    return tuple(
        sorted(
            {
                value.strip()
                for value in alternatives
                if value.strip() and normalize_name(value) != canonical_key
            }
        )
    )


def _primary_entries(
    path: Path, catalog: Mapping[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    rows = _read_csv(path, PRIMARY_FIELDS)
    snapshot = _source_snapshot(catalog, PRIMARY_SOURCE_ID)
    sha256 = file_sha256(path)
    entries: dict[str, dict[str, Any]] = {}
    exceptions: list[dict[str, Any]] = []

    for line_number, raw in enumerate(rows, start=2):
        province_name = raw["nama_kemendagri_provinsi"]
        try:
            province_code = normalize_region_code(
                raw["kode_kemendagri_provinsi"], "province"
            )
            if province_code != "32":
                continue
            if normalize_name(province_name) != "jawa barat":
                raise BuildError(
                    f"{path}:{line_number}: province code 32 has unexpected name "
                    f"{province_name!r}"
                )
            district_code = normalize_region_code(
                raw["kemendagri_kode_kecamatan"], "district"
            )
            codes = {
                "province": province_code,
                # The portal labels kode_kabupaten_kota as BPS. Derive the
                # canonical Kemendagri parent from its district code instead.
                "city": normalize_region_code(
                    district_code.replace(".", "")[:4], "city"
                ),
                "district": district_code,
                "village": normalize_region_code(
                    raw["kemendagri_kode_desa_kelurahan"], "village"
                ),
            }
            bps_city_code = normalize_region_code(
                raw["kode_kabupaten_kota"], "city"
            )
        except ReferenceValidationError as error:
            raise BuildError(f"{path}:{line_number}: {error}") from error
        postal_code = raw["kode_pos"]
        if len(postal_code) != 5 or not postal_code.isdigit():
            raise BuildError(
                f"{path}:{line_number}: invalid postal code {postal_code!r}"
            )
        names = {
            "province": province_name,
            "city": raw["nama_kabupaten_kota"],
            "district": raw["kemendagri_nama_kecamatan"],
            "village": raw["kemendagri_nama_desa_kelurahan"],
        }
        if any(not value for value in names.values()):
            raise BuildError(f"{path}:{line_number}: hierarchy names may not be empty")

        village_code = codes["village"]
        if bps_city_code != codes["city"]:
            exceptions.append(
                _exception(
                    kind="hierarchy_code_conflict",
                    village_code=village_code,
                    field="city_code",
                    values={"BPS": bps_city_code, "Kemendagri": codes["city"]},
                    note=(
                        "Kemendagri city parent is derived from the district code; "
                        "the differing BPS code is retained in this exception."
                    ),
                )
            )
        current = entries.get(village_code)
        if current is None:
            current = {
                "codes": codes,
                "names": names,
                "aliases": defaultdict(set),
                "postal_codes": set(),
                "sources": {
                    SourceReference(PRIMARY_SOURCE_ID, snapshot, sha256),
                },
            }
            entries[village_code] = current
        elif current["codes"] != codes or current["names"] != names:
            raise BuildError(
                f"{path}:{line_number}: primary source gives conflicting hierarchy "
                f"for {village_code}; resolve it explicitly before publishing"
            )
        if current["postal_codes"] and postal_code not in current["postal_codes"]:
            exceptions.append(
                _exception(
                    kind="postal_code_conflict",
                    village_code=village_code,
                    field="postal_code",
                    values={
                        PRIMARY_SOURCE_ID: ",".join(sorted(current["postal_codes"])),
                        f"{PRIMARY_SOURCE_ID}:row-{line_number}": postal_code,
                    },
                    note="All primary-source postal codes are retained; validator must not guess.",
                )
            )
        current["postal_codes"].add(postal_code)

        bps_pairs = {
            "province": raw.get("nama_bps_provinsi", ""),
            "district": raw.get("bps_nama_kecamatan", ""),
            "village": raw.get("bps_nama_desa_kelurahan", ""),
        }
        for level, bps_name in bps_pairs.items():
            if bps_name and normalize_name(bps_name) != normalize_name(names[level]):
                current["aliases"][level].add(bps_name)
                exceptions.append(
                    _exception(
                        kind="name_difference",
                        village_code=village_code,
                        field=f"{level}_name",
                        values={"BPS": bps_name, "Kemendagri": names[level]},
                        note=(
                            "Kemendagri name is canonical; BPS spelling is retained as an alias."
                        ),
                    )
                )

    if not entries:
        raise BuildError("primary input contains no Jawa Barat rows")
    return entries, exceptions, {
        "source_id": PRIMARY_SOURCE_ID,
        "snapshot": snapshot,
        "artifact_sha256": sha256,
        "path": path.name,
    }


def _apply_crosscheck(
    entries: dict[str, dict[str, Any]],
    path: Path,
    catalog: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows = _read_csv(path, NORMALIZED_CROSSCHECK_FIELDS)
    exceptions: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, str]] = set()
    sha256 = file_sha256(path)
    for line_number, raw in enumerate(rows, start=2):
        source_id = raw["source_id"]
        try:
            source = source_by_id(dict(catalog), source_id)
        except ValueError as error:
            raise BuildError(f"{path}:{line_number}: {error}") from error
        if source["decision"] == "reject":
            raise BuildError(
                f"{path}:{line_number}: rejected source {source_id} cannot be used"
            )
        snapshot = raw["snapshot"]
        if not snapshot:
            raise BuildError(f"{path}:{line_number}: snapshot is required")
        seen_sources.add((source_id, snapshot))
        try:
            village_code = normalize_region_code(raw["village_code"], "village")
        except ReferenceValidationError as error:
            raise BuildError(f"{path}:{line_number}: {error}") from error
        primary = entries.get(village_code)
        if primary is None:
            exceptions.append(
                _exception(
                    kind="missing_primary_row",
                    village_code=village_code,
                    field="village_code",
                    values={source_id: village_code, PRIMARY_SOURCE_ID: "missing"},
                    note=raw.get("note") or "Cross-check row has no primary-source match.",
                    evidence_url=raw.get("evidence_url", ""),
                )
            )
            continue

        comparisons = (
            ("province", "province_code", "province_name"),
            ("city", "city_code", "city_name"),
            ("district", "district_code", "district_name"),
            ("village", "village_code", "village_name"),
        )
        for level, code_field, name_field in comparisons:
            try:
                cross_code = normalize_region_code(raw[code_field], level)
            except ReferenceValidationError as error:
                raise BuildError(f"{path}:{line_number}: {error}") from error
            canonical_code = primary["codes"][level]
            if cross_code != canonical_code:
                exceptions.append(
                    _exception(
                        kind="hierarchy_code_conflict",
                        village_code=village_code,
                        field=code_field,
                        values={PRIMARY_SOURCE_ID: canonical_code, source_id: cross_code},
                        note=raw.get("note") or "Primary value retained pending adjudication.",
                        evidence_url=raw.get("evidence_url", ""),
                    )
                )
            cross_name = raw[name_field]
            canonical_name = primary["names"][level]
            if cross_name and normalize_name(cross_name) != normalize_name(canonical_name):
                if source["decision"] == "use":
                    primary["aliases"][level].add(cross_name)
                    difference_note = "Cross-check spelling retained as an alias."
                else:
                    difference_note = (
                        "Held-source spelling recorded as evidence only; no alias promoted."
                    )
                exceptions.append(
                    _exception(
                        kind="name_difference",
                        village_code=village_code,
                        field=name_field,
                        values={PRIMARY_SOURCE_ID: canonical_name, source_id: cross_name},
                        note=raw.get("note") or difference_note,
                        evidence_url=raw.get("evidence_url", ""),
                    )
                )
        cross_postal = raw["postal_code"]
        if cross_postal and cross_postal not in primary["postal_codes"]:
            exceptions.append(
                _exception(
                    kind="postal_code_conflict",
                    village_code=village_code,
                    field="postal_code",
                    values={
                        PRIMARY_SOURCE_ID: ",".join(sorted(primary["postal_codes"])),
                        source_id: cross_postal,
                    },
                    note=(
                        raw.get("note")
                        or "Cross-check postal code recorded as evidence, not silently promoted."
                    ),
                    evidence_url=raw.get("evidence_url", ""),
                )
            )
        if source["decision"] == "use":
            primary["sources"].add(SourceReference(source_id, snapshot, sha256))

    sources_label = ",".join(
        f"{source_id}@{snapshot}" for source_id, snapshot in sorted(seen_sources)
    )
    return exceptions, {
        "sources": sources_label,
        "artifact_sha256": sha256,
        "path": path.name,
    }


def build_reference(
    primary_path: Path,
    crosscheck_paths: Iterable[Path],
    catalog_path: Path,
) -> tuple[ReferenceHierarchy, dict[str, Any], list[dict[str, Any]]]:
    catalog = load_catalog(catalog_path)
    primary_source = source_by_id(catalog, PRIMARY_SOURCE_ID)
    if primary_source["decision"] != "use":
        raise BuildError(f"{PRIMARY_SOURCE_ID} is not approved for use")
    entries, exceptions, primary_artifact = _primary_entries(primary_path, catalog)
    inputs: list[dict[str, str]] = [primary_artifact]
    for path in crosscheck_paths:
        found, artifact = _apply_crosscheck(entries, path, catalog)
        exceptions.extend(found)
        inputs.append(artifact)

    rows = []
    for village_code in sorted(entries):
        entry = entries[village_code]
        rows.append(
            ReferenceRow(
                province_code=entry["codes"]["province"],
                province_name=entry["names"]["province"],
                province_aliases=_aliases(
                    entry["names"]["province"], entry["aliases"]["province"]
                ),
                city_code=entry["codes"]["city"],
                city_name=entry["names"]["city"],
                city_aliases=_aliases(entry["names"]["city"], entry["aliases"]["city"]),
                district_code=entry["codes"]["district"],
                district_name=entry["names"]["district"],
                district_aliases=_aliases(
                    entry["names"]["district"], entry["aliases"]["district"]
                ),
                village_code=village_code,
                village_name=entry["names"]["village"],
                village_aliases=_aliases(
                    entry["names"]["village"], entry["aliases"]["village"]
                ),
                postal_codes=tuple(sorted(entry["postal_codes"])),
                sources=tuple(
                    sorted(
                        entry["sources"],
                        key=lambda item: (item.source_id, item.snapshot),
                    )
                ),
            )
        )
    hierarchy = ReferenceHierarchy(rows)
    unique_exceptions = {
        item["exception_id"]: item
        for item in sorted(exceptions, key=lambda item: item["exception_id"])
    }
    build = {
        "catalog_version": catalog["catalog_version"],
        "scope": "Jawa Barat",
        "inputs": inputs,
    }
    return hierarchy, build, list(unique_exceptions.values())


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open-data-jabar", type=Path, required=True)
    parser.add_argument("--crosscheck", type=Path, action="append", default=[])
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "sources.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "reference-hierarchy.json",
    )
    parser.add_argument(
        "--exceptions-output",
        type=Path,
        default=ROOT / "data" / "processed" / "reference-exceptions.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        hierarchy, build, exceptions = build_reference(
            args.open_data_jabar, args.crosscheck, args.catalog
        )
        document = hierarchy.to_document(build=build, exceptions=exceptions)
        _write_json(args.output, document)
        _write_json(
            args.exceptions_output,
            {
                "schema_version": "1.0.0",
                "build": build,
                "exceptions": exceptions,
            },
        )
    except (BuildError, ReferenceValidationError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"built {len(hierarchy.rows)} rows with {len(exceptions)} documented exceptions"
    )
    print(args.output)
    print(args.exceptions_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

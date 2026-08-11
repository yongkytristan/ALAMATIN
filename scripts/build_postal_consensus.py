#!/usr/bin/env python3
"""Build a consensus-only Jawa Barat postal candidate with explicit lineage.

Administrative code resolutions are applied before matching the three source
views. A postal code is accepted only when Diskominfo, Open Data Jabar, and the
Kodepos.dev audit all provide the same valid five-digit value. Every other row
remains blank and review-required; no majority vote or silent overwrite occurs.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from build_source_review_workbook import (
    DEFAULT_DISKOMINFO,
    DEFAULT_ODJ,
    PLACEHOLDER_CODE,
    canonical_village_code,
    clean_postal,
    file_sha256,
    normalize_name,
    read_csv,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API = ROOT / "data" / "interim" / "kodepos-dev-jabar.csv"
DEFAULT_RESOLUTIONS = ROOT / "data" / "kemendagri_code_resolutions.json"
DEFAULT_ALL_OUTPUT = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-candidate.csv"
)
DEFAULT_ACCEPTED_OUTPUT = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-accepted.csv"
)
DEFAULT_CORROBORATED_OUTPUT = (
    ROOT / "data" / "processed" / "jabar-postal-corroborated-candidates.csv"
)
DEFAULT_REVIEW_OUTPUT = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-review-required.csv"
)
DEFAULT_UNRESOLVED_OUTPUT = (
    ROOT / "data" / "processed" / "jabar-postal-unresolved.csv"
)
DEFAULT_SUMMARY = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-summary.json"
)
SOURCE_IDS = (
    "diskominfo_jabar_village_2024_unreviewed",
    "open_data_jabar_postal_2023",
    "kodepos_dev_rest_api",
)
OUTPUT_FIELDS = (
    "village_code",
    "province_code",
    "province_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "village_name",
    "postal_code",
    "postal_code_candidate",
    "candidate_status",
    "candidate_sources",
    "postal_code_diskominfo",
    "postal_code_open_data_jabar",
    "postal_code_kodepos_dev",
    "postal_candidates",
    "verification_status",
    "confidence",
    "review_required",
    "selected_reason",
    "administrative_resolution_applied",
    "former_village_code",
    "source_village_codes",
    "source_ids",
    "source_rows",
    "snapshot",
)


class ConsensusBuildError(ValueError):
    """Raised when inputs cannot produce a trustworthy consensus artifact."""


def _postal_classification(
    postals: tuple[str, str, str],
) -> tuple[str, str, str, str, str, str]:
    """Return accepted, candidate, status, confidence, sources, and reason."""

    diskominfo, open_data_jabar, kodepos_dev = postals
    if all(postals) and len(set(postals)) == 1:
        return (
            diskominfo,
            "",
            "verified_consensus",
            "high",
            "",
            "All three source values are the same valid five-digit postal code.",
        )
    if kodepos_dev and kodepos_dev == open_data_jabar and kodepos_dev != diskominfo:
        return (
            "",
            kodepos_dev,
            "corroborated_candidate",
            "medium",
            "open_data_jabar_postal_2023;kodepos_dev_rest_api",
            "Kodepos.dev corroborates Open Data Jabar; candidate is not accepted as final.",
        )
    if kodepos_dev and kodepos_dev == diskominfo and kodepos_dev != open_data_jabar:
        return (
            "",
            kodepos_dev,
            "corroborated_candidate",
            "medium",
            "diskominfo_jabar_village_2024_unreviewed;kodepos_dev_rest_api",
            "Kodepos.dev corroborates Diskominfo; candidate is not accepted as final.",
        )
    return (
        "",
        "",
        "review_required",
        "unresolved",
        "",
        "No automatic selection: Kodepos.dev does not corroborate exactly one local source.",
    )


def load_resolutions(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ConsensusBuildError(f"invalid resolution document: {path}") from error
    if document.get("source_id") != "kemendagri_wilayah_2025":
        raise ConsensusBuildError("resolution source must be kemendagri_wilayah_2025")
    mapping: dict[str, dict[str, Any]] = {}
    current_codes: set[str] = set()
    for item in document.get("resolutions", []):
        former = canonical_village_code(str(item.get("former_village_code", "")))
        current = canonical_village_code(str(item.get("current_village_code", "")))
        if not former or not current or former == current:
            raise ConsensusBuildError("resolution codes must be valid and different")
        if former in mapping or current in current_codes:
            raise ConsensusBuildError("resolution codes must be unique")
        if not str(item.get("village_name", "")).strip():
            raise ConsensusBuildError("resolution village name is required")
        mapping[former] = dict(item)
        current_codes.add(current)
    return mapping, document


def _apply_resolution(
    code: str,
    village_name: str,
    resolutions: Mapping[str, Mapping[str, Any]],
) -> tuple[str, Mapping[str, Any] | None]:
    resolution = resolutions.get(code)
    if resolution is None:
        return code, None
    if normalize_name(village_name) != normalize_name(
        str(resolution["village_name"])
    ):
        raise ConsensusBuildError(
            f"resolution name mismatch for {code}: {village_name!r}"
        )
    return str(resolution["current_village_code"]), resolution


def _index_source(
    rows: Sequence[Mapping[str, str]],
    *,
    code_field: str,
    name_field: str,
    resolutions: Mapping[str, Mapping[str, Any]],
    include: Callable[[Mapping[str, str]], bool] | None = None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for source_row, row in enumerate(rows, start=2):
        if include is not None and not include(row):
            continue
        original_code = canonical_village_code(row.get(code_field, ""))
        if not original_code:
            continue
        canonical_code, resolution = _apply_resolution(
            original_code, row.get(name_field, ""), resolutions
        )
        if canonical_code in result:
            raise ConsensusBuildError(
                f"duplicate canonical village code after resolution: {canonical_code}"
            )
        result[canonical_code] = {
            "row": dict(row),
            "source_row": source_row,
            "original_code": original_code,
            "resolution": resolution,
        }
    return result


def build_consensus(
    diskominfo_rows: Sequence[Mapping[str, str]],
    odj_rows: Sequence[Mapping[str, str]],
    api_rows: Sequence[Mapping[str, str]],
    resolutions: Mapping[str, Mapping[str, Any]],
    *,
    snapshot: str,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    diskominfo = _index_source(
        diskominfo_rows,
        code_field="kemendagri_kelurahan_kode",
        name_field="kemendagri_kelurahan_nama",
        resolutions=resolutions,
        include=lambda row: row.get("kemendagri_kelurahan_kode", "").strip()
        != PLACEHOLDER_CODE,
    )
    odj = _index_source(
        odj_rows,
        code_field="kemendagri_kode_desa_kelurahan",
        name_field="kemendagri_nama_desa_kelurahan",
        resolutions=resolutions,
        include=lambda row: row.get("kode_kemendagri_provinsi", "").strip() == "32",
    )
    api = _index_source(
        api_rows,
        code_field="village_code",
        name_field="village_name",
        resolutions=resolutions,
        include=lambda row: row.get("province_code", "").strip() == "32",
    )
    code_sets = {tuple(sorted(source)) for source in (diskominfo, odj, api)}
    if len(code_sets) != 1:
        raise ConsensusBuildError(
            "source village-code sets still differ after administrative resolutions"
        )
    result: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for code in sorted(diskominfo):
        new_entry = diskominfo[code]
        old_entry = odj[code]
        api_entry = api[code]
        new = new_entry["row"]
        old = old_entry["row"]
        api_row = api_entry["row"]
        postals = (
            clean_postal(new.get("kode_pos", "")),
            clean_postal(old.get("kode_pos", "")),
            clean_postal(api_row.get("postal_code", "")),
        )
        (
            accepted_postal,
            candidate_postal,
            status,
            confidence,
            candidate_sources,
            selected_reason,
        ) = _postal_classification(postals)
        accepted = status == "verified_consensus"
        counts[status] += 1
        resolution = (
            new_entry["resolution"]
            or old_entry["resolution"]
            or api_entry["resolution"]
        )
        province_code, city_code, district_code = (
            code.split(".")[0],
            ".".join(code.split(".")[:2]),
            ".".join(code.split(".")[:3]),
        )
        village_name = (
            str(resolution["village_name"])
            if resolution
            else new.get("kemendagri_kelurahan_nama", "").strip()
        )
        district_name = (
            str(resolution["current_district_name"])
            if resolution
            else new.get("kemendagri_kecamatan_nama", "").strip()
        )
        city_name = (
            str(resolution["city_name"])
            if resolution
            else new.get("kemendagri_kota_nama", "").strip()
        )
        former_code = str(resolution["former_village_code"]) if resolution else ""
        result.append(
            {
                "village_code": code,
                "province_code": province_code,
                "province_name": "JAWA BARAT",
                "city_code": city_code,
                "city_name": city_name,
                "district_code": district_code,
                "district_name": district_name,
                "village_name": village_name,
                "postal_code": accepted_postal,
                "postal_code_candidate": candidate_postal,
                "candidate_status": (
                    "corroborated_by_two_sources" if candidate_postal else ""
                ),
                "candidate_sources": candidate_sources,
                "postal_code_diskominfo": postals[0],
                "postal_code_open_data_jabar": postals[1],
                "postal_code_kodepos_dev": postals[2],
                "postal_candidates": ";".join(sorted(set(filter(None, postals)))),
                "verification_status": status,
                "confidence": confidence,
                "review_required": "no" if accepted else "yes",
                "selected_reason": selected_reason,
                "administrative_resolution_applied": "yes" if resolution else "no",
                "former_village_code": former_code,
                "source_village_codes": ";".join(
                    (
                        f"diskominfo:{new_entry['original_code']}",
                        f"open_data_jabar:{old_entry['original_code']}",
                        f"kodepos_dev:{api_entry['original_code']}",
                    )
                ),
                "source_ids": ";".join(SOURCE_IDS),
                "source_rows": ";".join(
                    (
                        f"diskominfo:{new_entry['source_row']}",
                        f"open_data_jabar:{old_entry['source_row']}",
                        f"kodepos_dev:{api_entry['source_row']}",
                    )
                ),
                "snapshot": snapshot,
            }
        )
    return result, dict(sorted(counts.items()))


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diskominfo", type=Path, default=DEFAULT_DISKOMINFO)
    parser.add_argument("--odj", type=Path, default=DEFAULT_ODJ)
    parser.add_argument("--api", type=Path, default=DEFAULT_API)
    parser.add_argument("--resolutions", type=Path, default=DEFAULT_RESOLUTIONS)
    parser.add_argument("--snapshot", default="2026-08-11")
    parser.add_argument("--output", type=Path, default=DEFAULT_ALL_OUTPUT)
    parser.add_argument("--accepted-output", type=Path, default=DEFAULT_ACCEPTED_OUTPUT)
    parser.add_argument(
        "--corroborated-output", type=Path, default=DEFAULT_CORROBORATED_OUTPUT
    )
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW_OUTPUT)
    parser.add_argument("--unresolved-output", type=Path, default=DEFAULT_UNRESOLVED_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        resolutions, resolution_document = load_resolutions(args.resolutions)
        _, diskominfo = read_csv(args.diskominfo)
        _, odj = read_csv(args.odj)
        _, api = read_csv(args.api)
        rows, counts = build_consensus(
            diskominfo, odj, api, resolutions, snapshot=args.snapshot
        )
        accepted = [row for row in rows if row["verification_status"] == "verified_consensus"]
        corroborated = [
            row for row in rows if row["verification_status"] == "corroborated_candidate"
        ]
        review = [row for row in rows if row["review_required"] == "yes"]
        unresolved = [
            row for row in rows if row["verification_status"] == "review_required"
        ]
        _write_csv(args.output, rows)
        _write_csv(args.accepted_output, accepted)
        _write_csv(args.corroborated_output, corroborated)
        _write_csv(args.review_output, review)
        _write_csv(args.unresolved_output, unresolved)
        _write_json(
            args.summary,
            {
                "administrative_resolutions_applied": len(resolutions),
                "counts": counts,
                "input_sha256": {
                    "api": file_sha256(args.api),
                    "diskominfo": file_sha256(args.diskominfo),
                    "open_data_jabar": file_sha256(args.odj),
                    "resolutions": file_sha256(args.resolutions),
                },
                "output_sha256": {
                    "accepted": file_sha256(args.accepted_output),
                    "all": file_sha256(args.output),
                    "corroborated_candidates": file_sha256(args.corroborated_output),
                    "review_required": file_sha256(args.review_output),
                    "unresolved": file_sha256(args.unresolved_output),
                },
                "resolution_source": {
                    "source_id": resolution_document["source_id"],
                    "snapshot": resolution_document["snapshot"],
                    "artifacts": resolution_document["artifacts"],
                },
                "schema_version": "1.0.0",
                "scope": "Jawa Barat",
                "snapshot": args.snapshot,
                "total_rows": len(rows),
            },
        )
    except (ConsensusBuildError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(args.summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

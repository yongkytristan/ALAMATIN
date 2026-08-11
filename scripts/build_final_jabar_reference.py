#!/usr/bin/env python3
"""Build the governed final Jawa Barat hierarchy/postal reference package.

All administrative rows remain present, but only three-source postal consensus
is operationally usable. Two-source values stay candidates and all remaining
values stay unresolved. Selected Pos Indonesia observations are attached as
held evidence and never promoted automatically.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.reference_hierarchy import (  # noqa: E402
    ReferenceHierarchy,
    ReferenceRow,
    SourceReference,
)
from build_source_review_workbook import (  # noqa: E402
    DEFAULT_DISKOMINFO,
    DEFAULT_ODJ,
    canonical_village_code,
    file_sha256,
    normalize_name,
    read_csv,
)


DEFAULT_CONSENSUS = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-candidate.csv"
)
DEFAULT_CONSENSUS_SUMMARY = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-summary.json"
)
DEFAULT_OBSERVATIONS = ROOT / "data" / "interim" / "manual-pos-conflicts.csv"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "jabar-reference-v1.csv"
DEFAULT_VERIFIED_LOOKUP = (
    ROOT / "data" / "processed" / "jabar-reference-v1-verified.json"
)
DEFAULT_EXCEPTIONS = (
    ROOT / "data" / "processed" / "jabar-reference-v1-exceptions.csv"
)
DEFAULT_SUMMARY = ROOT / "data" / "processed" / "jabar-reference-v1-summary.json"

FINAL_FIELDS = (
    "record_id",
    "province_code",
    "province_name",
    "province_aliases",
    "city_code",
    "city_name",
    "city_aliases",
    "district_code",
    "district_name",
    "district_aliases",
    "village_code",
    "village_name",
    "village_aliases",
    "former_village_code",
    "bps_province_codes",
    "bps_city_codes",
    "bps_district_codes",
    "bps_village_codes",
    "postal_code",
    "postal_code_candidate",
    "postal_verification_status",
    "postal_confidence",
    "operational_status",
    "review_required",
    "postal_candidates",
    "postal_code_diskominfo",
    "postal_code_open_data_jabar",
    "postal_code_kodepos_dev",
    "postal_code_pos_indonesia_observed",
    "pos_indonesia_match",
    "pos_indonesia_checked_at",
    "pos_indonesia_evidence_url",
    "pos_indonesia_note",
    "administrative_resolution_applied",
    "source_ids",
    "source_village_codes",
    "source_rows",
    "snapshot",
    "use_policy",
)
EXCEPTION_FIELDS = (
    "exception_id",
    "village_code",
    "village_name",
    "district_name",
    "city_name",
    "exception_type",
    "verification_status",
    "postal_code_candidate",
    "postal_candidates",
    "pos_indonesia_observed",
    "review_required",
    "reason",
)


class FinalReferenceError(ValueError):
    """Raised when inputs cannot produce a safe final reference package."""


def _parse_source_codes(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in value.split(";"):
        if not item:
            continue
        try:
            source, code = item.split(":", 1)
        except ValueError as error:
            raise FinalReferenceError(f"invalid source_village_codes item: {item}") from error
        result[source] = code
    return result


def _source_index(
    rows: Sequence[Mapping[str, str]], code_field: str
) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for row in rows:
        code = canonical_village_code(row.get(code_field, ""))
        if not code or code == "00.00.00.0000":
            continue
        if code in result:
            raise FinalReferenceError(f"duplicate source village code: {code}")
        result[code] = row
    return result


def _aliases(canonical: str, values: Sequence[str]) -> str:
    canonical_key = normalize_name(canonical)
    return ";".join(
        sorted(
            {
                value.strip()
                for value in values
                if value.strip() and normalize_name(value) != canonical_key
            }
        )
    )


def _bps_code(value: str) -> str:
    cleaned = value.strip()
    if cleaned.endswith(".0"):
        cleaned = cleaned[:-2]
    return cleaned if cleaned.isdigit() else ""


def _codes(values: Sequence[str]) -> str:
    return ";".join(sorted({_bps_code(value) for value in values if _bps_code(value)}))


def _operational_status(status: str) -> tuple[str, str]:
    if status == "verified_consensus":
        return "usable_verified", "Use for exact postal validation."
    if status == "corroborated_candidate":
        return "candidate_review_only", "Do not auto-correct; request review or more evidence."
    if status == "review_required":
        return "unresolved_do_not_guess", "Do not select a postal code automatically."
    raise FinalReferenceError(f"unknown verification status: {status}")


def _observation_index(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for row in rows:
        if row.get("source_id") != "pos_indonesia_postcode_search":
            raise FinalReferenceError(
                f"unexpected manual source: {row.get('source_id', '')}"
            )
        code = canonical_village_code(row.get("village_code", ""))
        postal = row.get("postal_code", "").strip()
        if not code or len(postal) != 5 or not postal.isdigit():
            raise FinalReferenceError(f"invalid manual observation for {code}")
        if code in result:
            raise FinalReferenceError(f"duplicate manual observation for {code}")
        result[code] = row
    return result


def _pos_match(row: Mapping[str, str], postal: str) -> str:
    if not postal:
        return ""
    matches = [
        label
        for label, field in (
            ("diskominfo", "postal_code_diskominfo"),
            ("open_data_jabar", "postal_code_open_data_jabar"),
            ("kodepos_dev", "postal_code_kodepos_dev"),
        )
        if row.get(field) == postal
    ]
    return ";".join(matches) if matches else "new_value"


def build_final_reference(
    consensus_rows: Sequence[Mapping[str, str]],
    odj_rows: Sequence[Mapping[str, str]],
    diskominfo_rows: Sequence[Mapping[str, str]],
    observation_rows: Sequence[Mapping[str, str]],
    *,
    source_hashes: Mapping[str, str],
) -> tuple[
    list[dict[str, str]], ReferenceHierarchy, list[dict[str, str]], dict[str, Any]
]:
    odj = _source_index(odj_rows, "kemendagri_kode_desa_kelurahan")
    diskominfo = _source_index(diskominfo_rows, "kemendagri_kelurahan_kode")
    observations = _observation_index(observation_rows)
    final_rows: list[dict[str, str]] = []
    exceptions: list[dict[str, str]] = []
    verified_lookup_rows: list[ReferenceRow] = []
    seen_codes: set[str] = set()
    parent_names: dict[tuple[str, str], str] = {}
    status_counts: Counter[str] = Counter()
    operational_counts: Counter[str] = Counter()

    parent_counts: dict[str, dict[str, Counter[str]]] = {
        "city": {},
        "district": {},
    }
    authoritative_parent_names: dict[tuple[str, str], str] = {}
    for row in consensus_rows:
        for level in ("city", "district"):
            code = row[f"{level}_code"]
            name = row[f"{level}_name"]
            parent_counts[level].setdefault(code, Counter())[name] += 1
            if row.get("administrative_resolution_applied") == "yes":
                key = (level, code)
                previous = authoritative_parent_names.setdefault(key, name)
                if previous != name:
                    raise FinalReferenceError(
                        f"conflicting authoritative {level} names for {code}"
                    )
    canonical_parent_names: dict[tuple[str, str], str] = {}
    for level, by_code in parent_counts.items():
        for code, counts in by_code.items():
            canonical_parent_names[(level, code)] = authoritative_parent_names.get(
                (level, code),
                sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0],
            )

    for consensus in sorted(consensus_rows, key=lambda row: row["village_code"]):
        village_code = consensus["village_code"]
        if village_code in seen_codes:
            raise FinalReferenceError(f"duplicate final village code: {village_code}")
        seen_codes.add(village_code)
        if not village_code.startswith(consensus["district_code"] + "."):
            raise FinalReferenceError(f"invalid village parent for {village_code}")
        if not consensus["district_code"].startswith(consensus["city_code"] + "."):
            raise FinalReferenceError(f"invalid district parent for {village_code}")
        for level in ("city", "district"):
            key = (level, consensus[f"{level}_code"])
            name = canonical_parent_names[key]
            previous = parent_names.setdefault(key, name)
            if previous != name:
                raise FinalReferenceError(f"inconsistent {level} name for {key[1]}")

        source_codes = _parse_source_codes(consensus["source_village_codes"])
        try:
            odj_row = odj[canonical_village_code(source_codes["open_data_jabar"])]
            diskominfo_row = diskominfo[
                canonical_village_code(source_codes["diskominfo"])
            ]
        except KeyError as error:
            raise FinalReferenceError(
                f"missing raw source row for {village_code}: {error}"
            ) from error

        aliases = {
            "province": _aliases(
                consensus["province_name"],
                [
                    odj_row.get("nama_bps_provinsi", ""),
                    odj_row.get("nama_kemendagri_provinsi", ""),
                    diskominfo_row.get("bps_provinsi_nama", ""),
                    diskominfo_row.get("kemendagri_provinsi_nama", ""),
                ],
            ),
            "city": _aliases(
                canonical_parent_names[("city", consensus["city_code"])],
                [
                    consensus["city_name"],
                    odj_row.get("nama_kabupaten_kota", ""),
                    diskominfo_row.get("bps_kota_nama", ""),
                    diskominfo_row.get("kemendagri_kota_nama", ""),
                ],
            ),
            "district": _aliases(
                canonical_parent_names[("district", consensus["district_code"])],
                [
                    consensus["district_name"],
                    odj_row.get("bps_nama_kecamatan", ""),
                    odj_row.get("kemendagri_nama_kecamatan", ""),
                    diskominfo_row.get("bps_kecamatan_nama", ""),
                    diskominfo_row.get("kemendagri_kecamatan_nama", ""),
                ],
            ),
            "village": _aliases(
                consensus["village_name"],
                [
                    odj_row.get("bps_nama_desa_kelurahan", ""),
                    odj_row.get("kemendagri_nama_desa_kelurahan", ""),
                    diskominfo_row.get("bps_kelurahan_nama", ""),
                    diskominfo_row.get("kemendagri_kelurahan_nama", ""),
                ],
            ),
        }
        status = consensus["verification_status"]
        operational_status, use_policy = _operational_status(status)
        postal = consensus["postal_code"]
        candidate = consensus["postal_code_candidate"]
        if status == "verified_consensus" and not postal:
            raise FinalReferenceError(f"verified row lacks postal code: {village_code}")
        if status != "verified_consensus" and postal:
            raise FinalReferenceError(f"non-verified row has accepted postal: {village_code}")
        if status == "corroborated_candidate" and not candidate:
            raise FinalReferenceError(f"candidate row lacks candidate: {village_code}")

        observation = observations.get(village_code)
        observed_postal = observation.get("postal_code", "") if observation else ""
        source_ids = consensus["source_ids"].split(";")
        if observation:
            source_ids.append("pos_indonesia_postcode_search")
        if consensus["administrative_resolution_applied"] == "yes":
            source_ids.append("kemendagri_wilayah_2025")

        final = {
            "record_id": "ID-" + village_code.replace(".", ""),
            "province_code": consensus["province_code"],
            "province_name": consensus["province_name"],
            "province_aliases": aliases["province"],
            "city_code": consensus["city_code"],
            "city_name": canonical_parent_names[("city", consensus["city_code"])],
            "city_aliases": aliases["city"],
            "district_code": consensus["district_code"],
            "district_name": canonical_parent_names[
                ("district", consensus["district_code"])
            ],
            "district_aliases": aliases["district"],
            "village_code": village_code,
            "village_name": consensus["village_name"],
            "village_aliases": aliases["village"],
            "former_village_code": consensus["former_village_code"],
            "bps_province_codes": _codes(
                [odj_row.get("kode_bps_provinsi", ""), diskominfo_row.get("bps_provinsi_kode", "")]
            ),
            "bps_city_codes": _codes(
                [odj_row.get("kode_kabupaten_kota", ""), diskominfo_row.get("bps_kota_kode", "")]
            ),
            "bps_district_codes": _codes(
                [odj_row.get("bps_kode_kecamatan", ""), diskominfo_row.get("bps_kecamatan_kode", "")]
            ),
            "bps_village_codes": _codes(
                [odj_row.get("bps_kode_desa_kelurahan", ""), diskominfo_row.get("bps_kelurahan_kode", "")]
            ),
            "postal_code": postal,
            "postal_code_candidate": candidate,
            "postal_verification_status": status,
            "postal_confidence": consensus["confidence"],
            "operational_status": operational_status,
            "review_required": consensus["review_required"],
            "postal_candidates": consensus["postal_candidates"],
            "postal_code_diskominfo": consensus["postal_code_diskominfo"],
            "postal_code_open_data_jabar": consensus["postal_code_open_data_jabar"],
            "postal_code_kodepos_dev": consensus["postal_code_kodepos_dev"],
            "postal_code_pos_indonesia_observed": observed_postal,
            "pos_indonesia_match": _pos_match(consensus, observed_postal),
            "pos_indonesia_checked_at": observation.get("snapshot", "") if observation else "",
            "pos_indonesia_evidence_url": observation.get("evidence_url", "") if observation else "",
            "pos_indonesia_note": observation.get("note", "") if observation else "",
            "administrative_resolution_applied": consensus[
                "administrative_resolution_applied"
            ],
            "source_ids": ";".join(sorted(set(source_ids))),
            "source_village_codes": consensus["source_village_codes"],
            "source_rows": consensus["source_rows"],
            "snapshot": consensus["snapshot"],
            "use_policy": use_policy,
        }
        final_rows.append(final)
        status_counts[status] += 1
        operational_counts[operational_status] += 1

        if status == "verified_consensus":
            source_refs = tuple(
                sorted(
                    (
                        SourceReference(
                            "diskominfo_jabar_village_2024_unreviewed",
                            consensus["snapshot"],
                            source_hashes.get("diskominfo"),
                        ),
                        SourceReference(
                            "kodepos_dev_rest_api",
                            consensus["snapshot"],
                            source_hashes.get("api"),
                        ),
                        SourceReference(
                            "open_data_jabar_postal_2023",
                            "data-year-2023",
                            source_hashes.get("open_data_jabar"),
                        ),
                    ),
                    key=lambda item: (item.source_id, item.snapshot),
                )
            )
            verified_lookup_rows.append(
                ReferenceRow(
                    province_code=final["province_code"],
                    province_name=final["province_name"],
                    province_aliases=tuple(filter(None, final["province_aliases"].split(";"))),
                    city_code=final["city_code"],
                    city_name=final["city_name"],
                    city_aliases=tuple(filter(None, final["city_aliases"].split(";"))),
                    district_code=final["district_code"],
                    district_name=final["district_name"],
                    district_aliases=tuple(filter(None, final["district_aliases"].split(";"))),
                    village_code=final["village_code"],
                    village_name=final["village_name"],
                    village_aliases=tuple(filter(None, final["village_aliases"].split(";"))),
                    postal_codes=(postal,),
                    sources=source_refs,
                )
            )
        else:
            exceptions.append(
                {
                    "exception_id": f"POSTAL-{village_code.replace('.', '')}",
                    "village_code": village_code,
                    "village_name": final["village_name"],
                    "district_name": final["district_name"],
                    "city_name": final["city_name"],
                    "exception_type": operational_status,
                    "verification_status": status,
                    "postal_code_candidate": candidate,
                    "postal_candidates": final["postal_candidates"],
                    "pos_indonesia_observed": observed_postal,
                    "review_required": "yes",
                    "reason": consensus["selected_reason"],
                }
            )

    unknown_observations = set(observations) - seen_codes
    if unknown_observations:
        raise FinalReferenceError(
            "manual observations lack final rows: "
            + ", ".join(sorted(unknown_observations))
        )
    hierarchy = ReferenceHierarchy(verified_lookup_rows)
    alias_rows = sum(
        any(row[field] for field in ("province_aliases", "city_aliases", "district_aliases", "village_aliases"))
        for row in final_rows
    )
    summary: dict[str, Any] = {
        "total_administrative_rows": len(final_rows),
        "verified_lookup_rows": len(verified_lookup_rows),
        "exception_rows": len(exceptions),
        "manual_pos_observation_rows": len(observations),
        "rows_with_aliases": alias_rows,
        "verification_status_counts": dict(sorted(status_counts.items())),
        "operational_status_counts": dict(sorted(operational_counts.items())),
        "parent_integrity": True,
        "duplicate_village_codes": 0,
        "scope": "Jawa Barat",
        "release_policy": (
            "Only usable_verified rows enter the postal lookup; candidate and "
            "unresolved rows remain in the full table and exception report."
        ),
    }
    return final_rows, hierarchy, exceptions, summary


def _write_csv(
    path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
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
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument(
        "--consensus-summary", type=Path, default=DEFAULT_CONSENSUS_SUMMARY
    )
    parser.add_argument("--odj", type=Path, default=DEFAULT_ODJ)
    parser.add_argument("--diskominfo", type=Path, default=DEFAULT_DISKOMINFO)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verified-lookup", type=Path, default=DEFAULT_VERIFIED_LOOKUP)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _, consensus = read_csv(args.consensus)
        _, odj = read_csv(args.odj)
        _, diskominfo = read_csv(args.diskominfo)
        _, observations = read_csv(args.observations)
        consensus_summary = json.loads(args.consensus_summary.read_text(encoding="utf-8"))
        source_hashes = consensus_summary.get("input_sha256", {})
        final_rows, hierarchy, exceptions, summary = build_final_reference(
            consensus,
            odj,
            diskominfo,
            observations,
            source_hashes=source_hashes,
        )
        _write_csv(args.output, FINAL_FIELDS, final_rows)
        _write_csv(args.exceptions, EXCEPTION_FIELDS, exceptions)
        lookup_document = hierarchy.to_document(
            build={
                "artifact_type": "verified_postal_lookup",
                "scope": "Jawa Barat",
                "policy": summary["release_policy"],
                "inputs": {
                    "consensus_sha256": file_sha256(args.consensus),
                    "manual_observations_sha256": file_sha256(args.observations),
                },
            }
        )
        _write_json(args.verified_lookup, lookup_document)
        _write_json(
            args.summary,
            {
                **summary,
                "input_sha256": {
                    "consensus": file_sha256(args.consensus),
                    "consensus_summary": file_sha256(args.consensus_summary),
                    "diskominfo": file_sha256(args.diskominfo),
                    "manual_observations": file_sha256(args.observations),
                    "open_data_jabar": file_sha256(args.odj),
                },
                "output_sha256": {
                    "exceptions": file_sha256(args.exceptions),
                    "full_csv": file_sha256(args.output),
                    "verified_lookup": file_sha256(args.verified_lookup),
                },
                "schema_version": "1.0.0",
            },
        )
    except (FinalReferenceError, OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(args.summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

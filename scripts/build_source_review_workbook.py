#!/usr/bin/env python3
"""Build a local Excel review workbook from the ALAMATIN source artifacts.

The workbook is a human-review artifact, not the canonical dataset. Raw sheets
preserve source values as text. Candidate and conflict sheets are deterministic
derived views and never overwrite source artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ODJ = (
    ROOT
    / "data"
    / "raw"
    / "open_data_jabar_postal_2023"
    / "static"
    / "download"
    / "dispusipda-kode_pos_kab_kota_indonesia_data.csv"
)
DEFAULT_DISKOMINFO = (
    ROOT / "diskominfo-od_kode_wilayah_dan_nama_wilayah_desa_kelurahan.csv"
)
DEFAULT_BPS1 = ROOT / "databps1.xls"
DEFAULT_BPS2 = ROOT / "databps2.xls"
DEFAULT_KEMENDAGRI = ROOT / "kemendagri-api.json"
DEFAULT_KODEPOS = ROOT / "data" / "interim" / "kodepos-dev-crosscheck.csv"
DEFAULT_CONSENSUS = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-candidate.csv"
)
DEFAULT_UNRESOLVED_GROUP_SUMMARY = (
    ROOT / "data" / "processed" / "jabar-postal-unresolved-group-summary.json"
)
DEFAULT_SPOTCHECK_SUMMARY = (
    ROOT / "data" / "processed" / "jabar-postal-pos-spotcheck-summary.json"
)
DEFAULT_FINAL_REFERENCE_SUMMARY = (
    ROOT / "data" / "processed" / "jabar-reference-v1-summary.json"
)
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "jabar-source-review.xlsx"
PLACEHOLDER_CODE = "00.00.00.0000"
ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
NON_ALNUM = re.compile(r"[^0-9a-z]+")


class WorkbookBuildError(ValueError):
    """Raised when a source cannot produce a trustworthy review workbook."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_dialect(path: Path) -> csv.Dialect:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(8192)
    except FileNotFoundError as error:
        raise WorkbookBuildError(f"source not found: {path}") from error
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    dialect = _csv_dialect(path)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, dialect=dialect)
        headers = list(reader.fieldnames or ())
        rows = [
            {key: (value or "") for key, value in row.items() if key is not None}
            for row in reader
        ]
    if not headers:
        raise WorkbookBuildError(f"CSV has no header: {path}")
    return headers, rows


def iter_csv_sheet(path: Path) -> Iterator[Sequence[str]]:
    dialect = _csv_dialect(path)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, dialect=dialect)
        yield from reader


def normalize_name(value: str) -> str:
    return NON_ALNUM.sub(" ", value.casefold()).strip()


def clean_postal(value: str) -> str:
    cleaned = value.strip()
    if cleaned.endswith(".0"):
        cleaned = cleaned[:-2]
    if len(cleaned) == 5 and cleaned.isdigit() and cleaned != "00000":
        return cleaned
    return ""


def canonical_village_code(value: str) -> str:
    digits = re.sub(r"\D", "", value.strip())
    if len(digits) != 10:
        return ""
    return f"{digits[:2]}.{digits[2:4]}.{digits[4:6]}.{digits[6:]}"


def parent_codes(village_code: str) -> tuple[str, str, str]:
    parts = village_code.split(".")
    if len(parts) != 4:
        return "", "", ""
    return parts[0], ".".join(parts[:2]), ".".join(parts[:3])


class _HTMLDataRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_html_rows(path: Path) -> list[list[str]]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise WorkbookBuildError(f"source not found: {path}") from error
    parser = _HTMLDataRows()
    parser.feed(content)
    return parser.rows


def bps_rows(bps1: Path, bps2: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row_number, row in enumerate(parse_html_rows(bps1), start=1):
        if len(row) < 5:
            continue
        result.append(
            {
                "source_file": bps1.name,
                "source_row": str(row_number),
                "relationship": "bps_to_kemendagri_province",
                "number": row[0],
                "bps_name": row[1],
                "bps_code": row[2],
                "reference_name": row[3],
                "reference_code_or_postal_group": row[4],
            }
        )
    for row_number, row in enumerate(parse_html_rows(bps2), start=1):
        if len(row) < 5 or not any(cell.strip() for cell in row):
            continue
        result.append(
            {
                "source_file": bps2.name,
                "source_row": str(row_number),
                "relationship": "bps_to_postal_group",
                "number": row[0],
                "bps_name": row[1],
                "bps_code": row[2],
                "reference_name": row[3],
                "reference_code_or_postal_group": row[4],
            }
        )
    return result


def flatten_json(value: Any, path: str = "$") -> Iterator[tuple[str, str, str]]:
    if isinstance(value, dict):
        if not value:
            yield path, "object", "{}"
        for key in sorted(value):
            yield from flatten_json(value[key], f"{path}.{key}")
    elif isinstance(value, list):
        if not value:
            yield path, "array", "[]"
        for index, item in enumerate(value):
            yield from flatten_json(item, f"{path}[{index}]")
    elif value is None:
        yield path, "null", ""
    elif isinstance(value, bool):
        yield path, "boolean", str(value).lower()
    else:
        yield path, type(value).__name__, str(value)


def _different_alias(primary: str, alternative: str) -> str:
    if alternative.strip() and normalize_name(primary) != normalize_name(alternative):
        return alternative.strip()
    return ""


MERGED_FIELDS = [
    "village_code",
    "province_code",
    "province_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "village_name",
    "postal_accepted",
    "verification_status",
    "confidence",
    "postal_candidate",
    "postal_status",
    "review_required",
    "postal_diskominfo",
    "postal_odj_2023",
    "postal_kodepos_dev",
    "province_alias_odj",
    "city_alias_odj",
    "district_alias_odj",
    "village_alias_odj",
    "bps_province_code",
    "bps_province_name",
    "bps_city_code",
    "bps_city_name",
    "bps_district_code",
    "bps_district_name",
    "bps_village_code",
    "bps_village_name",
    "latitude",
    "longitude",
    "status_adm",
    "source_ids",
    "source_rows",
]


def _postal_decision(new: str, old: str, api: str) -> tuple[str, str, str]:
    present = [value for value in (new, old, api) if value]
    distinct = set(present)
    if not present:
        return "", "unresolved", "yes"
    if len(distinct) == 1:
        if new and old:
            return present[0], "agree", "no"
        if api and not new and not old:
            return api, "kodepos_only", "yes"
        if new:
            return new, "diskominfo_only", "yes"
        return old, "odj_only", "yes"
    if new and old and new != old:
        if api == new:
            return new, "conflict_api_supports_diskominfo", "yes"
        if api == old:
            return old, "conflict_api_supports_odj", "yes"
        if api:
            return "", "conflict_api_third_value", "yes"
        return "", "conflict", "yes"
    if api and new and api != new:
        return "", "conflict_api_vs_diskominfo", "yes"
    if api and old and api != old:
        return "", "conflict_api_vs_odj", "yes"
    return present[0], "single_source", "yes"


def build_merged(
    diskominfo_rows: Sequence[Mapping[str, str]],
    odj_rows: Sequence[Mapping[str, str]],
    kodepos_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    odj_map = {
        canonical_village_code(row.get("kemendagri_kode_desa_kelurahan", "")): row
        for row in odj_rows
        if canonical_village_code(row.get("kemendagri_kode_desa_kelurahan", ""))
    }
    api_map = {
        canonical_village_code(row.get("village_code", "")): row
        for row in kodepos_rows
        if canonical_village_code(row.get("village_code", ""))
    }
    merged: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()

    conflict_fields = [
        "conflict_id",
        "village_code",
        "field",
        "issue_type",
        "status",
        "diskominfo_value",
        "odj_2023_value",
        "kodepos_dev_value",
        "selected_candidate",
        "note",
    ]

    def add_conflict(
        code: str,
        field: str,
        issue_type: str,
        new_value: str = "",
        old_value: str = "",
        api_value: str = "",
        selected: str = "",
        note: str = "",
    ) -> None:
        identity = "|".join((code, field, issue_type, new_value, old_value, api_value))
        conflict_id = "XLSX-" + hashlib.sha256(identity.encode()).hexdigest()[:12].upper()
        conflicts.append(
            dict(
                zip(
                    conflict_fields,
                    (
                        conflict_id,
                        code,
                        field,
                        issue_type,
                        "review_required",
                        new_value,
                        old_value,
                        api_value,
                        selected,
                        note,
                    ),
                )
            )
        )

    for source_row_number, new in enumerate(diskominfo_rows, start=2):
        raw_code = new.get("kemendagri_kelurahan_kode", "").strip()
        if raw_code == PLACEHOLDER_CODE:
            add_conflict(
                raw_code,
                "village_code",
                "placeholder_row_excluded",
                new_value=new.get("kemendagri_kota_nama", ""),
                note=f"Diskominfo source row {source_row_number} is a city placeholder.",
            )
            continue
        code = canonical_village_code(raw_code)
        if not code:
            add_conflict(
                raw_code,
                "village_code",
                "invalid_village_code",
                new_value=raw_code,
                note=f"Diskominfo source row {source_row_number} cannot be canonicalized.",
            )
            continue
        province_code, city_code, district_code = parent_codes(code)
        old = odj_map.get(code, {})
        api = api_map.get(code, {})
        postal_new = clean_postal(new.get("kode_pos", ""))
        postal_old = clean_postal(old.get("kode_pos", ""))
        postal_api = clean_postal(api.get("postal_code", ""))
        postal_candidate, postal_status, review_required = _postal_decision(
            postal_new, postal_old, postal_api
        )
        consensus_accepted = bool(
            postal_new and postal_new == postal_old == postal_api
        )
        status_counts[postal_status] += 1
        source_ids = ["diskominfo_jabar_village_2024_unreviewed"]
        if old:
            source_ids.append("open_data_jabar_postal_2023")
        if api:
            source_ids.append("kodepos_dev_rest_api")
        result = {
            "village_code": code,
            "province_code": province_code,
            "province_name": new.get("kemendagri_provinsi_nama", "").strip(),
            "city_code": city_code,
            "city_name": new.get("kemendagri_kota_nama", "").strip(),
            "district_code": district_code,
            "district_name": new.get("kemendagri_kecamatan_nama", "").strip(),
            "village_name": new.get("kemendagri_kelurahan_nama", "").strip(),
            "postal_accepted": postal_new if consensus_accepted else "",
            "verification_status": (
                "verified_consensus" if consensus_accepted else "review_required"
            ),
            "confidence": "high" if consensus_accepted else "unresolved",
            "postal_candidate": postal_candidate,
            "postal_status": postal_status,
            "review_required": review_required,
            "postal_diskominfo": postal_new,
            "postal_odj_2023": postal_old,
            "postal_kodepos_dev": postal_api,
            "province_alias_odj": _different_alias(
                new.get("kemendagri_provinsi_nama", ""),
                old.get("nama_kemendagri_provinsi", ""),
            ),
            "city_alias_odj": _different_alias(
                new.get("kemendagri_kota_nama", ""),
                old.get("nama_kabupaten_kota", ""),
            ),
            "district_alias_odj": _different_alias(
                new.get("kemendagri_kecamatan_nama", ""),
                old.get("kemendagri_nama_kecamatan", ""),
            ),
            "village_alias_odj": _different_alias(
                new.get("kemendagri_kelurahan_nama", ""),
                old.get("kemendagri_nama_desa_kelurahan", ""),
            ),
            "bps_province_code": new.get("bps_provinsi_kode", "").strip(),
            "bps_province_name": new.get("bps_provinsi_nama", "").strip(),
            "bps_city_code": new.get("bps_kota_kode", "").strip(),
            "bps_city_name": new.get("bps_kota_nama", "").strip(),
            "bps_district_code": new.get("bps_kecamatan_kode", "").strip(),
            "bps_district_name": new.get("bps_kecamatan_nama", "").strip(),
            "bps_village_code": new.get("bps_kelurahan_kode", "").strip(),
            "bps_village_name": new.get("bps_kelurahan_nama", "").strip(),
            "latitude": new.get("latitude", "").strip(),
            "longitude": new.get("longitude", "").strip(),
            "status_adm": new.get("status_adm", "").strip(),
            "source_ids": ";".join(source_ids),
            "source_rows": (
                f"diskominfo:{source_row_number};"
                + (f"odj:{old.get('id', '')};" if old else "")
                + (f"kodepos:{api.get('snapshot', '')}" if api else "")
            ).rstrip(";"),
        }
        merged.append(result)

        if len({value for value in (postal_new, postal_old, postal_api) if value}) > 1:
            add_conflict(
                code,
                "postal_code",
                postal_status,
                postal_new,
                postal_old,
                postal_api,
                postal_candidate,
                "Postal disagreement is retained; blank candidate means unresolved.",
            )
        if not postal_new:
            add_conflict(
                code,
                "postal_code",
                "diskominfo_missing_or_invalid",
                new.get("kode_pos", ""),
                postal_old,
                postal_api,
                postal_candidate,
            )
        if not postal_old:
            add_conflict(
                code,
                "postal_code",
                "odj_missing_or_invalid",
                postal_new,
                old.get("kode_pos", ""),
                postal_api,
                postal_candidate,
            )
        for field, new_key, old_key in (
            ("city_name", "kemendagri_kota_nama", "nama_kabupaten_kota"),
            ("district_name", "kemendagri_kecamatan_nama", "kemendagri_nama_kecamatan"),
            ("village_name", "kemendagri_kelurahan_nama", "kemendagri_nama_desa_kelurahan"),
            ("bps_village_code", "bps_kelurahan_kode", "bps_kode_desa_kelurahan"),
            ("bps_village_name", "bps_kelurahan_nama", "bps_nama_desa_kelurahan"),
        ):
            new_value = new.get(new_key, "").strip()
            old_value = old.get(old_key, "").strip()
            if new_value and old_value and normalize_name(new_value) != normalize_name(old_value):
                add_conflict(
                    code,
                    field,
                    "source_difference",
                    new_value,
                    old_value,
                    note="Diskominfo remains the candidate hierarchy; alternative retained as evidence.",
                )
        if new.get("kemendagri_kota_kode", "").strip() != city_code:
            add_conflict(
                code,
                "city_code",
                "source_format_normalized_from_village_prefix",
                new.get("kemendagri_kota_kode", "").strip(),
                old.get("kode_kabupaten_kota", "").strip(),
                selected=city_code,
            )
        if not new.get("bps_kelurahan_kode", "").strip():
            add_conflict(code, "bps_village_code", "diskominfo_bps_missing")
        if not new.get("latitude", "").strip() or not new.get("longitude", "").strip():
            add_conflict(code, "coordinates", "diskominfo_coordinates_missing")

    merged.sort(key=lambda row: row["village_code"])
    conflicts.sort(key=lambda row: (row["village_code"], row["field"], row["issue_type"]))
    return merged, conflicts, dict(sorted(status_counts.items()))


def _excel_column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml_text(value: Any) -> str:
    text = ILLEGAL_XML.sub("", str(value if value is not None else ""))
    return escape(text)


def _write_sheet_xml(
    path: Path,
    rows: Iterable[Sequence[Any]],
    *,
    freeze_header: bool = True,
    autofilter: bool = True,
) -> tuple[int, int]:
    row_count = 0
    column_count = 0
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
        stream.write('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')
        if freeze_header:
            stream.write(
                '<sheetViews><sheetView workbookViewId="0">'
                '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                '</sheetView></sheetViews>'
            )
        stream.write('<sheetFormatPr defaultRowHeight="15"/>')
        stream.write('<sheetData>')
        for row_count, row in enumerate(rows, start=1):
            values = list(row)
            column_count = max(column_count, len(values))
            stream.write(f'<row r="{row_count}">')
            for column_index, value in enumerate(values, start=1):
                reference = f"{_excel_column(column_index)}{row_count}"
                style = ' s="1"' if row_count == 1 else ""
                stream.write(f'<c r="{reference}" t="inlineStr"{style}><is><t xml:space="preserve">')
                stream.write(_xml_text(value))
                stream.write('</t></is></c>')
            stream.write('</row>')
        stream.write('</sheetData>')
        if autofilter and row_count and column_count:
            stream.write(
                f'<autoFilter ref="A1:{_excel_column(column_count)}{row_count}"/>'
            )
        stream.write('</worksheet>')
    return row_count, column_count


def _workbook_parts(sheet_names: Sequence[str]) -> dict[str, str]:
    sheet_elements = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    relationships = "".join(
        '<Relationship '
        f'Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheet_names) + 1)
    )
    relationships += (
        '<Relationship Id="rIdStyles" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    )
    overrides = "".join(
        '<Override '
        f'PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheet_names) + 1)
    )
    return {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            f'{overrides}</Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            '</Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{sheet_elements}</sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{relationships}</Relationships>'
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyNumberFormat="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        ),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:creator>ALAMATIN</dc:creator><dc:title>Jawa Barat source review</dc:title>'
            '<dcterms:created xsi:type="dcterms:W3CDTF">2026-08-11T00:00:00Z</dcterms:created>'
            '</cp:coreProperties>'
        ),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            '<Application>ALAMATIN source review generator</Application></Properties>'
        ),
    }


def write_xlsx(
    output: Path,
    sheets: Sequence[tuple[str, Callable[[], Iterable[Sequence[Any]]]]],
) -> dict[str, tuple[int, int]]:
    names = [name for name, _ in sheets]
    if len(names) != len(set(names)) or any(not name or len(name) > 31 for name in names):
        raise WorkbookBuildError("sheet names must be unique and at most 31 characters")
    output.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, tuple[int, int]] = {}
    temporary_output = output.with_name(f".{output.name}.part")
    try:
        with tempfile.TemporaryDirectory(prefix="alamatin-xlsx-") as directory:
            temp_dir = Path(directory)
            sheet_paths: list[Path] = []
            for index, (name, factory) in enumerate(sheets, start=1):
                sheet_path = temp_dir / f"sheet{index}.xml"
                counts[name] = _write_sheet_xml(sheet_path, factory())
                sheet_paths.append(sheet_path)
            with zipfile.ZipFile(
                temporary_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                for archive_name, content in _workbook_parts(names).items():
                    archive.writestr(_zip_info(archive_name), content)
                for index, sheet_path in enumerate(sheet_paths, start=1):
                    archive_name = f"xl/worksheets/sheet{index}.xml"
                    with sheet_path.open("rb") as source, archive.open(
                        _zip_info(archive_name), "w"
                    ) as destination:
                        shutil.copyfileobj(source, destination, length=1024 * 1024)
        temporary_output.replace(output)
    except BaseException:
        temporary_output.unlink(missing_ok=True)
        raise
    return counts


def _zip_info(name: str) -> zipfile.ZipInfo:
    """Return stable ZIP metadata so identical workbook inputs hash identically."""
    info = zipfile.ZipInfo(name, date_time=(2026, 8, 11, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _dict_sheet(headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> Iterator[Sequence[Any]]:
    yield headers
    for row in rows:
        yield [row.get(header, "") for header in headers]


def _count_csv_rows(path: Path) -> int:
    return sum(1 for _ in iter_csv_sheet(path)) - 1


def build_workbook(
    *,
    odj_path: Path,
    diskominfo_path: Path,
    bps1_path: Path,
    bps2_path: Path,
    kemendagri_path: Path,
    kodepos_path: Path,
    consensus_path: Path,
    unresolved_group_summary_path: Path,
    spotcheck_summary_path: Path,
    final_reference_summary_path: Path,
    output: Path,
) -> dict[str, Any]:
    odj_headers, odj_all = read_csv(odj_path)
    odj_jabar = [
        row
        for row in odj_all
        if row.get("kode_kemendagri_provinsi", "").strip() == "32"
    ]
    diskominfo_headers, diskominfo = read_csv(diskominfo_path)
    bps = bps_rows(bps1_path, bps2_path)
    bps_headers = list(bps[0]) if bps else [
        "source_file", "source_row", "relationship", "number", "bps_name",
        "bps_code", "reference_name", "reference_code_or_postal_group",
    ]
    try:
        kemendagri = json.loads(kemendagri_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise WorkbookBuildError(f"invalid Kemendagri metadata: {kemendagri_path}") from error
    kodepos_headers, kodepos = read_csv(kodepos_path)
    merged, conflicts, status_counts = build_merged(diskominfo, odj_jabar, kodepos)
    if consensus_path.exists():
        consensus_headers, consensus_rows = read_csv(consensus_path)
        required_consensus = {
            "village_code",
            "postal_code",
            "verification_status",
            "administrative_resolution_applied",
        }
        missing_consensus = required_consensus - set(consensus_headers)
        if missing_consensus:
            raise WorkbookBuildError(
                "consensus CSV is missing columns: "
                + ", ".join(sorted(missing_consensus))
            )
        if len(consensus_rows) != len(merged):
            raise WorkbookBuildError(
                "consensus CSV row count differs from the merged source coverage"
            )
        merged_sheet_headers = consensus_headers
        merged_sheet_rows = consensus_rows
    else:
        merged_sheet_headers = MERGED_FIELDS
        merged_sheet_rows = merged
    conflict_headers = list(conflicts[0]) if conflicts else [
        "conflict_id", "village_code", "field", "issue_type", "status",
        "diskominfo_value", "odj_2023_value", "kodepos_dev_value",
        "selected_candidate", "note",
    ]

    actual_diskominfo = [
        row for row in diskominfo
        if row.get("kemendagri_kelurahan_kode", "").strip() != PLACEHOLDER_CODE
    ]
    old_codes = {
        canonical_village_code(row.get("kemendagri_kode_desa_kelurahan", ""))
        for row in odj_jabar
    }
    new_codes = {
        canonical_village_code(row.get("kemendagri_kelurahan_kode", ""))
        for row in actual_diskominfo
    }
    quality_rows: list[dict[str, str]] = [
        {"category": "coverage", "metric": "odj_all_rows", "value": str(len(odj_all)), "note": "National raw rows."},
        {"category": "coverage", "metric": "odj_jabar_rows", "value": str(len(odj_jabar)), "note": "Province code 32."},
        {"category": "coverage", "metric": "diskominfo_raw_rows", "value": str(len(diskominfo)), "note": "Includes placeholders."},
        {"category": "coverage", "metric": "diskominfo_placeholder_rows", "value": str(len(diskominfo) - len(actual_diskominfo)), "note": "Excluded from candidate."},
        {"category": "coverage", "metric": "merged_candidate_rows", "value": str(len(merged)), "note": "One row per actual village code."},
        {"category": "integrity", "metric": "same_village_code_set", "value": str(old_codes == new_codes).lower(), "note": "ODJ Jabar versus Diskominfo actual rows."},
        {"category": "quality", "metric": "diskominfo_missing_postal", "value": str(sum(not clean_postal(row.get("kode_pos", "")) for row in actual_diskominfo)), "note": "Blank or invalid five-digit value."},
        {"category": "quality", "metric": "odj_missing_or_invalid_postal", "value": str(sum(not clean_postal(row.get("kode_pos", "")) for row in odj_jabar)), "note": "Includes zero values."},
        {"category": "quality", "metric": "diskominfo_missing_bps_village", "value": str(sum(not row.get("bps_kelurahan_kode", "").strip() for row in actual_diskominfo)), "note": "Village BPS fields absent."},
        {"category": "quality", "metric": "diskominfo_missing_coordinates", "value": str(sum(not row.get("latitude", "").strip() or not row.get("longitude", "").strip() for row in actual_diskominfo)), "note": "Latitude or longitude absent."},
        {"category": "validation", "metric": "kodepos_dev_observations", "value": str(len(kodepos)), "note": "Internal third-party REST validation observations."},
        {"category": "consensus", "metric": "verified_consensus", "value": str(sum(row.get("verification_status", "") == "verified_consensus" for row in merged_sheet_rows)), "note": "All three postal values are the same valid five-digit code."},
        {"category": "consensus", "metric": "corroborated_candidate", "value": str(sum(row.get("verification_status", "") == "corroborated_candidate" for row in merged_sheet_rows)), "note": "Kodepos.dev matches exactly one local source; candidate only."},
        {"category": "consensus", "metric": "review_required_total", "value": str(sum(row.get("review_required", "") == "yes" for row in merged_sheet_rows)), "note": "Accepted postal_code remains blank; includes corroborated candidates."},
        {"category": "consensus", "metric": "unresolved", "value": str(sum(row.get("verification_status", "") == "review_required" for row in merged_sheet_rows)), "note": "No two-source candidate selected."},
        {"category": "consensus", "metric": "administrative_resolutions_applied", "value": str(sum(row.get("administrative_resolution_applied", "") == "yes" for row in merged_sheet_rows)), "note": "Kemendagri 2025 old-to-current village-code resolutions."},
        {"category": "review", "metric": "conflict_rows", "value": str(len(conflicts)), "note": "May contain multiple issues per village."},
    ]
    quality_rows.extend(
        {"category": "postal_status", "metric": status, "value": str(count), "note": "Derived candidate status."}
        for status, count in status_counts.items()
    )
    if unresolved_group_summary_path.exists():
        try:
            unresolved_summary = json.loads(
                unresolved_group_summary_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise WorkbookBuildError(
                f"invalid unresolved group summary: {unresolved_group_summary_path}"
            ) from error
        for metric in (
            "source_disagreement_rows",
            "government_consensus_api_conflict_rows",
            "district_cluster_count",
            "triplet_cluster_count",
        ):
            quality_rows.append(
                {
                    "category": "unresolved_grouping",
                    "metric": metric,
                    "value": str(unresolved_summary.get(metric, "")),
                    "note": "Generated by scripts/group_postal_unresolved.py.",
                }
            )
    if spotcheck_summary_path.exists():
        try:
            spotcheck_summary = json.loads(
                spotcheck_summary_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise WorkbookBuildError(
                f"invalid postal spot-check summary: {spotcheck_summary_path}"
            ) from error
        for metric in (
            "queue_rows",
            "represented_unresolved_rows",
            "observed_queue_rows",
            "pending_queue_rows",
            "observed_represented_rows",
        ):
            quality_rows.append(
                {
                    "category": "pos_indonesia_spotcheck",
                    "metric": metric,
                    "value": str(spotcheck_summary.get(metric, "")),
                    "note": (
                        "Selected manual evidence only; never propagated "
                        "automatically to a cluster."
                    ),
                }
            )
    if final_reference_summary_path.exists():
        try:
            final_summary = json.loads(
                final_reference_summary_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise WorkbookBuildError(
                f"invalid final reference summary: {final_reference_summary_path}"
            ) from error
        for metric in (
            "total_administrative_rows",
            "verified_lookup_rows",
            "exception_rows",
            "rows_with_aliases",
            "manual_pos_observation_rows",
        ):
            quality_rows.append(
                {
                    "category": "final_reference_v1",
                    "metric": metric,
                    "value": str(final_summary.get(metric, "")),
                    "note": "Generated by scripts/build_final_jabar_reference.py.",
                }
            )
    quality_headers = ["category", "metric", "value", "note"]

    sources = [
        ("01_odj_raw_all", "open_data_jabar_postal_2023", odj_path, len(odj_all), len(odj_all), "Exact raw CSV rows; all values written as text."),
        ("02_odj_jabar", "open_data_jabar_postal_2023", odj_path, len(odj_all), len(odj_jabar), "Filter kode_kemendagri_provinsi == 32."),
        ("03_diskominfo_raw", "diskominfo_jabar_village_2024_unreviewed", diskominfo_path, len(diskominfo), len(diskominfo), "Exact raw CSV rows; source requires catalog review."),
        (
            "04_bps_province_map",
            "bps_sig_code_relationship_2020",
            bps1_path,
            len(parse_html_rows(bps1_path)),
            sum(row["source_file"] == bps1_path.name for row in bps),
            "Normalized first HTML table mislabeled .xls; province level only.",
        ),
        (
            "04_bps_province_map",
            "bps_sig_code_relationship_2020",
            bps2_path,
            len(parse_html_rows(bps2_path)),
            sum(row["source_file"] == bps2_path.name for row in bps),
            "Normalized second HTML table mislabeled .xls; province level only.",
        ),
        ("05_kemendagri_meta", "kemendagri_master_village_2024", kemendagri_path, 1, sum(1 for _ in flatten_json(kemendagri)), "Flattened CKAN metadata; not master village data."),
        ("06_kodepos_checks", "kodepos_dev_rest_api", kodepos_path, len(kodepos), len(kodepos), "Internal validation observations; not canonical authority."),
        ("07_merged_candidate", "derived_multi_source", consensus_path if consensus_path.exists() else output, 0, len(merged_sheet_rows), "Tiered consensus/corroborated candidate when the processed artifact is available; accepted postal_code remains blank outside full consensus."),
        ("08_conflicts", "derived_multi_source", output, 0, len(conflicts), "Every detected difference/gap is retained for review."),
        ("09_quality_summary", "derived_multi_source", output, 0, len(quality_rows), "Deterministic counts from this build."),
    ]
    manifest_headers = [
        "sheet", "source_id", "role", "original_path", "sha256", "raw_rows",
        "included_rows", "transformation", "notes",
    ]
    manifest_rows: list[dict[str, str]] = [
        {
            "sheet": "00_manifest",
            "source_id": "alamatin_source_review_workbook",
            "role": "human_review_only",
            "original_path": str(output.relative_to(ROOT) if output.is_relative_to(ROOT) else output),
            "sha256": "computed after build; use sha256sum on workbook",
            "raw_rows": "",
            "included_rows": "",
            "transformation": "Generated by scripts/build_source_review_workbook.py",
            "notes": "Not canonical; do not commit raw-derived workbook.",
        }
    ]
    for sheet, source_id, path, raw_count, included_count, transformation in sources:
        source_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        manifest_rows.append(
            {
                "sheet": sheet,
                "source_id": source_id,
                "role": "raw" if "raw" in sheet else "derived_or_normalized",
                "original_path": str(source_path),
                "sha256": file_sha256(path) if path.exists() and path != output else "",
                "raw_rows": str(raw_count),
                "included_rows": str(included_count),
                "transformation": transformation,
                "notes": "Codes and postal values are stored as Excel text.",
            }
        )

    flat_kemendagri = list(flatten_json(kemendagri))
    sheet_factories: list[tuple[str, Callable[[], Iterable[Sequence[Any]]]]] = [
        ("00_manifest", lambda: _dict_sheet(manifest_headers, manifest_rows)),
        ("01_odj_raw_all", lambda: iter_csv_sheet(odj_path)),
        ("02_odj_jabar", lambda: _dict_sheet(odj_headers, odj_jabar)),
        ("03_diskominfo_raw", lambda: iter_csv_sheet(diskominfo_path)),
        ("04_bps_province_map", lambda: _dict_sheet(bps_headers, bps)),
        ("05_kemendagri_meta", lambda: iter((["json_path", "value_type", "value"], *flat_kemendagri))),
        ("06_kodepos_checks", lambda: _dict_sheet(kodepos_headers, kodepos)),
        ("07_merged_candidate", lambda: _dict_sheet(merged_sheet_headers, merged_sheet_rows)),
        ("08_conflicts", lambda: _dict_sheet(conflict_headers, conflicts)),
        ("09_quality_summary", lambda: _dict_sheet(quality_headers, quality_rows)),
    ]
    counts = write_xlsx(output, sheet_factories)
    return {
        "output": str(output),
        "sha256": file_sha256(output),
        "sheets": {
            name: {"rows_with_header": row_count, "columns": column_count}
            for name, (row_count, column_count) in counts.items()
        },
    }


def validate_xlsx(path: Path, expected_sheets: Sequence[str]) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise WorkbookBuildError(f"corrupt workbook member: {bad}")
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            names = [sheet.attrib["name"] for sheet in workbook.findall("x:sheets/x:sheet", namespace)]
            if names != list(expected_sheets):
                raise WorkbookBuildError(f"unexpected sheet order: {names}")
            for index in range(1, len(names) + 1):
                ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
    except (FileNotFoundError, zipfile.BadZipFile, ET.ParseError) as error:
        raise WorkbookBuildError(f"invalid xlsx workbook: {path}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odj", type=Path, default=DEFAULT_ODJ)
    parser.add_argument("--diskominfo", type=Path, default=DEFAULT_DISKOMINFO)
    parser.add_argument("--bps1", type=Path, default=DEFAULT_BPS1)
    parser.add_argument("--bps2", type=Path, default=DEFAULT_BPS2)
    parser.add_argument("--kemendagri", type=Path, default=DEFAULT_KEMENDAGRI)
    parser.add_argument("--kodepos", type=Path, default=DEFAULT_KODEPOS)
    parser.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS)
    parser.add_argument(
        "--unresolved-group-summary",
        type=Path,
        default=DEFAULT_UNRESOLVED_GROUP_SUMMARY,
    )
    parser.add_argument(
        "--spotcheck-summary",
        type=Path,
        default=DEFAULT_SPOTCHECK_SUMMARY,
    )
    parser.add_argument(
        "--final-reference-summary",
        type=Path,
        default=DEFAULT_FINAL_REFERENCE_SUMMARY,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_workbook(
            odj_path=args.odj,
            diskominfo_path=args.diskominfo,
            bps1_path=args.bps1,
            bps2_path=args.bps2,
            kemendagri_path=args.kemendagri,
            kodepos_path=args.kodepos,
            consensus_path=args.consensus,
            unresolved_group_summary_path=args.unresolved_group_summary,
            spotcheck_summary_path=args.spotcheck_summary,
            final_reference_summary_path=args.final_reference_summary,
            output=args.output,
        )
        expected = [f"{index:02d}_{name}" for index, name in enumerate((
            "manifest", "odj_raw_all", "odj_jabar", "diskominfo_raw",
            "bps_province_map", "kemendagri_meta", "kodepos_checks",
            "merged_candidate", "conflicts", "quality_summary",
        ))]
        validate_xlsx(args.output, expected)
    except (WorkbookBuildError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

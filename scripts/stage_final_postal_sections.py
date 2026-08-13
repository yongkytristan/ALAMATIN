#!/usr/bin/env python3
"""Stage merge-ready postal sections under data/final."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from build_source_review_workbook import file_sha256, read_csv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SECTION_ONE_SOURCE = (
    ROOT / "data" / "processed" / "jabar-postal-consensus-accepted.csv"
)
DEFAULT_ADJUDICATED_SOURCE = (
    ROOT / "data" / "processed" / "jabar-postal-adjudicated.csv"
)
DEFAULT_SECTION_TWO_CODES = (
    ROOT / "data" / "interim" / "postal-review" / "jabar-postal-corroborated-review.csv"
)
DEFAULT_SECTION_THREE_CODES = (
    ROOT / "data" / "interim" / "postal-review" / "jabar-postal-unresolved-review.csv"
)
DEFAULT_SECTION_ONE = ROOT / "data" / "final" / "section-1-verified-consensus.csv"
DEFAULT_SECTION_TWO = ROOT / "data" / "final" / "section-2-verified-adjudicated.csv"
DEFAULT_SECTION_THREE = ROOT / "data" / "final" / "section-3-verified-adjudicated.csv"
DEFAULT_MERGED = ROOT / "data" / "final" / "jabar-postal-final-merged.csv"
DEFAULT_SUMMARY = ROOT / "data" / "final" / "sections-summary.json"


class FinalSectionError(ValueError):
    """Raised when the two sections cannot be staged safely."""


def stage_sections(
    section_one_rows: Sequence[Mapping[str, str]],
    adjudicated_rows: Sequence[Mapping[str, str]],
    section_two_codes: set[str],
    section_three_codes: set[str],
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, Any],
]:
    section_one = [dict(row) for row in section_one_rows]
    section_two = [
        dict(row)
        for row in adjudicated_rows
        if row.get("village_code") in section_two_codes
        and row.get("verification_status") == "verified_adjudicated"
    ]
    section_three = [
        dict(row)
        for row in adjudicated_rows
        if row.get("village_code") in section_three_codes
        and row.get("verification_status") == "verified_adjudicated"
    ]
    if (
        len(section_one) != 2876
        or len(section_two_codes) != 1974
        or len(section_two) != 1974
        or len(section_three_codes) != 1107
    ):
        raise FinalSectionError(
            "unexpected section source or promoted counts"
        )
    one_codes = {row.get("village_code", "") for row in section_one}
    two_codes = {row.get("village_code", "") for row in section_two}
    three_codes = {row.get("village_code", "") for row in section_three}
    if "" in one_codes or "" in two_codes or "" in three_codes:
        raise FinalSectionError("a staged row lacks village_code")
    if (
        len(one_codes) != len(section_one)
        or len(two_codes) != len(section_two)
        or len(three_codes) != len(section_three)
    ):
        raise FinalSectionError("a staged section contains duplicate village_code")
    if one_codes & two_codes or one_codes & three_codes or two_codes & three_codes:
        raise FinalSectionError("staged sections overlap")
    for row in [*section_one, *section_two, *section_three]:
        postal = row.get("postal_code", "")
        if len(postal) != 5 or not postal.isdigit():
            raise FinalSectionError(
                f"invalid final postal_code for {row.get('village_code', '')}"
            )
        if row.get("review_required") != "no":
            raise FinalSectionError(
                f"merge-ready row still requires review: {row.get('village_code', '')}"
            )
    section_one.sort(key=lambda row: row["village_code"])
    section_two.sort(key=lambda row: row["village_code"])
    section_three.sort(key=lambda row: row["village_code"])
    merged = sorted(
        [*section_one, *section_two, *section_three],
        key=lambda row: row["village_code"],
    )
    return section_one, section_two, section_three, merged, {
        "schema_version": "1.0.0",
        "section_1_rows": len(section_one),
        "section_2_rows": len(section_two),
        "section_3_rows": len(section_three),
        "section_3_unresolved_rows": len(section_three_codes) - len(section_three),
        "merge_ready_rows": len(section_one) + len(section_two) + len(section_three),
        "overlap_village_codes": 0,
        "schema_compatible": True,
        "merge_key": "village_code",
    }


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section-one-source", type=Path, default=DEFAULT_SECTION_ONE_SOURCE
    )
    parser.add_argument(
        "--adjudicated-source", type=Path, default=DEFAULT_ADJUDICATED_SOURCE
    )
    parser.add_argument(
        "--section-two-codes", type=Path, default=DEFAULT_SECTION_TWO_CODES
    )
    parser.add_argument(
        "--section-three-codes", type=Path, default=DEFAULT_SECTION_THREE_CODES
    )
    parser.add_argument("--section-one", type=Path, default=DEFAULT_SECTION_ONE)
    parser.add_argument("--section-two", type=Path, default=DEFAULT_SECTION_TWO)
    parser.add_argument("--section-three", type=Path, default=DEFAULT_SECTION_THREE)
    parser.add_argument("--merged", type=Path, default=DEFAULT_MERGED)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fields_one, source_one = read_csv(args.section_one_source)
        fields_adjudicated, adjudicated = read_csv(args.adjudicated_source)
        _, section_two_source = read_csv(args.section_two_codes)
        _, section_three_source = read_csv(args.section_three_codes)
        if fields_one != fields_adjudicated:
            raise FinalSectionError("Section sources do not share the canonical schema")
        section_one, section_two, section_three, merged, summary = stage_sections(
            source_one,
            adjudicated,
            {row["village_code"] for row in section_two_source},
            {row["village_code"] for row in section_three_source},
        )
        _write_csv(args.section_one, fields_one, section_one)
        _write_csv(args.section_two, fields_one, section_two)
        _write_csv(args.section_three, fields_one, section_three)
        _write_csv(args.merged, fields_one, merged)
        _write_json(
            args.summary,
            {
                **summary,
                "merged_rows": len(merged),
                "input_sha256": {
                    "section_1_source": file_sha256(args.section_one_source),
                    "adjudicated_source": file_sha256(args.adjudicated_source),
                    "section_2_codes": file_sha256(args.section_two_codes),
                    "section_3_codes": file_sha256(args.section_three_codes),
                },
                "output_sha256": {
                    "section_1": file_sha256(args.section_one),
                    "section_2": file_sha256(args.section_two),
                    "section_3": file_sha256(args.section_three),
                    "merged": file_sha256(args.merged),
                },
            },
        )
    except (FinalSectionError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(args.summary.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

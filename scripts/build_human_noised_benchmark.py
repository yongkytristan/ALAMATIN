#!/usr/bin/env python3
"""Turn selected public-address candidates into ALM-012's human-noised benchmark.

This script has two steps and deliberately does NOT write address text itself:

  make-template   Turn candidates.csv into a blank worksheet for a human
                   annotator to fill in (rewritten_address, annotator_id).
  assemble        Validate a completed worksheet and assemble the governed
                   benchmark manifest.

A real person must fill in `rewritten_address` the way they would type the
address into a checkout form, without adding any new personal data. Nothing
in this repository may synthesize that column and label it human-written --
doing so would misrepresent the benchmark's provenance.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "interim" / "school-address-benchmark"
DEFAULT_CANDIDATES = DEFAULT_DIR / "candidates.csv"
DEFAULT_TEMPLATE = DEFAULT_DIR / "annotation-template.csv"
DEFAULT_BENCHMARK = DEFAULT_DIR / "human-noised-benchmark.json"
DEFAULT_SUMMARY = DEFAULT_DIR / "human-noised-benchmark-summary.json"
TEMPLATE_FIELDS = (
    "base_address_id",
    "source_id",
    "source_record_id",
    "school_level",
    "reference_address",
    "rewritten_address",
    "annotator_id",
    "notes",
)
LANDING_PAGE_URLS = {
    "open_data_jabar_npsn_sd_2023": (
        "https://opendata.jabarprov.go.id/id/dataset/"
        "daftar-nomor-pokok-sekolah-nasional-npsn-sekolah-dasar-sd-berdasarkan-"
        "status-sekolah-dan-kabupatenkota-di-jawa-barat"
    ),
    "open_data_jabar_npsn_sma_2023": (
        "https://opendata.jabarprov.go.id/id/dataset/"
        "daftar-nomor-pokok-sekolah-nasional-npsn-sekolah-menengah-atas-sma-"
        "berdasarkan-status-sekolah-dan-kabupatenkota-di-jawa-barat"
    ),
}
POSSIBLE_PHONE_NUMBER = re.compile(r"\b\d{7,}\b")


class BenchmarkAssemblyError(ValueError):
    """Raised when the annotation worksheet is missing or violates a rule."""


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        return ","


def _read_csv_rows(path: Path, required_fields: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(4096)
            stream.seek(0)
            reader = csv.DictReader(stream, delimiter=_sniff_delimiter(sample))
            missing = set(required_fields) - set(reader.fieldnames or ())
            if missing:
                raise BenchmarkAssemblyError(
                    f"{path} missing columns: {', '.join(sorted(missing))}"
                )
            return [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    except FileNotFoundError as error:
        raise BenchmarkAssemblyError(f"file not found: {path}") from error


def make_template(candidates_path: Path, template_path: Path) -> int:
    candidates = _read_csv_rows(
        candidates_path,
        ("base_address_id", "source_id", "source_record_id", "school_level", "reference_address"),
    )
    if not candidates:
        raise BenchmarkAssemblyError("no candidates to build a template from")
    rows = [
        {
            "base_address_id": row["base_address_id"],
            "source_id": row["source_id"],
            "source_record_id": row["source_record_id"],
            "school_level": row["school_level"],
            "reference_address": row["reference_address"],
            "rewritten_address": "",
            "annotator_id": "",
            "notes": "",
        }
        for row in candidates
    ]
    template_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = template_path.with_name(f".{template_path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TEMPLATE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(template_path)
    return len(rows)


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def validate_completed_rows(rows: list[dict[str, str]]) -> list[str]:
    problems: list[str] = []
    seen_ids: set[str] = set()
    for row in rows:
        base_id = row["base_address_id"]
        if base_id in seen_ids:
            problems.append(f"{base_id}: duplicate base_address_id")
        seen_ids.add(base_id)
        if not row["rewritten_address"]:
            problems.append(f"{base_id}: rewritten_address is empty")
            continue
        if not row["annotator_id"]:
            problems.append(f"{base_id}: annotator_id is empty")
        if _normalize(row["rewritten_address"]) == _normalize(row["reference_address"]):
            problems.append(f"{base_id}: rewritten_address is identical to reference_address")
        phone_like = POSSIBLE_PHONE_NUMBER.findall(row["rewritten_address"])
        if phone_like:
            problems.append(
                f"{base_id}: rewritten_address contains a phone-number-like sequence {phone_like}"
            )
    return problems


def assemble(template_path: Path, benchmark_path: Path, summary_path: Path) -> dict[str, Any]:
    rows = _read_csv_rows(template_path, TEMPLATE_FIELDS)
    if not rows:
        raise BenchmarkAssemblyError("completed worksheet has no rows")
    problems = validate_completed_rows(rows)
    if problems:
        raise BenchmarkAssemblyError(
            "worksheet failed validation:\n" + "\n".join(f"- {problem}" for problem in problems)
        )

    assembled_at = datetime.now(timezone.utc).isoformat()
    examples = [
        {
            "base_address_id": row["base_address_id"],
            "source_id": row["source_id"],
            "source_record_id": row["source_record_id"],
            "source_url": LANDING_PAGE_URLS.get(row["source_id"], ""),
            "school_level": row["school_level"],
            "text": row["rewritten_address"],
            "annotator_id": row["annotator_id"],
            "notes": row["notes"],
        }
        for row in sorted(rows, key=lambda item: item["base_address_id"])
    ]
    benchmark = {
        "benchmark_id": "alamatin_human_noised_public_address_benchmark_v1",
        "schema_version": "1.0.0",
        "assembled_at": assembled_at,
        "example_count": len(examples),
        "examples": examples,
    }
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    temp_benchmark = benchmark_path.with_name(f".{benchmark_path.name}.part")
    temp_benchmark.write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_benchmark.replace(benchmark_path)

    annotator_counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    for example in examples:
        annotator_counts[example["annotator_id"]] = annotator_counts.get(example["annotator_id"], 0) + 1
        level_counts[example["school_level"]] = level_counts.get(example["school_level"], 0) + 1
    summary = {
        "schema_version": "1.0.0",
        "assembled_at": assembled_at,
        "example_count": len(examples),
        "annotator_counts": dict(sorted(annotator_counts.items())),
        "level_counts": dict(sorted(level_counts.items())),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temp_summary = summary_path.with_name(f".{summary_path.name}.part")
    temp_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_summary.replace(summary_path)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser("make-template", help="build a blank annotation worksheet")
    template_parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    template_parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)

    assemble_parser = subparsers.add_parser("assemble", help="validate and assemble a completed worksheet")
    assemble_parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    assemble_parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    assemble_parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "make-template":
            count = make_template(args.candidates, args.template)
            print(json.dumps({"template": str(args.template), "row_count": count}, indent=2))
        elif args.command == "assemble":
            summary = assemble(args.template, args.benchmark, args.summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, BenchmarkAssemblyError) as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

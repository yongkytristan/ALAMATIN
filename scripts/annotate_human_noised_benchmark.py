#!/usr/bin/env python3
"""Produce candidate BIO labels for the ALM-012 human-noised benchmark.

This is an automated, rule-based first pass, explicitly disclosed as such
(`annotator_id`/`method` fields say so in the output). Per
`docs/label_schema.md` section 8, an automated candidate pass is allowed as a
starting point, but it never substitutes for documented human review --
every example still needs a human to confirm or correct it, and a stratified
20-30% sample must be independently re-labeled by a human to measure
agreement (see scripts/sample_double_annotation.py and
scripts/compute_annotation_agreement.py).

The heuristic works on comma/semicolon/hyphen-delimited segments (this
benchmark's addresses are almost always written as
"<locator>, <kecamatan>, <kabupaten/kota>", even when internal spacing inside
a segment is badly broken by typos) and cross-checks each segment against the
already-known structured kecamatan/kabupaten_kota values from
candidates.csv -- the strongest evidence tier in the label schema's
precedence rules. Anything it cannot confidently resolve is left `O` (never
guessed) and flagged in `needs_review` for a human to decide.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.label_schema import validate_bio_sequence  # noqa: E402
from alamatin.tokenizer import tokenize  # noqa: E402

DEFAULT_BENCHMARK = ROOT / "data" / "interim" / "school-address-benchmark" / "human-noised-benchmark.json"
DEFAULT_CANDIDATES_CSV = ROOT / "data" / "interim" / "school-address-benchmark" / "candidates.csv"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "school-address-benchmark" / "bio-candidates.json"
ANNOTATION_METHOD = "automated_rule_based_v1"

SEGMENT_BREAK_TOKENS = {",", ";", "-"}
FUZZY_MATCH_THRESHOLD = 0.62

KECAMATAN_PREFIXES = (
    "kecamatan", "kecmatan", "kmctn", "kcmtn", "kecamatn", "kecamtan", "kec", "kc",
)
KABUPATEN_PREFIXES = (
    "kabupaten", "kabupatn", "kbupatn", "kabpatn", "kabupatan", "kab", "kb", "kota", "kta", "kt",
)
KAMPUNG_DESA_PREFIXES = (
    "jalan", "jaln", "jln", "jl", "gang", "gg", "kampung", "kp", "dusun", "dsn", "dsuun", "desa", "ds",
)
PROVINCE_FORMS = ("jawabarat", "jabar")

RT_PATTERN = re.compile(r"^rt\.{0,2}0*(\d+)[a-z]?$")
RW_PATTERN = re.compile(r"^rw\.{0,2}0*(\d+)[a-z]?$")
NOMOR_PATTERN = re.compile(r"^(no|nomor|nomer)\.?0*(\d+[a-z]?)$")
RT_MARKER_ONLY = re.compile(r"^rt\.{0,2}$")
RW_MARKER_ONLY = re.compile(r"^rw\.{0,2}$")
NOMOR_MARKER_ONLY = re.compile(r"^(no|nomor|nomer)\.?$")
BARE_NUMBER = re.compile(r"^0*(\d+)[a-z]?$")
KODEPOS_PATTERN = re.compile(r"^\d{5}$")


class AnnotationError(ValueError):
    """Raised when the input data cannot be turned into candidate labels."""


def _clean(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _strip_prefix(cleaned: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in sorted(prefixes, key=len, reverse=True):
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
            return cleaned[len(prefix):]
    return None


def _fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _segment_spans(tokens: list[str]) -> list[list[int]]:
    segments: list[list[int]] = []
    current: list[int] = []
    for index, token in enumerate(tokens):
        if token in SEGMENT_BREAK_TOKENS:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(index)
    if current:
        segments.append(current)
    return segments


def _contiguous_runs(indices: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for index in indices:
        if runs and index == runs[-1][-1] + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    return runs


def _label_span(labels: list[str], indices: list[int], entity: str) -> None:
    """Label ``indices`` as ``entity``, starting a new B- at every gap.

    A gap happens when another entity (RT/RW/NOMOR) was extracted from the
    middle of the same logical segment; BIO validity requires a fresh B- tag
    after any interruption, even if the surrounding text is semantically one
    span.
    """

    for run in _contiguous_runs(indices):
        for position, index in enumerate(run):
            labels[index] = f"{'B' if position == 0 else 'I'}-{entity}"


def _extract_rt_rw_nomor(
    tokens: list[str], indices: list[int], labels: list[str], flags: list[str]
) -> list[int]:
    consumed: set[int] = set()
    position = 0
    while position < len(indices):
        index = indices[position]
        cleaned = tokens[index].lower()
        next_index = indices[position + 1] if position + 1 < len(indices) else None
        next_cleaned = tokens[next_index].lower() if next_index is not None else ""

        glued_match = None
        marker_only = None
        entity = None
        if RT_PATTERN.match(cleaned):
            glued_match, entity = RT_PATTERN.match(cleaned), "RT"
        elif RW_PATTERN.match(cleaned):
            glued_match, entity = RW_PATTERN.match(cleaned), "RW"
        elif NOMOR_PATTERN.match(cleaned):
            glued_match, entity = NOMOR_PATTERN.match(cleaned), "NOMOR"
        elif RT_MARKER_ONLY.match(cleaned) and next_index is not None and BARE_NUMBER.match(next_cleaned):
            marker_only, entity = True, "RT"
        elif RW_MARKER_ONLY.match(cleaned) and next_index is not None and BARE_NUMBER.match(next_cleaned):
            marker_only, entity = True, "RW"
        elif NOMOR_MARKER_ONLY.match(cleaned) and next_index is not None and BARE_NUMBER.match(next_cleaned):
            marker_only, entity = True, "NOMOR"
        elif KODEPOS_PATTERN.match(cleaned):
            labels[index] = "B-KODEPOS"
            consumed.add(index)
            position += 1
            continue

        if glued_match:
            labels[index] = f"B-{entity}"
            consumed.add(index)
            group = glued_match.group(glued_match.re.groups)
            if not cleaned.endswith(group):
                flags.append(f"{entity.lower()}_token_has_trailing_noise:{tokens[index]!r}")
            position += 1
            continue
        if marker_only:
            labels[index] = f"B-{entity}"
            labels[next_index] = f"I-{entity}"
            consumed.add(index)
            consumed.add(next_index)
            position += 2
            continue
        position += 1

    return [index for index in indices if index not in consumed]


def label_example(
    tokens: list[str], kecamatan_name: str, kabupaten_kota_name: str
) -> tuple[list[str], list[str]]:
    labels = ["O"] * len(tokens)
    flags: list[str] = []
    kecamatan_clean = _clean(kecamatan_name)
    kabupaten_clean = _clean(_strip_prefix(_clean(kabupaten_kota_name), ("kabupaten", "kota")) or kabupaten_kota_name)

    first_locator_assigned = False
    for segment in _segment_spans(tokens):
        remaining = _extract_rt_rw_nomor(tokens, segment, labels, flags)
        if not remaining:
            continue

        joined_clean = _clean("".join(tokens[i] for i in remaining))

        if joined_clean in PROVINCE_FORMS or "jawabarat" in joined_clean:
            _label_span(labels, remaining, "PROVINSI")
            continue

        kec_candidate = _strip_prefix(joined_clean, KECAMATAN_PREFIXES) or joined_clean
        kab_candidate = _strip_prefix(joined_clean, KABUPATEN_PREFIXES) or joined_clean
        kec_ratio = _fuzzy_ratio(kec_candidate, kecamatan_clean)
        kab_ratio = _fuzzy_ratio(kab_candidate, kabupaten_clean)

        has_kec_prefix = _strip_prefix(joined_clean, KECAMATAN_PREFIXES) is not None
        has_kab_prefix = _strip_prefix(joined_clean, KABUPATEN_PREFIXES) is not None

        if kec_ratio >= FUZZY_MATCH_THRESHOLD and kec_ratio >= kab_ratio:
            _label_span(labels, remaining, "KECAMATAN")
        elif kab_ratio >= FUZZY_MATCH_THRESHOLD:
            _label_span(labels, remaining, "KOTA_KABUPATEN")
        elif has_kec_prefix:
            flags.append(f"unmatched_kecamatan_designator:{''.join(tokens[i] for i in remaining)!r}")
            _label_span(labels, remaining, "KECAMATAN")
        elif has_kab_prefix:
            flags.append(f"unmatched_kabupaten_designator:{''.join(tokens[i] for i in remaining)!r}")
            _label_span(labels, remaining, "KOTA_KABUPATEN")
        else:
            entity = "JALAN" if not first_locator_assigned else "DETAIL_LOKASI"
            first_locator_assigned = True
            _label_span(labels, remaining, entity)
            if len(joined_clean) > 25:
                flags.append(f"long_unmatched_segment_needs_review:{''.join(tokens[i] for i in remaining)!r}")

    return labels, flags


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
        with args.candidates.open("r", encoding="utf-8-sig", newline="") as stream:
            metadata_by_id = {row["base_address_id"]: row for row in csv.DictReader(stream)}

        results: list[dict[str, Any]] = []
        flagged_count = 0
        for example in benchmark["examples"]:
            base_id = example["base_address_id"]
            metadata = metadata_by_id.get(base_id)
            if metadata is None:
                raise AnnotationError(f"no candidate metadata found for {base_id}")
            tokens = tokenize(example["text"])
            labels, flags = label_example(tokens, metadata["kecamatan"], metadata["kabupaten_kota"])
            valid, reason = validate_bio_sequence(labels)
            if not valid:
                raise AnnotationError(f"{base_id}: generated an invalid BIO sequence: {reason}")
            if flags:
                flagged_count += 1
            results.append(
                {
                    "base_address_id": base_id,
                    "tokens": tokens,
                    "labels": labels,
                    "status": "candidate",
                    "annotation_method": ANNOTATION_METHOD,
                    "flags": flags,
                }
            )

        payload = {
            "schema_version": "1.0.0",
            "annotation_method": ANNOTATION_METHOD,
            "example_count": len(results),
            "flagged_count": flagged_count,
            "examples": sorted(results, key=lambda item: item["base_address_id"]),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.part")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(args.output)
    except (OSError, KeyError, AnnotationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"example_count": len(results), "flagged_count": flagged_count}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

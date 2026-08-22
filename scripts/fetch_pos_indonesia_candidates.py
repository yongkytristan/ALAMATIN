#!/usr/bin/env python3
"""Fetch rate-limited Pos Indonesia observations for candidate review rows.

This internal-only tool submits the same public postcode search form a reviewer
uses, caches each unique village-name response, and accepts a result only when
village, district, city/regency, and province all match the target row. It does
not promote observations into the verified reference dataset.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SEARCH_URL = "https://kodepos.posindonesia.co.id/CariKodepos"
SOURCE_ID = "pos_indonesia_postcode_search"
USER_AGENT = (
    "ALAMATIN-postcode-validation/1.0 "
    "(+https://github.com/yongkytristan/ALAMATIN)"
)
DEFAULT_INPUT = (
    ROOT
    / "data"
    / "interim"
    / "postal-review"
    / "jabar-postal-corroborated-review.csv"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "interim"
    / "postal-review"
    / "pos-indonesia-candidate-observations.csv"
)
DEFAULT_CACHE = DEFAULT_OUTPUT.with_suffix(".cache.json")
DEFAULT_SUMMARY = DEFAULT_OUTPUT.with_suffix(".summary.json")
POSTAL_CODE = re.compile(r"^\d{5}$")
REQUIRED_FIELDS = {
    "province_code",
    "province_name",
    "city_code",
    "city_name",
    "district_code",
    "district_name",
    "village_code",
    "village_name",
    "postal_code_diskominfo",
    "suggested_postal_code",
}
RESULT_COLUMNS = (
    "postal_code",
    "village_name",
    "district_name",
    "city_name",
    "province_name",
)
OUTPUT_FIELDS = (
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
    "postal_code_diskominfo",
    "postal_code_candidate",
    "official_postal_code",
    "observation_status",
    "matches_diskominfo",
    "matches_candidate",
    "search_term",
    "search_result_count",
    "exact_result_count",
    "evidence_url",
    "note",
)


class PosFetchError(RuntimeError):
    """Raised when an input or remote response violates the fetch contract."""


class PosResultsParser(HTMLParser):
    """Extract rows from the official search result table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._table_depth = 0
        self._in_target_table = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row_cells: list[str] | None = None
        self.results: list[dict[str, str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self._in_target_table:
                self._table_depth += 1
            elif attributes.get("id") == "list-data":
                self._in_target_table = True
                self._table_depth = 1
        elif self._in_target_table and tag == "tr":
            self._row_cells = []
        elif self._in_target_table and tag == "td" and self._row_cells is not None:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._in_target_table:
            return
        if tag == "td" and self._in_cell and self._row_cells is not None:
            self._row_cells.append(" ".join("".join(self._cell_parts).split()))
            self._in_cell = False
            self._cell_parts = []
        elif tag == "tr" and self._row_cells is not None:
            if len(self._row_cells) == 6:
                values = self._row_cells[1:]
                self.results.append(dict(zip(RESULT_COLUMNS, values)))
            self._row_cells = None
        elif tag == "table":
            self._table_depth -= 1
            if self._table_depth == 0:
                self._in_target_table = False


def parse_results(html: str) -> list[dict[str, str]]:
    parser = PosResultsParser()
    parser.feed(html)
    parser.close()
    return parser.results


def normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def query_key(value: str) -> str:
    return normalize_name(value)


def exact_results(
    row: Mapping[str, str], results: Iterable[Mapping[str, str]]
) -> list[Mapping[str, str]]:
    expected = {
        "village_name": normalize_name(row["village_name"]),
        "district_name": normalize_name(row["district_name"]),
        "city_name": normalize_name(row["city_name"]),
        "province_name": normalize_name(row["province_name"]),
    }
    return [
        result
        for result in results
        if all(normalize_name(result[field]) == value for field, value in expected.items())
    ]


def read_review_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            missing = REQUIRED_FIELDS - set(reader.fieldnames or ())
            if missing:
                raise PosFetchError(
                    f"{path} missing fields: {', '.join(sorted(missing))}"
                )
            rows = [
                {key: (value or "").strip() for key, value in row.items() if key}
                for row in reader
            ]
    except FileNotFoundError as error:
        raise PosFetchError(f"input not found: {path}") from error
    if not rows:
        raise PosFetchError("input contains no review rows")
    return rows


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "1.0.0",
            "source_url": SEARCH_URL,
            "queries": {},
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PosFetchError(f"invalid cache: {path}") from error
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "1.0.0"
        or value.get("source_url") != SEARCH_URL
        or not isinstance(value.get("queries"), dict)
    ):
        raise PosFetchError(f"unsupported cache contract: {path}")
    return value


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def fetch_query(search_term: str, *, timeout: float, retries: int) -> list[dict[str, str]]:
    payload = urlencode({"kodepos": search_term}).encode("ascii")
    request = Request(
        SEARCH_URL,
        data=payload,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                html = response.read().decode(charset, errors="replace")
            return parse_results(html)
        except HTTPError as error:
            if error.code in {403, 429}:
                raise PosFetchError(
                    f"remote access stopped with HTTP {error.code}; do not bypass"
                ) from error
            if error.code < 500 or attempt == retries:
                raise PosFetchError(
                    f"request for {search_term!r} failed with HTTP {error.code}"
                ) from error
        except (TimeoutError, URLError) as error:
            if attempt == retries:
                raise PosFetchError(
                    f"request for {search_term!r} failed after {retries} attempts: {error}"
                ) from error
        time.sleep(min(2**attempt, 10))
    raise AssertionError("retry loop ended unexpectedly")


def build_observations(
    rows: Sequence[Mapping[str, str]], cache: Mapping[str, Any], snapshot: str
) -> list[dict[str, str]]:
    queries = cache["queries"]
    output: list[dict[str, str]] = []
    for row in rows:
        cached = queries.get(query_key(row["village_name"]))
        results = cached["results"] if cached else []
        exact = exact_results(row, results)
        official_codes = sorted(
            {
                result["postal_code"]
                for result in exact
                if POSTAL_CODE.fullmatch(result["postal_code"])
            }
        )
        if cached is None:
            status = "not_queried"
        elif not exact:
            status = "no_exact_match"
        elif len(official_codes) == 1:
            status = "exact_match"
        else:
            status = "multiple_exact_codes"
        official = official_codes[0] if len(official_codes) == 1 else ""
        output.append(
            {
                "source_id": SOURCE_ID,
                "snapshot": snapshot,
                "province_code": row["province_code"],
                "province_name": row["province_name"],
                "city_code": row["city_code"],
                "city_name": row["city_name"],
                "district_code": row["district_code"],
                "district_name": row["district_name"],
                "village_code": row["village_code"],
                "village_name": row["village_name"],
                "postal_code_diskominfo": row["postal_code_diskominfo"],
                "postal_code_candidate": row["suggested_postal_code"],
                "official_postal_code": official,
                "observation_status": status,
                "matches_diskominfo": str(
                    bool(official and official == row["postal_code_diskominfo"])
                ).lower(),
                "matches_candidate": str(
                    bool(official and official == row["suggested_postal_code"])
                ).lower(),
                "search_term": row["village_name"],
                "search_result_count": str(len(results)) if cached else "",
                "exact_result_count": str(len(exact)) if cached else "",
                "evidence_url": SEARCH_URL,
                "note": (
                    "Rate-limited internal observation; exact hierarchy match; "
                    "requires adjudication before promotion."
                ),
            }
        )
    return output


def write_csv_atomic(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def build_summary(
    observations: Sequence[Mapping[str, str]],
    *,
    cache: Mapping[str, Any],
    total_queries: int,
    snapshot: str,
    batch_size: int,
    request_delay: float,
    batch_pause: float,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in observations:
        status = row["observation_status"]
        counts[status] = counts.get(status, 0) + 1
    exact = [row for row in observations if row["observation_status"] == "exact_match"]
    return {
        "schema_version": "1.0.0",
        "source_id": SOURCE_ID,
        "source_url": SEARCH_URL,
        "snapshot": snapshot,
        "authorization_record": "project-owner approval in ALAMATIN work session 2026-08-11",
        "policy": "Observation only; no automatic promotion to verified data.",
        "review_rows": len(observations),
        "unique_queries_total": total_queries,
        "unique_queries_cached": len(cache["queries"]),
        "status_counts": dict(sorted(counts.items())),
        "exact_matches_diskominfo": sum(row["matches_diskominfo"] == "true" for row in exact),
        "exact_matches_candidate": sum(row["matches_candidate"] == "true" for row in exact),
        "batch_size": batch_size,
        "request_delay_seconds": request_delay,
        "batch_pause_seconds": batch_pause,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--snapshot", default=date.today().isoformat())
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--request-delay", type=float, default=2.0)
    parser.add_argument("--batch-pause", type=float, default=300.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--request-offset",
        type=int,
        default=0,
        help="Completed requests from a prior resumable run, used for batch pauses.",
    )
    parser.add_argument(
        "--max-new-requests",
        type=int,
        default=0,
        help="Stop after this many uncached queries; zero means all remaining queries.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.batch_size < 1:
            raise PosFetchError("--batch-size must be positive")
        if args.request_delay < 0 or args.batch_pause < 0:
            raise PosFetchError("delays may not be negative")
        if args.retries < 1 or args.max_new_requests < 0 or args.request_offset < 0:
            raise PosFetchError(
                "retries must be positive and request counts non-negative"
            )
        rows = read_review_rows(args.input)
        cache = load_cache(args.cache)
        query_terms: dict[str, str] = {}
        for row in rows:
            query_terms.setdefault(query_key(row["village_name"]), row["village_name"])
        pending = [key for key in sorted(query_terms) if key not in cache["queries"]]
        if args.max_new_requests:
            pending = pending[: args.max_new_requests]

        print(
            f"targets={len(rows)} unique_queries={len(query_terms)} "
            f"cached={len(cache['queries'])} scheduled={len(pending)}",
            flush=True,
        )
        for index, key in enumerate(pending, start=1):
            absolute_index = args.request_offset + index
            term = query_terms[key]
            results = fetch_query(term, timeout=args.timeout, retries=args.retries)
            cache["queries"][key] = {
                "query": term,
                "checked_at": args.snapshot,
                "result_count": len(results),
                "results": results,
            }
            write_json_atomic(args.cache, cache)
            print(
                f"request={absolute_index} cached={len(cache['queries'])}/"
                f"{len(query_terms)} query={term!r} results={len(results)}",
                flush=True,
            )
            if index == len(pending):
                continue
            if absolute_index % args.batch_size == 0:
                print(
                    f"batch complete; pausing {args.batch_pause:.0f} seconds",
                    flush=True,
                )
                time.sleep(args.batch_pause)
            elif args.request_delay:
                time.sleep(args.request_delay)

        observations = build_observations(rows, cache, args.snapshot)
        write_csv_atomic(args.output, observations)
        summary = build_summary(
            observations,
            cache=cache,
            total_queries=len(query_terms),
            snapshot=args.snapshot,
            batch_size=args.batch_size,
            request_delay=args.request_delay,
            batch_pause=args.batch_pause,
        )
        write_json_atomic(args.summary, summary)
    except (OSError, PosFetchError) as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 2

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

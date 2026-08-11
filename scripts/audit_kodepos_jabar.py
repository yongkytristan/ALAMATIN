#!/usr/bin/env python3
"""Audit all Jawa Barat village postal codes through paginated Kodepos.dev REST.

This command uses the API's documented search pagination instead of issuing one
request per village. Results are internal validation evidence, written only to
ignored ``data/interim`` paths, and never silently replace government-source
values. A checkpoint is saved after every page so a failed run can resume
without spending credits again on completed pages.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
from fetch_kodepos_crosscheck import (
    API_BASE_URL,
    CROSSCHECK_FIELDS,
    USER_AGENT,
    KodeposAPIError,
    _error_detail,
    crosscheck_row,
    load_api_key,
    write_crosscheck,
)


ROOT = Path(__file__).resolve().parents[1]
PROVINCE_CODE = "32"
SEARCH_QUERY = "Jawa Barat"
MAX_PAGE_SIZE = 100
MAX_ALLOWED_PAGES = 100
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "kodepos-dev-jabar.csv"
DEFAULT_COMPARISON = (
    ROOT / "data" / "interim" / "kodepos-dev-jabar-comparison.csv"
)
DEFAULT_DIFFERENCES = (
    ROOT / "data" / "interim" / "kodepos-dev-jabar-differences.csv"
)
DEFAULT_PRIORITY_REVIEW = (
    ROOT / "data" / "interim" / "kodepos-dev-jabar-priority-review.csv"
)
DEFAULT_LOCAL_DIFFERENCES = (
    ROOT
    / "data"
    / "interim"
    / "diskominfo-vs-open-data-jabar-postal-differences.csv"
)
DEFAULT_SUMMARY = ROOT / "data" / "interim" / "kodepos-dev-jabar-summary.json"
DEFAULT_CHECKPOINT = (
    ROOT / "data" / "interim" / "kodepos-dev-jabar-checkpoint.json"
)
COMPARISON_FIELDS = (
    "village_code",
    "api_village_name",
    "diskominfo_village_name",
    "odj_village_name",
    "api_postal_code",
    "diskominfo_postal_code",
    "odj_postal_code",
    "diskominfo_vs_open_data_jabar",
    "api_vs_diskominfo",
    "api_vs_odj",
    "comparison_status",
    "postal_review_required",
    "name_difference",
    "note",
)


def _request_page_once(
    *,
    api_key: str,
    after: str | None,
    page_size: int,
    timeout: float,
    opener: Callable[..., BinaryIO],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    parameters = {"q": SEARCH_QUERY, "first": str(page_size)}
    if after:
        parameters["after"] = after
    url = f"{API_BASE_URL}/search?{urlencode(parameters)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
        },
    )
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise KodeposAPIError("Kodepos.dev search returned an unsuccessful response")
    rows = payload.get("data")
    pagination = payload.get("pagination")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise KodeposAPIError("Kodepos.dev search response has invalid data")
    if not isinstance(pagination, dict):
        raise KodeposAPIError("Kodepos.dev search response has no pagination object")
    return rows, pagination, url


def fetch_search_page(
    *,
    api_key: str,
    after: str | None,
    page_size: int = MAX_PAGE_SIZE,
    timeout: float = 30.0,
    retries: int = 4,
    opener: Callable[..., BinaryIO] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Fetch one search page with bounded retries for transient failures."""

    if not api_key:
        raise KodeposAPIError("KODEPOS_API_KEY is not set")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise KodeposAPIError(f"page size must be between 1 and {MAX_PAGE_SIZE}")
    if retries < 0 or retries > 8:
        raise KodeposAPIError("retries must be between 0 and 8")
    for attempt in range(retries + 1):
        try:
            return _request_page_once(
                api_key=api_key,
                after=after,
                page_size=page_size,
                timeout=timeout,
                opener=opener,
            )
        except HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retryable or attempt == retries:
                raise KodeposAPIError(
                    f"Kodepos.dev search failed (HTTP {error.code}): "
                    f"{_error_detail(error)}"
                ) from error
            retry_after = error.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.isdigit() else 2**attempt
        except URLError as error:
            if attempt == retries:
                raise KodeposAPIError(
                    f"Kodepos.dev search failed: {error.reason}"
                ) from error
            delay = 2**attempt
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise KodeposAPIError("Kodepos.dev search returned invalid JSON") from error
        sleeper(min(max(delay, 0.5), 30.0))
    raise AssertionError("unreachable")


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_checkpoint(
    path: Path, *, snapshot: str
) -> tuple[list[dict[str, str]], str | None, int | None, bool]:
    if not path.exists():
        return [], None, None, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise KodeposAPIError(f"invalid checkpoint JSON: {path}") from error
    if payload.get("snapshot") != snapshot or payload.get("query") != SEARCH_QUERY:
        raise KodeposAPIError(
            "checkpoint snapshot/query differs; use --restart or the original snapshot"
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise KodeposAPIError("checkpoint rows are invalid")
    normalized = [
        {field: str(row.get(field, "")) for field in CROSSCHECK_FIELDS}
        for row in rows
    ]
    total = payload.get("expected_total")
    if total is not None and not isinstance(total, int):
        raise KodeposAPIError("checkpoint expected_total is invalid")
    cursor = payload.get("next_cursor") or None
    complete = payload.get("complete") is True
    return normalized, cursor, total, complete


def fetch_all_jabar(
    *,
    api_key: str,
    snapshot: str,
    checkpoint: Path,
    page_size: int,
    max_pages: int,
    delay: float,
    timeout: float,
    retries: int,
    page_fetcher: Callable[..., tuple[list[dict[str, Any]], dict[str, Any], str]] = fetch_search_page,
) -> list[dict[str, str]]:
    rows, after, expected_total, complete = _load_checkpoint(
        checkpoint, snapshot=snapshot
    )
    if complete:
        return rows
    seen = {row["village_code"] for row in rows}
    if len(seen) != len(rows):
        raise KodeposAPIError("checkpoint contains duplicate village codes")
    for page_number in range(1, max_pages + 1):
        page, pagination, page_url = page_fetcher(
            api_key=api_key,
            after=after,
            page_size=page_size,
            timeout=timeout,
            retries=retries,
        )
        normalized_page = [
            crosscheck_row(item, snapshot=snapshot, evidence_url=page_url)
            for item in page
        ]
        wrong_province = [
            row["village_code"]
            for row in normalized_page
            if row["province_code"] != PROVINCE_CODE
        ]
        if wrong_province:
            raise KodeposAPIError(
                f"search returned non-Jawa-Barat codes: {wrong_province[:3]}"
            )
        duplicates = [row["village_code"] for row in normalized_page if row["village_code"] in seen]
        if duplicates:
            raise KodeposAPIError(
                f"pagination returned duplicate codes: {duplicates[:3]}"
            )
        rows.extend(normalized_page)
        seen.update(row["village_code"] for row in normalized_page)
        page_total = pagination.get("total")
        if isinstance(page_total, int) and expected_total is None:
            # The live API reports a decreasing remainder after the first
            # cursor, so only the first page's total is the full result count.
            expected_total = page_total
        has_next = pagination.get("hasNextPage") is True
        next_cursor = pagination.get("endCursor") if has_next else None
        if has_next and (not isinstance(next_cursor, str) or not next_cursor or next_cursor == after):
            raise KodeposAPIError("pagination cursor did not advance")
        _write_json_atomic(
            checkpoint,
            {
                "complete": not has_next,
                "expected_total": expected_total,
                "next_cursor": next_cursor,
                "query": SEARCH_QUERY,
                "rows": rows,
                "snapshot": snapshot,
            },
        )
        print(
            f"page {page_number}: collected {len(rows)}"
            + (f"/{expected_total}" if expected_total is not None else ""),
            flush=True,
        )
        if not has_next:
            if expected_total is not None and len(rows) != expected_total:
                raise KodeposAPIError(
                    f"completed with {len(rows)} rows, expected {expected_total}"
                )
            return rows
        after = next_cursor
        if delay:
            time.sleep(delay)
    raise KodeposAPIError(
        f"audit exceeded --max-pages={max_pages}; checkpoint can be resumed"
    )


def _source_relation(api_row: Mapping[str, str] | None, source_postal: str) -> str:
    if api_row is None:
        return "missing_in_api"
    if not source_postal:
        return "source_postal_missing"
    return "match" if api_row["postal_code"] == source_postal else "different"


def _local_source_relation(diskominfo_postal: str, odj_postal: str) -> str:
    if diskominfo_postal and odj_postal:
        return "match" if diskominfo_postal == odj_postal else "different"
    if diskominfo_postal:
        return "diskominfo_only"
    if odj_postal:
        return "open_data_jabar_only"
    return "both_missing"


def build_comparison(
    api_rows: Sequence[Mapping[str, str]],
    diskominfo_rows: Sequence[Mapping[str, str]],
    odj_rows: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    api = {
        canonical_village_code(row.get("village_code", "")): row
        for row in api_rows
        if canonical_village_code(row.get("village_code", ""))
    }
    diskominfo = {
        canonical_village_code(row.get("kemendagri_kelurahan_kode", "")): row
        for row in diskominfo_rows
        if row.get("kemendagri_kelurahan_kode", "").strip() != PLACEHOLDER_CODE
        and canonical_village_code(row.get("kemendagri_kelurahan_kode", ""))
    }
    odj = {
        canonical_village_code(row.get("kemendagri_kode_desa_kelurahan", "")): row
        for row in odj_rows
        if row.get("kode_kemendagri_provinsi", "").strip() == PROVINCE_CODE
        and canonical_village_code(row.get("kemendagri_kode_desa_kelurahan", ""))
    }
    result: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for code in sorted(set(api) | set(diskominfo) | set(odj)):
        api_row = api.get(code)
        new = diskominfo.get(code, {})
        old = odj.get(code, {})
        api_postal = clean_postal(api_row.get("postal_code", "")) if api_row else ""
        new_postal = clean_postal(new.get("kode_pos", ""))
        old_postal = clean_postal(old.get("kode_pos", ""))
        new_relation = _source_relation(api_row, new_postal)
        old_relation = _source_relation(api_row, old_postal)
        if api_row is None:
            status = "missing_in_api"
        elif not new and not old:
            status = "api_extra"
        elif new_relation == "match" and old_relation == "match":
            status = "all_match"
        elif new_relation == "match":
            status = "api_matches_diskominfo"
        elif old_relation == "match":
            status = "api_matches_odj"
        elif new_relation == "source_postal_missing" and old_relation == "source_postal_missing":
            status = "api_only"
        else:
            status = "api_differs_available_sources"
        api_name = api_row.get("village_name", "") if api_row else ""
        new_name = new.get("kemendagri_kelurahan_nama", "")
        old_name = old.get("kemendagri_nama_desa_kelurahan", "")
        name_difference = any(
            value and normalize_name(value) != normalize_name(api_name)
            for value in (new_name, old_name)
        ) if api_name else bool(new_name or old_name)
        counts[status] += 1
        note = ""
        if status == "api_differs_available_sources":
            note = "API postal code differs from every available source postal code."
        elif status == "missing_in_api":
            note = "Government-source village code was not returned by the API search."
        elif status == "api_extra":
            note = "API village code was not present in either local government-source view."
        result.append(
            {
                "village_code": code,
                "api_village_name": api_name,
                "diskominfo_village_name": new_name,
                "odj_village_name": old_name,
                "api_postal_code": api_postal,
                "diskominfo_postal_code": new_postal,
                "odj_postal_code": old_postal,
                "diskominfo_vs_open_data_jabar": _local_source_relation(
                    new_postal, old_postal
                ),
                "api_vs_diskominfo": new_relation,
                "api_vs_odj": old_relation,
                "comparison_status": status,
                "postal_review_required": "no" if status == "all_match" else "yes",
                "name_difference": "yes" if name_difference else "no",
                "note": note,
            }
        )
    return result, dict(sorted(counts.items()))


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COMPARISON_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-full-jabar", action="store_true")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--odj", type=Path, default=DEFAULT_ODJ)
    parser.add_argument("--diskominfo", type=Path, default=DEFAULT_DISKOMINFO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--differences", type=Path, default=DEFAULT_DIFFERENCES)
    parser.add_argument("--priority-review", type=Path, default=DEFAULT_PRIORITY_REVIEW)
    parser.add_argument("--local-differences", type=Path, default=DEFAULT_LOCAL_DIFFERENCES)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--page-size", type=int, default=MAX_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=MAX_ALLOWED_PAGES)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--restart", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.confirm_full_jabar:
            raise KodeposAPIError(
                "--confirm-full-jabar is required because API requests consume credits"
            )
        if not 1 <= args.max_pages <= MAX_ALLOWED_PAGES:
            raise KodeposAPIError(
                f"--max-pages must be between 1 and {MAX_ALLOWED_PAGES}"
            )
        if args.delay < 0:
            raise KodeposAPIError("--delay may not be negative")
        if args.restart:
            args.checkpoint.unlink(missing_ok=True)
        api_key = load_api_key(args.env_file)
        if not api_key:
            raise KodeposAPIError("KODEPOS_API_KEY is not set")
        api_rows = fetch_all_jabar(
            api_key=api_key,
            snapshot=args.snapshot,
            checkpoint=args.checkpoint,
            page_size=args.page_size,
            max_pages=args.max_pages,
            delay=args.delay,
            timeout=args.timeout,
            retries=args.retries,
        )
        for row in api_rows:
            row["note"] = (
                "Province-wide paginated Kodepos.dev REST audit; internal "
                "validation evidence only, never a silent canonical override."
            )
        write_crosscheck(args.output, api_rows)
        _, diskominfo = read_csv(args.diskominfo)
        _, odj = read_csv(args.odj)
        comparison, counts = build_comparison(api_rows, diskominfo, odj)
        differences = [
            row for row in comparison if row["postal_review_required"] == "yes"
        ]
        priority_review = [
            row
            for row in comparison
            if row["comparison_status"]
            in {"api_differs_available_sources", "api_extra", "missing_in_api"}
        ]
        local_differences = [
            row
            for row in comparison
            if row["diskominfo_vs_open_data_jabar"] != "match"
            and row["comparison_status"] != "api_extra"
        ]
        _write_csv(args.comparison, comparison)
        _write_csv(args.differences, differences)
        _write_csv(args.priority_review, priority_review)
        _write_csv(args.local_differences, local_differences)
        _write_json_atomic(
            args.summary,
            {
                "api_rows": len(api_rows),
                "comparison_rows": len(comparison),
                "comparison_status_counts": counts,
                "differences_rows": len(differences),
                "priority_review_rows": len(priority_review),
                "local_differences_rows": len(local_differences),
                "local_source_status_counts": dict(
                    sorted(
                        Counter(
                            row["diskominfo_vs_open_data_jabar"]
                            for row in comparison
                            if row["comparison_status"] != "api_extra"
                        ).items()
                    )
                ),
                "input_sha256": {
                    "diskominfo": file_sha256(args.diskominfo),
                    "odj": file_sha256(args.odj),
                },
                "output_sha256": {
                    "api": file_sha256(args.output),
                    "comparison": file_sha256(args.comparison),
                    "differences": file_sha256(args.differences),
                    "priority_review": file_sha256(args.priority_review),
                    "local_differences": file_sha256(args.local_differences),
                },
                "query": SEARCH_QUERY,
                "snapshot": args.snapshot,
            },
        )
    except (KodeposAPIError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(json.loads(args.summary.read_text()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

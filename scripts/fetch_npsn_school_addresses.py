#!/usr/bin/env python3
"""Fetch NPSN public-school address rows for Jawa Barat (ALM-012 base pool).

Pulls SD and SMA rows from the Open Data Jabar "bigdata" endpoints published
by Dinas Pendidikan Provinsi Jawa Barat. The published `?download=csv` export
returns an HTTP 403 Cloudflare challenge from this environment (the same
finding already recorded for `open_data_jabar_postal_2023` in
data/sources.json); the paginated JSON endpoint works when the request
includes the same Referer/Origin/Accept headers a normal browser page load
sends, so this script uses that path instead. See data/sources.md for the
documented acquisition exception.

This script only fetches and stores raw rows. It does not select benchmark
candidates or write any human-facing text -- see
scripts/build_public_address_benchmark_candidates.py for that step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "interim" / "school-address-benchmark"
REFERER = "https://opendata.jabarprov.go.id/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "ALAMATIN-school-address-fetch/1.0 (+https://github.com/yongkytristan/ALAMATIN)"
)
LEVELS: dict[str, dict[str, str]] = {
    "sd": {
        "source_id": "open_data_jabar_npsn_sd_2023",
        "endpoint": (
            "https://data.jabarprov.go.id/api-backend/bigdata/disdik/"
            "dftr_kd_sklh_dsr_sd_brdsrkn_sts_sklh_dan_kcmtn_di_jawa_barat"
        ),
    },
    "sma": {
        "source_id": "open_data_jabar_npsn_sma_2023",
        "endpoint": (
            "https://data.jabarprov.go.id/api-backend/bigdata/disdik/"
            "od_20078_daftar_nomor_pokok_sekolah_nasional_npsn_sekolah_m_v1"
        ),
    },
}
REQUIRED_ROW_FIELDS = (
    "npsn",
    "nama_sekolah",
    "status_sekolah",
    "alamat_sekolah",
    "nama_kabupaten_kota",
    "kemendagri_nama_kecamatan",
    "tahun",
)


class SchoolFetchError(RuntimeError):
    """Raised when the school-address fetch cannot proceed safely."""


def _fetch_page(endpoint: str, *, skip: int, limit: int, timeout: float, retries: int) -> dict[str, Any]:
    query = urlencode({"limit": limit, "skip": skip})
    request = Request(
        f"{endpoint}?{query}",
        headers={
            "Accept": "application/json",
            "Referer": REFERER,
            "Origin": REFERER.rstrip("/"),
            "User-Agent": USER_AGENT,
        },
    )
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                charset = response.headers.get_content_charset() or "utf-8"
                payload = json.loads(response.read().decode(charset))
            if payload.get("error"):
                raise SchoolFetchError(f"remote reported an error: {payload}")
            return payload
        except HTTPError as error:
            if error.code in {403, 429}:
                raise SchoolFetchError(
                    f"remote access stopped with HTTP {error.code}; do not bypass"
                ) from error
            if error.code < 500 or attempt == retries:
                raise SchoolFetchError(
                    f"request skip={skip} failed with HTTP {error.code}"
                ) from error
        except (TimeoutError, URLError, json.JSONDecodeError) as error:
            if attempt == retries:
                raise SchoolFetchError(
                    f"request skip={skip} failed after {retries} attempts: {error}"
                ) from error
        time.sleep(min(2**attempt, 10))
    raise AssertionError("retry loop ended unexpectedly")


def fetch_level(
    level: str, *, limit: int, delay: float, timeout: float, retries: int
) -> dict[str, Any]:
    endpoint = LEVELS[level]["endpoint"]
    source_id = LEVELS[level]["source_id"]
    rows: list[dict[str, Any]] = []
    skip = 0
    total_reported: int | None = None
    while True:
        page = _fetch_page(endpoint, skip=skip, limit=limit, timeout=timeout, retries=retries)
        page_rows = page.get("data", [])
        meta = page.get("meta", {})
        total_reported = meta.get("total_record", total_reported)
        for row in page_rows:
            missing = [field for field in REQUIRED_ROW_FIELDS if field not in row]
            if missing:
                raise SchoolFetchError(
                    f"{level} row at skip={skip} missing fields: {', '.join(missing)}"
                )
            rows.append(row)
        print(
            f"level={level} skip={skip} fetched={len(page_rows)} "
            f"total_so_far={len(rows)}/{total_reported}",
            flush=True,
        )
        skip += limit
        if not page_rows or (total_reported is not None and skip >= total_reported):
            break
        time.sleep(delay)

    if total_reported is not None and len(rows) != total_reported:
        raise SchoolFetchError(
            f"{level}: fetched {len(rows)} rows but source reported {total_reported}"
        )

    return {
        "schema_version": "1.0.0",
        "source_id": source_id,
        "endpoint": endpoint,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_record_reported": total_reported,
        "row_count": len(rows),
        "rows": rows,
    }


def write_json_atomic(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", nargs="+", choices=sorted(LEVELS), default=sorted(LEVELS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.limit < 1:
            raise SchoolFetchError("--limit must be positive")
        summary: dict[str, Any] = {}
        for level in args.levels:
            output_path = args.output_dir / f"npsn-{level}-raw.json"
            if output_path.exists() and not args.force:
                raise SchoolFetchError(
                    f"refusing to overwrite {output_path}; pass --force explicitly"
                )
            payload = fetch_level(
                level,
                limit=args.limit,
                delay=args.delay,
                timeout=args.timeout,
                retries=args.retries,
            )
            checksum = write_json_atomic(output_path, payload)
            summary[level] = {
                "output": str(output_path),
                "row_count": payload["row_count"],
                "sha256": checksum,
            }
    except (OSError, SchoolFetchError) as error:
        print(f"error: {error}", file=sys.stderr, flush=True)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

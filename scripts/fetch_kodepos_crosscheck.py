#!/usr/bin/env python3
"""Fetch bounded Kodepos.dev REST spot checks into the cross-check CSV contract.

The API key is read from ``KODEPOS_API_KEY`` or a local ignored ``.env`` file.
It is never accepted as a command-line argument or written to output. This
command is intentionally bounded to selected village codes; it is not a
bulk-dataset downloader.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
API_BASE_URL = "https://api.kodepos.dev/kodepos/api"
SOURCE_ID = "kodepos_dev_rest_api"
USER_AGENT = "ALAMATIN-kodepos-crosscheck/1.0 (+https://github.com/yongkytristan/ALAMATIN)"
MAX_ALLOWED_REQUESTS = 100
REGION_CODE_DIGITS = re.compile(r"^\d{10}$")
POSTAL_CODE = re.compile(r"^\d{5}$")
CROSSCHECK_FIELDS = (
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
)


class KodeposAPIError(RuntimeError):
    """Raised for invalid input or a failed/invalid Kodepos.dev response."""


def load_api_key(env_file: Path) -> str:
    """Read the key from the process environment, then a minimal dotenv file."""

    environment_value = os.environ.get("KODEPOS_API_KEY", "").strip()
    if environment_value:
        return environment_value
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if not separator or name.strip() != "KODEPOS_API_KEY":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not value or "\x00" in value:
            raise KodeposAPIError(
                f"{env_file}:{line_number}: KODEPOS_API_KEY has an invalid value"
            )
        return value
    return ""


def normalize_village_code(value: str) -> str:
    """Return a dotted 10-digit Kemendagri village code."""

    digits = re.sub(r"\D", "", value.strip())
    if not REGION_CODE_DIGITS.fullmatch(digits):
        raise KodeposAPIError(f"invalid village code: {value!r}")
    return f"{digits[:2]}.{digits[2:4]}.{digits[4:6]}.{digits[6:]}"


def load_village_codes(values: Iterable[str], codes_file: Path | None) -> list[str]:
    """Load, normalize, deduplicate, and sort explicitly selected codes."""

    candidates = list(values)
    if codes_file is not None:
        try:
            candidates.extend(codes_file.read_text(encoding="utf-8").splitlines())
        except FileNotFoundError as error:
            raise KodeposAPIError(f"codes file not found: {codes_file}") from error
    codes = sorted(
        {
            normalize_village_code(value)
            for value in candidates
            if value.strip() and not value.lstrip().startswith("#")
        }
    )
    if not codes:
        raise KodeposAPIError("at least one village code is required")
    return codes


def _error_detail(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return error.reason or "HTTP request failed"
    api_error = payload.get("error", {}) if isinstance(payload, dict) else {}
    code = api_error.get("code", "HTTP_ERROR")
    message = api_error.get("message", error.reason or "HTTP request failed")
    return f"{code}: {message}"


def fetch_subdistrict(
    village_code: str,
    api_key: str,
    *,
    timeout: float = 30.0,
    opener: Callable[..., BinaryIO] = urlopen,
) -> tuple[dict[str, Any], str]:
    """Fetch one village detail and return its data plus the evidence URL."""

    code = normalize_village_code(village_code)
    if not api_key:
        raise KodeposAPIError("KODEPOS_API_KEY is not set")
    url = f"{API_BASE_URL}/subdistricts/{quote(code, safe='')}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise KodeposAPIError(
            f"Kodepos.dev request failed for {code} (HTTP {error.code}): "
            f"{_error_detail(error)}"
        ) from error
    except URLError as error:
        raise KodeposAPIError(
            f"Kodepos.dev request failed for {code}: {error.reason}"
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KodeposAPIError(
            f"Kodepos.dev returned invalid JSON for {code}"
        ) from error

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise KodeposAPIError(f"Kodepos.dev returned an unsuccessful response for {code}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise KodeposAPIError(f"Kodepos.dev response has no object data for {code}")
    return data, url


def _region_from(
    field: str, *containers: Any
) -> Mapping[str, Any]:
    """Resolve documented, nested-ancestry, or flat region response shapes."""

    for container in containers:
        if not isinstance(container, dict):
            continue
        nested = container.get(field)
        if isinstance(nested, dict) and nested.get("code") and nested.get("name"):
            return nested
        code = container.get(f"{field}Code") or container.get(f"{field}_code")
        name = container.get(f"{field}Name") or container.get(f"{field}_name")
        if code and name:
            return {"code": code, "name": name}
    top_level = containers[0] if containers and isinstance(containers[0], dict) else {}
    available = ", ".join(sorted(str(key) for key in top_level)) or "none"
    raise KodeposAPIError(
        f"Kodepos.dev response has invalid {field}; available data fields: {available}"
    )


def crosscheck_row(
    data: Mapping[str, Any], *, snapshot: str, evidence_url: str
) -> dict[str, str]:
    """Normalize one API object to the hierarchy builder's CSV contract."""

    district_container = data.get("district")
    district = _region_from("district", data)
    city = _region_from("city", data, district_container)
    city_container = data.get("city")
    if not isinstance(city_container, dict):
        city_container = (
            district_container.get("city")
            if isinstance(district_container, dict)
            else None
        )
    province = _region_from(
        "province", data, city_container, district_container
    )
    village_code = normalize_village_code(str(data.get("code", "")))
    village_name = str(data.get("name", "")).strip()
    postal_code = str(data.get("postalCode", "")).strip()
    if not snapshot.strip():
        raise KodeposAPIError("snapshot is required")
    if not village_name:
        raise KodeposAPIError(f"Kodepos.dev response has no village name for {village_code}")
    if not POSTAL_CODE.fullmatch(postal_code):
        raise KodeposAPIError(
            f"Kodepos.dev response has invalid postal code for {village_code}"
        )
    return {
        "source_id": SOURCE_ID,
        "snapshot": snapshot.strip(),
        "province_code": str(province["code"]).strip(),
        "province_name": str(province["name"]).strip(),
        "city_code": str(city["code"]).strip(),
        "city_name": str(city["name"]).strip(),
        "district_code": str(district["code"]).strip(),
        "district_name": str(district["name"]).strip(),
        "village_code": village_code,
        "village_name": village_name,
        "postal_code": postal_code,
        "evidence_url": evidence_url,
        "note": (
            "Bounded Kodepos.dev REST API spot check; validation evidence only, "
            "never a silent canonical override."
        ),
    }


def write_crosscheck(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CROSSCHECK_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--village-code", action="append", default=[])
    parser.add_argument("--codes-file", type=Path)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env",
        help="Ignored dotenv file used only when KODEPOS_API_KEY is not exported",
    )
    parser.add_argument("--snapshot", required=True, help="Explicit API access date/version")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "interim" / "kodepos-dev-crosscheck.csv",
    )
    parser.add_argument("--max-requests", type=int, default=25)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        codes = load_village_codes(args.village_code, args.codes_file)
        if not 1 <= args.max_requests <= MAX_ALLOWED_REQUESTS:
            raise KodeposAPIError(
                f"--max-requests must be between 1 and {MAX_ALLOWED_REQUESTS}"
            )
        if len(codes) > args.max_requests:
            raise KodeposAPIError(
                f"selected {len(codes)} codes but --max-requests is {args.max_requests}"
            )
        if args.delay < 0:
            raise KodeposAPIError("--delay may not be negative")
        api_key = load_api_key(args.env_file)
        if not api_key:
            raise KodeposAPIError(
                f"KODEPOS_API_KEY is not set in the environment or {args.env_file}"
            )

        rows: list[dict[str, str]] = []
        for index, code in enumerate(codes):
            data, evidence_url = fetch_subdistrict(
                code, api_key, timeout=args.timeout
            )
            rows.append(
                crosscheck_row(
                    data,
                    snapshot=args.snapshot,
                    evidence_url=evidence_url,
                )
            )
            if index + 1 < len(codes) and args.delay:
                time.sleep(args.delay)
        write_crosscheck(args.output, rows)
    except (KodeposAPIError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"wrote {len(rows)} bounded Kodepos.dev observations")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

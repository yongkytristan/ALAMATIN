#!/usr/bin/env python3
"""List, inspect, and reproducibly acquire approved ALAMATIN data sources.

The command intentionally has no bulk/default download mode. A caller must name
one approved source, and downloaded artifacts stay in ignored data/raw paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data" / "sources.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "raw"
SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
CHECKSUM_LENGTH = {"md5": 32, "sha256": 64}
USER_AGENT = "ALAMATIN-source-acquisition/1.0 (+https://github.com/yongkytristan/ALAMATIN)"


class CatalogError(ValueError):
    """Raised when the source catalog violates its contract."""


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CatalogError(f"catalog not found: {path}") from error
    except json.JSONDecodeError as error:
        raise CatalogError(f"catalog is not valid JSON: {error}") from error

    required_top_level = {"catalog_version", "reviewed_at", "purpose_vocabulary", "sources"}
    missing = required_top_level - catalog.keys()
    if missing:
        raise CatalogError(f"catalog missing fields: {', '.join(sorted(missing))}")
    if not isinstance(catalog["sources"], list) or not catalog["sources"]:
        raise CatalogError("catalog sources must be a non-empty list")

    allowed_purposes = set(catalog["purpose_vocabulary"])
    seen_ids: set[str] = set()
    for source in catalog["sources"]:
        source_id = source.get("source_id", "")
        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            raise CatalogError(f"invalid source_id: {source_id!r}")
        if source_id in seen_ids:
            raise CatalogError(f"duplicate source_id: {source_id}")
        seen_ids.add(source_id)

        required_source = {
            "name",
            "decision",
            "purposes",
            "publisher",
            "landing_page_url",
            "accessed_at",
            "snapshot",
            "license_review",
            "pii_review",
            "acquisition",
            "transformation_plan",
            "limitations",
        }
        missing_source = required_source - source.keys()
        if missing_source:
            fields = ", ".join(sorted(missing_source))
            raise CatalogError(f"{source_id} missing fields: {fields}")
        if source["decision"] not in {"use", "hold", "reject"}:
            raise CatalogError(f"{source_id} has invalid decision")
        unknown_purposes = set(source["purposes"]) - allowed_purposes
        if unknown_purposes:
            purposes = ", ".join(sorted(unknown_purposes))
            raise CatalogError(f"{source_id} has unknown purposes: {purposes}")
        if not source["landing_page_url"].startswith("https://"):
            raise CatalogError(f"{source_id} landing page must use HTTPS")
        _validate_acquisition(source_id, source["acquisition"])

    return catalog


def _validate_acquisition(source_id: str, acquisition: dict[str, Any]) -> None:
    mode = acquisition.get("mode")
    if mode == "download":
        artifacts = acquisition.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise CatalogError(f"{source_id} download mode requires artifacts")
        artifact_ids: set[str] = set()
        for artifact in artifacts:
            artifact_id = artifact.get("artifact_id", "")
            if not SOURCE_ID_PATTERN.fullmatch(artifact_id):
                raise CatalogError(f"{source_id} has invalid artifact_id: {artifact_id!r}")
            if artifact_id in artifact_ids:
                raise CatalogError(f"{source_id} has duplicate artifact_id: {artifact_id}")
            artifact_ids.add(artifact_id)
            if not artifact.get("url", "").startswith("https://"):
                raise CatalogError(f"{source_id}/{artifact_id} URL must use HTTPS")
            filename = artifact.get("filename", "")
            if not filename or Path(filename).name != filename:
                raise CatalogError(f"{source_id}/{artifact_id} has unsafe filename")
            checksum_url = artifact.get("checksum_url")
            checksum_algorithm = artifact.get("checksum_algorithm")
            if bool(checksum_url) != bool(checksum_algorithm):
                raise CatalogError(
                    f"{source_id}/{artifact_id} must set checksum_url and "
                    "checksum_algorithm together"
                )
            if checksum_url and not checksum_url.startswith("https://"):
                raise CatalogError(f"{source_id}/{artifact_id} checksum URL must use HTTPS")
            if checksum_algorithm and checksum_algorithm not in CHECKSUM_LENGTH:
                raise CatalogError(f"{source_id}/{artifact_id} has unsupported checksum")
    elif mode == "local":
        local_path = acquisition.get("path", "")
        if not local_path or Path(local_path).is_absolute() or ".." in Path(local_path).parts:
            raise CatalogError(f"{source_id} has unsafe local path")
    elif mode == "none":
        if not acquisition.get("reason"):
            raise CatalogError(f"{source_id} acquisition hold needs a reason")
    else:
        raise CatalogError(f"{source_id} has invalid acquisition mode: {mode!r}")


def source_by_id(catalog: dict[str, Any], source_id: str) -> dict[str, Any]:
    for source in catalog["sources"]:
        if source["source_id"] == source_id:
            return source
    raise CatalogError(f"unknown source_id: {source_id}")


def _open_url(url: str) -> BinaryIO:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    return urlopen(request, timeout=60)  # noqa: S310 - URLs are catalog-controlled HTTPS


def _remote_checksum(artifact: dict[str, Any]) -> str | None:
    checksum_url = artifact.get("checksum_url")
    if not checksum_url:
        return None
    algorithm = artifact["checksum_algorithm"]
    with _open_url(checksum_url) as response:
        content = response.read(4096).decode("ascii", errors="strict")
    length = CHECKSUM_LENGTH[algorithm]
    match = re.search(rf"\b[0-9a-fA-F]{{{length}}}\b", content)
    if not match:
        raise CatalogError(f"no {algorithm} checksum found at {checksum_url}")
    return match.group(0).lower()


def _download_artifact(artifact: dict[str, Any], destination: Path) -> dict[str, Any]:
    upstream_algorithm = artifact.get("checksum_algorithm")
    expected_upstream = _remote_checksum(artifact)
    hashes = {"sha256": hashlib.sha256()}
    if upstream_algorithm:
        hashes[upstream_algorithm] = hashlib.new(upstream_algorithm)

    temporary = destination.with_name(f".{destination.name}.part")
    byte_count = 0
    try:
        with _open_url(artifact["url"]) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                byte_count += len(chunk)
                for digest in hashes.values():
                    digest.update(chunk)
        actual_upstream = hashes[upstream_algorithm].hexdigest() if upstream_algorithm else None
        if expected_upstream and actual_upstream != expected_upstream:
            raise CatalogError(
                f"checksum mismatch for {artifact['artifact_id']}: "
                f"expected {expected_upstream}, got {actual_upstream}"
            )
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    result = {
        "artifact_id": artifact["artifact_id"],
        "filename": artifact["filename"],
        "url": artifact["url"],
        "bytes": byte_count,
        "sha256": hashes["sha256"].hexdigest(),
    }
    if expected_upstream:
        result["upstream_checksum"] = {
            "algorithm": upstream_algorithm,
            "value": expected_upstream,
            "url": artifact["checksum_url"],
        }
    return result


def fetch_source(
    catalog: dict[str, Any], source: dict[str, Any], output_dir: Path, force: bool
) -> Path:
    source_id = source["source_id"]
    if source["decision"] != "use":
        raise CatalogError(f"source {source_id} is {source['decision']}; acquisition is forbidden")
    if source["acquisition"]["mode"] != "download":
        raise CatalogError(f"source {source_id} is not a downloadable source")

    source_dir = output_dir.resolve() / source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = source_dir / "acquisition-manifest.json"
    artifact_records = []
    destinations = [
        source_dir / artifact["filename"]
        for artifact in source["acquisition"]["artifacts"]
    ]
    existing = [destination for destination in destinations if destination.exists()]
    if existing and not force:
        raise CatalogError(
            f"refusing to overwrite {existing[0]}; pass --force explicitly"
        )
    # An old manifest must never describe a partially refreshed set of files.
    if force:
        manifest_path.unlink(missing_ok=True)

    for artifact in source["acquisition"]["artifacts"]:
        destination = source_dir / artifact["filename"]
        print(
            f"downloading {source_id}/{artifact['artifact_id']} -> {destination}",
            file=sys.stderr,
        )
        artifact_records.append(_download_artifact(artifact, destination))

    manifest = {
        "manifest_version": "1.0.0",
        "catalog_version": catalog["catalog_version"],
        "source_id": source_id,
        "source_snapshot": source["snapshot"],
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifacts": artifact_records,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def verify_local(source: dict[str, Any]) -> Path:
    source_id = source["source_id"]
    if source["decision"] != "use":
        raise CatalogError(f"source {source_id} is not approved for use")
    if source["acquisition"]["mode"] != "local":
        raise CatalogError(f"source {source_id} is not a local source")
    path = (ROOT / source["acquisition"]["path"]).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise CatalogError(f"local source is missing or outside the repository: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list source decisions")
    list_parser.add_argument("--decision", choices=("use", "hold", "reject"))

    show_parser = subparsers.add_parser("show", help="print one catalog record")
    show_parser.add_argument("source_id")

    fetch_parser = subparsers.add_parser("fetch", help="download one approved source")
    fetch_parser.add_argument("source_id")
    fetch_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    fetch_parser.add_argument("--force", action="store_true")

    verify_parser = subparsers.add_parser("verify-local", help="verify one local source path")
    verify_parser.add_argument("source_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        if args.command == "list":
            for source in catalog["sources"]:
                if args.decision and source["decision"] != args.decision:
                    continue
                purposes = ",".join(source["purposes"])
                print(f"{source['source_id']}\t{source['decision']}\t{purposes}")
        elif args.command == "show":
            source = source_by_id(catalog, args.source_id)
            print(json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "fetch":
            source = source_by_id(catalog, args.source_id)
            manifest_path = fetch_source(catalog, source, args.output_dir, args.force)
            print(manifest_path)
        elif args.command == "verify-local":
            source = source_by_id(catalog, args.source_id)
            print(verify_local(source))
    except (CatalogError, OSError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

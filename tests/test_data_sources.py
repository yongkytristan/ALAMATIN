from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "sources.json"
SOURCES_DOC_PATH = ROOT / "data" / "sources.md"
DATASET_CARD_PATH = ROOT / "data" / "dataset_card.md"
sys.path.insert(0, str(ROOT / "scripts"))

from acquire_sources import (  # noqa: E402
    CatalogError,
    fetch_source,
    load_catalog,
    source_by_id,
    verify_local,
)


class DataSourceCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)
        cls.raw_catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.sources_doc = SOURCES_DOC_PATH.read_text(encoding="utf-8")
        cls.dataset_card = DATASET_CARD_PATH.read_text(encoding="utf-8")

    def test_catalog_has_stable_unique_source_ids(self) -> None:
        source_ids = [source["source_id"] for source in self.catalog["sources"]]
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertGreaterEqual(len(source_ids), 3)

    def test_required_use_cases_have_an_approved_source(self) -> None:
        approved_purposes = {
            purpose
            for source in self.catalog["sources"]
            if source["decision"] == "use"
            for purpose in source["purposes"]
        }
        self.assertTrue(
            {
                "administrative_hierarchy",
                "street_landmark_reference",
                "base_address_benchmark",
            }.issubset(approved_purposes)
        )

    def test_every_source_records_review_and_provenance(self) -> None:
        for source in self.catalog["sources"]:
            with self.subTest(source_id=source["source_id"]):
                self.assertTrue(source["snapshot"])
                self.assertTrue(source["accessed_at"])
                self.assertTrue(source["license_review"]["status"])
                self.assertTrue(source["license_review"]["redistribution"])
                self.assertTrue(source["pii_review"]["status"])
                self.assertTrue(source["limitations"])

    def test_source_ids_are_in_review_and_dataset_card(self) -> None:
        for source in self.catalog["sources"]:
            source_id = source["source_id"]
            with self.subTest(source_id=source_id):
                self.assertIn(f"`{source_id}`", self.sources_doc)
                self.assertIn(f"`{source_id}`", self.dataset_card)

    def test_downloads_are_explicit_https_and_local_only_destinations(self) -> None:
        for source in self.catalog["sources"]:
            acquisition = source["acquisition"]
            if acquisition["mode"] != "download":
                continue
            for artifact in acquisition["artifacts"]:
                with self.subTest(
                    source_id=source["source_id"], artifact=artifact["artifact_id"]
                ):
                    self.assertTrue(artifact["url"].startswith("https://"))
                    self.assertEqual(Path(artifact["filename"]).name, artifact["filename"])

    def test_local_benchmark_path_exists(self) -> None:
        source = source_by_id(self.catalog, "alamatin_synthetic_ner_review_v1")
        self.assertEqual(
            verify_local(source), ROOT / "tests" / "fixtures" / "ner_gold_examples.json"
        )

    def test_hold_source_cannot_be_mistaken_for_use(self) -> None:
        source = source_by_id(self.catalog, "pos_indonesia_postcode_search")
        self.assertEqual(source["decision"], "hold")
        self.assertEqual(source["acquisition"]["mode"], "none")
        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaisesRegex(CatalogError, "acquisition is forbidden"):
                fetch_source(self.catalog, source, Path(output_dir), force=False)

    def test_fetch_writes_artifact_and_sha256_manifest(self) -> None:
        payload = b"synthetic public source fixture\n"
        source = {
            "source_id": "test_public_source",
            "decision": "use",
            "snapshot": "test-v1",
            "acquisition": {
                "mode": "download",
                "artifacts": [
                    {
                        "artifact_id": "fixture",
                        "url": "https://example.invalid/source.bin",
                        "filename": "source.bin",
                    }
                ],
            },
        }
        with tempfile.TemporaryDirectory() as output_dir:
            with patch("acquire_sources._open_url", return_value=io.BytesIO(payload)):
                manifest_path = fetch_source(
                    {"catalog_version": "test-v1"},
                    source,
                    Path(output_dir),
                    force=False,
                )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact_path = manifest_path.parent / "source.bin"
            self.assertEqual(artifact_path.read_bytes(), payload)
            self.assertEqual(
                manifest["artifacts"][0]["sha256"], hashlib.sha256(payload).hexdigest()
            )

    def test_unknown_source_id_fails(self) -> None:
        with self.assertRaisesRegex(CatalogError, "unknown source_id"):
            source_by_id(self.catalog, "missing_source")

    def test_cli_lists_catalog_source_ids(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/acquire_sources.py", "list", "--decision", "use"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for source in self.raw_catalog["sources"]:
            if source["decision"] == "use":
                self.assertIn(source["source_id"], result.stdout)
        self.assertNotIn("pos_indonesia_postcode_search", result.stdout)


if __name__ == "__main__":
    unittest.main()

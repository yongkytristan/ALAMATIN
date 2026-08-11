from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_kodepos_crosscheck import (  # noqa: E402
    KodeposAPIError,
    crosscheck_row,
    fetch_subdistrict,
    load_api_key,
    load_village_codes,
    normalize_village_code,
    write_crosscheck,
)


API_DATA = {
    "code": "32.73.05.1002",
    "name": "Braga",
    "postalCode": "40111",
    "district": {"code": "32.73.05", "name": "Sumur Bandung"},
    "city": {"code": "32.73", "name": "Kota Bandung"},
    "province": {"code": "32", "name": "Jawa Barat"},
}


class KodeposRESTTest(unittest.TestCase):
    def test_api_key_loads_from_dotenv_without_overriding_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("KODEPOS_API_KEY='file-secret'\n", encoding="utf-8")
            previous = os.environ.get("KODEPOS_API_KEY")
            os.environ.pop("KODEPOS_API_KEY", None)
            try:
                self.assertEqual(load_api_key(path), "file-secret")
                os.environ["KODEPOS_API_KEY"] = "environment-secret"
                self.assertEqual(load_api_key(path), "environment-secret")
            finally:
                if previous is None:
                    os.environ.pop("KODEPOS_API_KEY", None)
                else:
                    os.environ["KODEPOS_API_KEY"] = previous

    def test_codes_are_normalized_deduplicated_and_sorted(self) -> None:
        self.assertEqual(normalize_village_code("3273051002"), "32.73.05.1002")
        self.assertEqual(
            load_village_codes(["32.73.05.1002", "3201011001", "3273051002"], None),
            ["32.01.01.1001", "32.73.05.1002"],
        )
        with self.assertRaises(KodeposAPIError):
            normalize_village_code("32.73")

    def test_fetch_uses_bearer_without_exposing_it_in_result(self) -> None:
        observed = {}

        def opener(request, *, timeout):
            observed["authorization"] = request.get_header("Authorization")
            observed["url"] = request.full_url
            observed["timeout"] = timeout
            return io.BytesIO(
                json.dumps({"success": True, "data": API_DATA}).encode("utf-8")
            )

        data, url = fetch_subdistrict(
            "3273051002", "test-secret", timeout=5, opener=opener
        )
        self.assertEqual(data, API_DATA)
        self.assertEqual(observed["authorization"], "Bearer test-secret")
        self.assertEqual(observed["timeout"], 5)
        self.assertEqual(url, observed["url"])
        self.assertNotIn("test-secret", url)

    def test_response_is_written_in_builder_crosscheck_contract(self) -> None:
        row = crosscheck_row(
            API_DATA,
            snapshot="2026-08-11",
            evidence_url="https://api.kodepos.dev/kodepos/api/subdistricts/32.73.05.1002",
        )
        self.assertEqual(row["source_id"], "kodepos_dev_rest_api")
        self.assertEqual(row["postal_code"], "40111")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crosscheck.csv"
            write_crosscheck(path, [row])
            with path.open(encoding="utf-8", newline="") as stream:
                written = list(csv.DictReader(stream))
        self.assertEqual(written, [row])

    def test_response_accepts_nested_ancestry_shape(self) -> None:
        nested = {
            "code": "32.73.05.1002",
            "name": "Braga",
            "postalCode": "40111",
            "district": {
                "code": "32.73.05",
                "name": "Sumur Bandung",
                "city": {
                    "code": "32.73",
                    "name": "Kota Bandung",
                    "province": {"code": "32", "name": "Jawa Barat"},
                },
            },
        }
        row = crosscheck_row(
            nested,
            snapshot="2026-08-11",
            evidence_url="https://example.invalid/detail",
        )
        self.assertEqual(row["province_name"], "Jawa Barat")
        self.assertEqual(row["city_code"], "32.73")

    def test_response_accepts_flat_hierarchy_shape(self) -> None:
        flat = {
            "code": "32.73.05.1002",
            "name": "Braga",
            "postalCode": "40111",
            "districtCode": "32.73.05",
            "districtName": "Sumur Bandung",
            "cityCode": "32.73",
            "cityName": "Kota Bandung",
            "provinceCode": "32",
            "provinceName": "Jawa Barat",
        }
        row = crosscheck_row(
            flat,
            snapshot="2026-08-11",
            evidence_url="https://example.invalid/detail",
        )
        self.assertEqual(row["district_name"], "Sumur Bandung")
        self.assertEqual(row["postal_code"], "40111")

    def test_cli_requires_environment_key_before_network_access(self) -> None:
        environment = dict(os.environ)
        environment.pop("KODEPOS_API_KEY", None)
        with tempfile.TemporaryDirectory() as directory:
            missing_env = Path(directory) / "missing.env"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/fetch_kodepos_crosscheck.py",
                    "--village-code",
                    "32.73.05.1002",
                    "--snapshot",
                    "2026-08-11",
                    "--env-file",
                    str(missing_env),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("KODEPOS_API_KEY is not set", result.stderr)


if __name__ == "__main__":
    unittest.main()

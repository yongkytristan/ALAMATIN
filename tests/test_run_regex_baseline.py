from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_regex_baseline", ROOT / "scripts" / "run_regex_baseline.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RunRegexBaselineTest(unittest.TestCase):
    def test_raises_on_empty_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.json"
            path.write_text(json.dumps({"examples": []}), encoding="utf-8")
            exit_code = MODULE.main(["--dataset", str(path)])
            self.assertEqual(exit_code, 2)

    def test_cli_writes_a_report_with_metrics_and_latency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset.json"
            payload = {
                "examples": [
                    {
                        "id": "X-1",
                        "tokens": ["Jl.", "Mawar", "No.", "7"],
                        "labels": ["B-JALAN", "I-JALAN", "B-NOMOR", "I-NOMOR"],
                    }
                ]
            }
            dataset_path.write_text(json.dumps(payload), encoding="utf-8")
            output_path = Path(directory) / "report.json"

            args = [
                sys.executable,
                "scripts/run_regex_baseline.py",
                "--dataset", str(dataset_path),
                "--output", str(output_path),
            ]
            result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["baseline"], "regex_baseline_v1_2")
            self.assertEqual(report["overall"]["f1"], 1.0)
            self.assertEqual(report["latency_ms"]["sample_count"], 1)

    def test_is_fully_deterministic_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "dataset.json"
            payload = {
                "examples": [
                    {"id": "X-1", "tokens": ["Jl.", "Mawar", "No.", "7"], "labels": ["B-JALAN", "I-JALAN", "B-NOMOR", "I-NOMOR"]},
                    {"id": "X-2", "tokens": ["Kp.", "Foo", "Kec.", "Bar"], "labels": ["B-JALAN", "I-JALAN", "B-KECAMATAN", "I-KECAMATAN"]},
                ]
            }
            dataset_path.write_text(json.dumps(payload), encoding="utf-8")

            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            MODULE.main(["--dataset", str(dataset_path), "--output", str(first)])
            MODULE.main(["--dataset", str(dataset_path), "--output", str(second)])

            first_report = json.loads(first.read_text(encoding="utf-8"))
            second_report = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(first_report["overall"], second_report["overall"])
            self.assertEqual(first_report["by_type"], second_report["by_type"])


if __name__ == "__main__":
    unittest.main()

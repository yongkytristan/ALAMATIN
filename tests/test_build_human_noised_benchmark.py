"""Tests for the ALM-012 annotation worksheet and assembly tool.

These tests exercise the pipeline's validation and assembly logic only, using
small hand-written fixture rows. They do not assert anything about what real
human annotators write and must never be mistaken for the actual benchmark.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_human_noised_benchmark",
    ROOT / "scripts" / "build_human_noised_benchmark.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


CANDIDATE_FIELDS = (
    "base_address_id",
    "source_id",
    "source_record_id",
    "school_level",
    "school_name",
    "status_sekolah",
    "kabupaten_kota",
    "kecamatan",
    "reference_address",
    "source_year",
)


class MakeTemplateTest(unittest.TestCase):
    def test_template_has_blank_annotation_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidates_path = Path(directory) / "candidates.csv"
            template_path = Path(directory) / "template.csv"
            _write_csv(
                candidates_path,
                CANDIDATE_FIELDS,
                [
                    {
                        "base_address_id": "npsn_sd_1",
                        "source_id": "open_data_jabar_npsn_sd_2023",
                        "source_record_id": "1",
                        "school_level": "SD",
                        "school_name": "SD N CONTOH",
                        "status_sekolah": "NEGERI",
                        "kabupaten_kota": "KABUPATEN BOGOR",
                        "kecamatan": "CIBINONG",
                        "reference_address": "JL. CONTOH RT 01 RW 02",
                        "source_year": "2023",
                    }
                ],
            )
            count = MODULE.make_template(candidates_path, template_path)
            self.assertEqual(count, 1)
            with template_path.open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["rewritten_address"], "")
            self.assertEqual(rows[0]["annotator_id"], "")
            self.assertEqual(rows[0]["reference_address"], "JL. CONTOH RT 01 RW 02")

    def test_raises_on_empty_candidate_pool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidates_path = Path(directory) / "candidates.csv"
            _write_csv(candidates_path, CANDIDATE_FIELDS, [])
            with self.assertRaises(MODULE.BenchmarkAssemblyError):
                MODULE.make_template(candidates_path, Path(directory) / "template.csv")


def _template_row(**overrides: str) -> dict[str, str]:
    row = {
        "base_address_id": "npsn_sd_1",
        "source_id": "open_data_jabar_npsn_sd_2023",
        "source_record_id": "1",
        "school_level": "SD",
        "reference_address": "JL. CONTOH RT 01 RW 02",
        "rewritten_address": "jl contoh rt 1 rw 2 dekat pasar",
        "annotator_id": "ANN-01",
        "notes": "",
    }
    row.update(overrides)
    return row


class ValidateCompletedRowsTest(unittest.TestCase):
    def test_valid_rows_have_no_problems(self) -> None:
        self.assertEqual(MODULE.validate_completed_rows([_template_row()]), [])

    def test_flags_empty_rewritten_address(self) -> None:
        problems = MODULE.validate_completed_rows([_template_row(rewritten_address="")])
        self.assertTrue(any("rewritten_address is empty" in problem for problem in problems))

    def test_flags_missing_annotator_id(self) -> None:
        problems = MODULE.validate_completed_rows([_template_row(annotator_id="")])
        self.assertTrue(any("annotator_id is empty" in problem for problem in problems))

    def test_flags_verbatim_copy_of_reference_address(self) -> None:
        row = _template_row(rewritten_address="JL. CONTOH RT 01 RW 02")
        problems = MODULE.validate_completed_rows([row])
        self.assertTrue(any("identical to reference_address" in problem for problem in problems))

    def test_flags_phone_number_like_sequences(self) -> None:
        row = _template_row(rewritten_address="jl contoh, hubungi 081234567890")
        problems = MODULE.validate_completed_rows([row])
        self.assertTrue(any("phone-number-like" in problem for problem in problems))

    def test_flags_duplicate_base_address_id(self) -> None:
        problems = MODULE.validate_completed_rows([_template_row(), _template_row()])
        self.assertTrue(any("duplicate base_address_id" in problem for problem in problems))


class AssembleTest(unittest.TestCase):
    def test_assemble_writes_benchmark_with_manifest_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            template_path = Path(directory) / "template.csv"
            _write_csv(template_path, MODULE.TEMPLATE_FIELDS, [_template_row()])
            benchmark_path = Path(directory) / "benchmark.json"
            summary_path = Path(directory) / "summary.json"

            MODULE.assemble(template_path, benchmark_path, summary_path)

            benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
            self.assertEqual(benchmark["example_count"], 1)
            example = benchmark["examples"][0]
            for field in ("base_address_id", "source_id", "source_record_id", "source_url", "annotator_id"):
                self.assertIn(field, example)
                self.assertTrue(example[field])
            self.assertNotIn("reference_address", example)

    def test_assemble_raises_and_does_not_write_on_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            template_path = Path(directory) / "template.csv"
            _write_csv(template_path, MODULE.TEMPLATE_FIELDS, [_template_row(annotator_id="")])
            benchmark_path = Path(directory) / "benchmark.json"
            summary_path = Path(directory) / "summary.json"

            with self.assertRaises(MODULE.BenchmarkAssemblyError):
                MODULE.assemble(template_path, benchmark_path, summary_path)
            self.assertFalse(benchmark_path.exists())


if __name__ == "__main__":
    unittest.main()

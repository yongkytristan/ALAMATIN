from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "compute_annotation_agreement", ROOT / "scripts" / "compute_annotation_agreement.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ParseSpansTest(unittest.TestCase):
    def test_parses_a_single_span(self) -> None:
        labels = MODULE.parse_spans("JALAN:0-2", token_count=4, base_address_id="x")
        self.assertEqual(labels, ["B-JALAN", "I-JALAN", "O", "O"])

    def test_parses_multiple_spans(self) -> None:
        labels = MODULE.parse_spans("JALAN:0-2;KECAMATAN:3-4", token_count=4, base_address_id="x")
        self.assertEqual(labels, ["B-JALAN", "I-JALAN", "O", "B-KECAMATAN"])

    def test_empty_spans_is_all_o(self) -> None:
        self.assertEqual(MODULE.parse_spans("", token_count=3, base_address_id="x"), ["O", "O", "O"])

    def test_raises_on_unknown_entity(self) -> None:
        with self.assertRaises(MODULE.AgreementError):
            MODULE.parse_spans("NOTREAL:0-1", token_count=2, base_address_id="x")

    def test_raises_on_out_of_range_span(self) -> None:
        with self.assertRaises(MODULE.AgreementError):
            MODULE.parse_spans("JALAN:0-9", token_count=2, base_address_id="x")

    def test_raises_on_malformed_span(self) -> None:
        with self.assertRaises(MODULE.AgreementError):
            MODULE.parse_spans("JALAN-0-1", token_count=2, base_address_id="x")


class MainIntegrationTest(unittest.TestCase):
    def test_accepts_a_semicolon_delimited_worksheet(self) -> None:
        # Excel with an Indonesian locale re-saves CSV with ';' as the
        # delimiter; a completed worksheet round-tripped through Excel must
        # still be readable.
        with tempfile.TemporaryDirectory() as directory:
            candidates_path = Path(directory) / "candidates.json"
            candidates_path.write_text(
                json.dumps(
                    {
                        "examples": [
                            {
                                "base_address_id": "npsn_sd_1",
                                "tokens": ["Jl.", "Mawar"],
                                "labels": ["B-JALAN", "I-JALAN"],
                                "flags": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            worksheet_path = Path(directory) / "worksheet.csv"
            worksheet_path.write_text(
                "base_address_id;indexed_tokens;spans;annotator_id;notes\n"
                "npsn_sd_1;0:Jl. 1:Mawar;JALAN:0-2;YT-01;\n",
                encoding="utf-8",
            )
            exit_code = MODULE.main(
                [
                    "--candidates", str(candidates_path),
                    "--worksheet", str(worksheet_path),
                    "--agreement", str(Path(directory) / "agreement.json"),
                    "--adjudication", str(Path(directory) / "adjudication.csv"),
                    "--human-labels", str(Path(directory) / "human.json"),
                ]
            )
            self.assertEqual(exit_code, 0)

    def test_perfect_agreement_yields_no_adjudication_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidates_path = Path(directory) / "candidates.json"
            candidates_path.write_text(
                json.dumps(
                    {
                        "examples": [
                            {
                                "base_address_id": "npsn_sd_1",
                                "tokens": ["Jl.", "Mawar"],
                                "labels": ["B-JALAN", "I-JALAN"],
                                "flags": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            worksheet_path = Path(directory) / "worksheet.csv"
            worksheet_path.write_text(
                "base_address_id,indexed_tokens,spans,annotator_id,notes\n"
                "npsn_sd_1,0:Jl. 1:Mawar,JALAN:0-2,YT-01,\n",
                encoding="utf-8",
            )
            agreement_path = Path(directory) / "agreement.json"
            adjudication_path = Path(directory) / "adjudication.csv"
            human_labels_path = Path(directory) / "human.json"

            exit_code = MODULE.main(
                [
                    "--candidates", str(candidates_path),
                    "--worksheet", str(worksheet_path),
                    "--agreement", str(agreement_path),
                    "--adjudication", str(adjudication_path),
                    "--human-labels", str(human_labels_path),
                ]
            )
            self.assertEqual(exit_code, 0)

            report = json.loads(agreement_path.read_text(encoding="utf-8"))
            self.assertEqual(report["overall"]["f1"], 1.0)
            self.assertEqual(report["disagreement_examples"], 0)

            with adjudication_path.open(encoding="utf-8") as stream:
                rows = stream.read().strip().splitlines()
            self.assertEqual(len(rows), 1)  # header only, no disagreements

    def test_disagreement_produces_an_adjudication_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidates_path = Path(directory) / "candidates.json"
            candidates_path.write_text(
                json.dumps(
                    {
                        "examples": [
                            {
                                "base_address_id": "npsn_sd_1",
                                "tokens": ["Kp.", "Foo"],
                                "labels": ["B-JALAN", "I-JALAN"],
                                "flags": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            worksheet_path = Path(directory) / "worksheet.csv"
            worksheet_path.write_text(
                "base_address_id,indexed_tokens,spans,annotator_id,notes\n"
                "npsn_sd_1,0:Kp. 1:Foo,DETAIL_LOKASI:0-2,YT-01,\n",
                encoding="utf-8",
            )
            agreement_path = Path(directory) / "agreement.json"
            adjudication_path = Path(directory) / "adjudication.csv"
            human_labels_path = Path(directory) / "human.json"

            MODULE.main(
                [
                    "--candidates", str(candidates_path),
                    "--worksheet", str(worksheet_path),
                    "--agreement", str(agreement_path),
                    "--adjudication", str(adjudication_path),
                    "--human-labels", str(human_labels_path),
                ]
            )
            with adjudication_path.open(encoding="utf-8") as stream:
                rows = stream.read().strip().splitlines()
            self.assertEqual(len(rows), 3)  # header + one row per side of the disagreement


if __name__ == "__main__":
    unittest.main()

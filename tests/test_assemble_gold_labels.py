from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location("assemble_gold_labels", ROOT / "scripts" / "assemble_gold_labels.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

from alamatin.label_schema import validate_bio_sequence  # noqa: E402


def _candidates() -> dict:
    return {
        "examples": [
            {"base_address_id": "A", "tokens": ["Jl.", "Foo"], "labels": ["B-JALAN", "I-JALAN"]},
            {"base_address_id": "B", "tokens": ["Kp.", "Bar"], "labels": ["B-JALAN", "I-JALAN"]},
        ]
    }


class AssembleTest(unittest.TestCase):
    def test_unsampled_example_uses_automated_labels(self) -> None:
        payload = MODULE.assemble(
            _candidates(),
            manifest={"sampled_ids": []},
            human_labels_by_id={},
            adjudication_rows=[],
        )
        example = next(e for e in payload["examples"] if e["base_address_id"] == "A")
        self.assertEqual(example["labels"], ["B-JALAN", "I-JALAN"])
        self.assertEqual(example["annotation_provenance"], "automated_accepted")
        self.assertEqual(example["annotator_id"], MODULE.AUTOMATED_ANNOTATOR_ID)

    def test_sampled_example_with_no_disagreement_uses_human_labels(self) -> None:
        payload = MODULE.assemble(
            _candidates(),
            manifest={"sampled_ids": ["A"]},
            human_labels_by_id={"A": {"tokens": ["Jl.", "Foo"], "labels": ["B-JALAN", "I-JALAN"], "annotator_id": "YT-01"}},
            adjudication_rows=[],
        )
        example = next(e for e in payload["examples"] if e["base_address_id"] == "A")
        self.assertEqual(example["annotation_provenance"], "double_annotated_agreed")
        self.assertEqual(example["annotator_id"], "YT-01")

    def test_adjudicated_override_is_applied(self) -> None:
        payload = MODULE.assemble(
            _candidates(),
            manifest={"sampled_ids": ["B"]},
            human_labels_by_id={"B": {"tokens": ["Kp.", "Bar"], "labels": ["B-JALAN", "I-JALAN"], "annotator_id": "YT-01"}},
            adjudication_rows=[
                {
                    "base_address_id": "B",
                    "start": "0",
                    "end": "2",
                    "adjudicated_label": "DETAIL_LOKASI",
                }
            ],
        )
        example = next(e for e in payload["examples"] if e["base_address_id"] == "B")
        self.assertEqual(example["labels"], ["B-DETAIL_LOKASI", "I-DETAIL_LOKASI"])
        self.assertEqual(example["annotation_provenance"], "double_annotated_adjudicated")

    def test_o_decision_does_not_wipe_finer_human_sub_spans_it_overlaps(self) -> None:
        # A disagreement row sourced from "automated added a coarser span the
        # human didn't have" carries the automated pass's own (misaligned)
        # boundary. Adjudicating that row to "O" must not destroy the
        # human's correct, finer-grained sub-spans that fall inside it.
        candidates = {
            "examples": [
                {
                    "base_address_id": "A",
                    "tokens": ["Kp.", "Foo", "Kec.", "Bar"],
                    "labels": ["B-JALAN", "I-JALAN", "I-JALAN", "I-JALAN"],
                }
            ]
        }
        human_labels_by_id = {
            "A": {
                "tokens": ["Kp.", "Foo", "Kec.", "Bar"],
                "labels": ["B-JALAN", "I-JALAN", "B-KECAMATAN", "I-KECAMATAN"],
                "annotator_id": "YT-01",
            }
        }
        payload = MODULE.assemble(
            candidates,
            manifest={"sampled_ids": ["A"]},
            human_labels_by_id=human_labels_by_id,
            adjudication_rows=[
                {"base_address_id": "A", "start": "0", "end": "4", "adjudicated_label": "O"},
            ],
        )
        example = next(e for e in payload["examples"] if e["base_address_id"] == "A")
        self.assertEqual(example["labels"], ["B-JALAN", "I-JALAN", "B-KECAMATAN", "I-KECAMATAN"])

    def test_raises_when_a_sampled_example_was_never_reviewed(self) -> None:
        with self.assertRaises(MODULE.GoldAssemblyError):
            MODULE.assemble(
                _candidates(),
                manifest={"sampled_ids": ["A"]},
                human_labels_by_id={},
                adjudication_rows=[],
            )

    def test_raises_on_unresolved_adjudication_row(self) -> None:
        with self.assertRaises(MODULE.GoldAssemblyError):
            MODULE.assemble(
                _candidates(),
                manifest={"sampled_ids": ["A"]},
                human_labels_by_id={"A": {"tokens": ["Jl.", "Foo"], "labels": ["B-JALAN", "I-JALAN"], "annotator_id": "YT-01"}},
                adjudication_rows=[{"base_address_id": "A", "start": "0", "end": "2", "adjudicated_label": ""}],
            )

    def test_every_final_label_sequence_is_valid_bio(self) -> None:
        payload = MODULE.assemble(
            _candidates(),
            manifest={"sampled_ids": []},
            human_labels_by_id={},
            adjudication_rows=[],
        )
        for example in payload["examples"]:
            valid, reason = validate_bio_sequence(example["labels"])
            self.assertTrue(valid, reason)


if __name__ == "__main__":
    unittest.main()

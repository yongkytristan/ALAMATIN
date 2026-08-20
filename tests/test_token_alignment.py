from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.label_schema import LABEL_TO_ID  # noqa: E402
from alamatin.token_alignment import (  # noqa: E402
    IGNORE_INDEX,
    align_word_labels,
    predictions_to_word_labels,
    tokenize_and_align,
)


class TokenAlignmentTest(unittest.TestCase):
    def test_only_first_subword_receives_label(self) -> None:
        aligned = align_word_labels(
            [None, 0, 0, None],
            ["B-KELURAHAN"],
        )

        self.assertEqual(
            aligned,
            [
                IGNORE_INDEX,
                LABEL_TO_ID["B-KELURAHAN"],
                IGNORE_INDEX,
                IGNORE_INDEX,
            ],
        )

    def test_punctuation_does_not_shift_labels(self) -> None:
        aligned = align_word_labels(
            [None, 0, 1, 2, None],
            ["B-JALAN", "O", "B-KOTA_KABUPATEN"],
        )

        self.assertEqual(
            aligned,
            [
                IGNORE_INDEX,
                LABEL_TO_ID["B-JALAN"],
                LABEL_TO_ID["O"],
                LABEL_TO_ID["B-KOTA_KABUPATEN"],
                IGNORE_INDEX,
            ],
        )

    def test_rt_rw_and_separator_alignment(self) -> None:
        aligned = align_word_labels(
            [None, 0, 1, 2, 3, 4, None],
            ["B-RT", "I-RT", "O", "B-RW", "I-RW"],
        )

        self.assertEqual(
            aligned,
            [
                IGNORE_INDEX,
                LABEL_TO_ID["B-RT"],
                LABEL_TO_ID["I-RT"],
                LABEL_TO_ID["O"],
                LABEL_TO_ID["B-RW"],
                LABEL_TO_ID["I-RW"],
                IGNORE_INDEX,
            ],
        )

    def test_number_and_postcode_subwords(self) -> None:
        aligned = align_word_labels(
            [None, 0, 1, 2, 2, None],
            ["B-NOMOR", "I-NOMOR", "B-KODEPOS"],
        )

        self.assertEqual(
            aligned,
            [
                IGNORE_INDEX,
                LABEL_TO_ID["B-NOMOR"],
                LABEL_TO_ID["I-NOMOR"],
                LABEL_TO_ID["B-KODEPOS"],
                IGNORE_INDEX,
                IGNORE_INDEX,
            ],
        )

    def test_empty_input_ignores_special_tokens(self) -> None:
        self.assertEqual(
            align_word_labels([None, None], []),
            [IGNORE_INDEX, IGNORE_INDEX],
        )

    def test_rejects_whitespace_only_token(self) -> None:
        class TokenizerMustNotBeCalled:
            def __call__(self, *args: object, **kwargs: object) -> object:
                raise AssertionError("tokenizer should not be called")

        with self.assertRaisesRegex(ValueError, "whitespace-only"):
            tokenize_and_align(
                {"tokens": ["   "], "labels": ["O"]},
                tokenizer=TokenizerMustNotBeCalled(),
            )

    def test_special_tokens_and_padding_use_ignore_index(self) -> None:
        aligned = align_word_labels(
            [None, 0, None, None, None],
            ["B-KOTA_KABUPATEN"],
        )

        self.assertEqual(
            aligned,
            [
                IGNORE_INDEX,
                LABEL_TO_ID["B-KOTA_KABUPATEN"],
                IGNORE_INDEX,
                IGNORE_INDEX,
                IGNORE_INDEX,
            ],
        )

    def test_predictions_round_trip_without_label_shift(self) -> None:
        word_ids = [None, 0, 1, 1, 2, 2, None]
        predicted_ids = [
            LABEL_TO_ID["O"],
            LABEL_TO_ID["B-JALAN"],
            LABEL_TO_ID["I-JALAN"],
            LABEL_TO_ID["O"],
            LABEL_TO_ID["B-KODEPOS"],
            LABEL_TO_ID["B-PROVINSI"],
            LABEL_TO_ID["O"],
        ]

        reconstructed = predictions_to_word_labels(
            predicted_ids,
            word_ids,
            word_count=3,
        )

        self.assertEqual(
            reconstructed,
            ["B-JALAN", "I-JALAN", "B-KODEPOS"],
        )

    def test_rejects_word_id_outside_label_sequence(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside label sequence"):
            align_word_labels([None, 0, 1, None], ["O"])

    def test_rejects_missing_prediction_after_truncation(self) -> None:
        with self.assertRaisesRegex(ValueError, "may have been truncated"):
            predictions_to_word_labels(
                [LABEL_TO_ID["O"], LABEL_TO_ID["B-JALAN"]],
                [None, 0],
                word_count=2,
            )


if __name__ == "__main__":
    unittest.main()

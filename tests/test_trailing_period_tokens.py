"""Tests for numeric tokens that carry a trailing period.

Reported from real use: in

    Jl. Braga No. 5, RT. 5, RW. 6. Kel. Braga, Kec. Sumur Bandung, ...

`RW` was not detected. A period used as a separator attaches to the token before
it, so the tokenizer produces `RW.` followed by `6.`, and every numeric pattern
allowed leading dots but not trailing ones. The number was silently dropped.

The first fix made detection work and immediately created a worse bug: the
value `40111.` reached the administrative validator, which compared it with
`40111` and reported a conflict -- a **correct** address declared `TIDAK_VALID`.
Detection and canonicalisation had to move together, so these tests cover both
ends: the field is found, and the value that leaves the normalizer is clean.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.address_normalizer import normalize_address  # noqa: E402
from alamatin.regex_baseline import tag_text  # noqa: E402

PERIOD = (
    "Jl. Braga No. 5, RT. 5, RW. 6. Kel. Braga, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 40111"
)
COMMA = (
    "Jl. Braga No. 5, RT. 5, RW. 6, Kel. Braga, Kec. Sumur Bandung, "
    "Kota Bandung, Jawa Barat 40111"
)


def fields(text: str) -> dict[str, str]:
    tokens, labels = tag_text(text)
    found: dict[str, list[str]] = {}
    for token, label in zip(tokens, labels):
        if label == "O":
            continue
        found.setdefault(label.split("-", 1)[1], []).append(token)
    return {name: " ".join(parts) for name, parts in found.items()}


class DetectionTest(unittest.TestCase):
    def test_rw_is_detected_when_a_period_separates_it(self) -> None:
        # The reported case. Previously absent.
        self.assertIn("RW", fields(PERIOD))

    def test_a_period_separated_address_finds_the_same_fields_as_a_comma_one(self) -> None:
        self.assertEqual(set(fields(PERIOD)), set(fields(COMMA)))

    def test_every_numeric_form_tolerates_a_trailing_period(self) -> None:
        cases = {
            "RT. 5. Kel. Braga": "RT",
            "RW. 6. Kel. Braga": "RW",
            "Jl. Braga No. 5. Kel. Braga": "NOMOR",
            "Jl. Braga, Kel. Braga, Kota Bandung, Jawa Barat 40111.": "KODEPOS",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIn(expected, fields(text))

    def test_a_lone_period_is_still_not_a_number(self) -> None:
        # Non-vacuous: the relaxation must not make punctuation numeric.
        self.assertNotIn("RW", fields("Jl. Braga RW. . Kel. Braga"))


class CanonicalisationTest(unittest.TestCase):
    """The half that matters more: the value handed to the validator."""

    def test_rt_rw_canonicalise_despite_the_period(self) -> None:
        result = normalize_address({"RT": "RT. 5.", "RW": "RW. 6."})
        self.assertEqual(result.values()["RT"], "RT 005")
        self.assertEqual(result.values()["RW"], "RW 006")

    def test_a_postcode_does_not_keep_a_sentence_period(self) -> None:
        # This is the false-conflict case: "40111." against a reference holding
        # "40111" was reported as an administrative conflict at high severity.
        result = normalize_address({"KODEPOS": "40111."})
        self.assertEqual(result.values()["KODEPOS"], "40111")

    def test_a_split_postcode_still_joins(self) -> None:
        # The behaviour that existed before must survive the change.
        self.assertEqual(
            normalize_address({"KODEPOS": "40 111"}).values()["KODEPOS"], "40111"
        )

    def test_a_split_postcode_with_a_period_also_joins(self) -> None:
        self.assertEqual(
            normalize_address({"KODEPOS": "40 111."}).values()["KODEPOS"], "40111"
        )

    def test_a_non_postcode_value_is_left_alone(self) -> None:
        # Non-vacuous: the trim must not invent a postcode from anything else.
        self.assertEqual(
            normalize_address({"KODEPOS": "bukan kodepos"}).values()["KODEPOS"],
            "bukan kodepos",
        )


class EndToEndTest(unittest.TestCase):
    SPLIT = ROOT / "data" / "processed" / "jabar-reference-v1-verified.json"

    def setUp(self) -> None:
        if not self.SPLIT.is_file():
            self.skipTest("governed reference not present; see data/sources.md")
        import alamatin.service as service

        self.pipeline = service.load_pipeline()

    def _status(self, text: str) -> str:
        return self.pipeline.process(
            text, request_id="trailingdot-001"
        ).document["quality_gate"]["status"]

    def test_period_and_comma_separated_forms_agree(self) -> None:
        # The whole point: the same address written two ways must not get two
        # different verdicts.
        self.assertEqual(self._status(PERIOD), self._status(COMMA))

    def test_a_correct_address_ending_in_a_period_is_not_rejected(self) -> None:
        self.assertEqual(
            self._status(
                "Jl. Braga No. 5, Kel. Braga, Kec. Sumur Bandung, "
                "Kota Bandung, Jawa Barat 40111."
            ),
            "SIAP_DIPROSES",
        )

    def test_a_fully_period_separated_address_is_not_rejected(self) -> None:
        self.assertEqual(
            self._status(
                "Jl. Braga No. 5. RT. 5. RW. 6. Kel. Braga. "
                "Kec. Sumur Bandung. Kota Bandung. Jawa Barat 40111."
            ),
            "SIAP_DIPROSES",
        )


if __name__ == "__main__":
    unittest.main()

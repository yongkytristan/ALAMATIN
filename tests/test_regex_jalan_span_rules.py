"""Tests for the two JALAN span rules added after the real-data comparison.

Both rules were derived from failures on real addresses, so each test states
the real pattern it protects. The negative cases matter more than the positive
ones: a merge rule that merges too eagerly, or a cap that never truncates,
would raise the metric on one split and silently corrupt every other field.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.evaluation_metrics import (  # noqa: E402
    CRITICAL_ENTITY_TYPES,
    extract_bio_entities,
)
from alamatin.regex_baseline import MAX_SPAN_LENGTH, tag_tokens  # noqa: E402


def spans(text: str) -> set[tuple[str, str]]:
    """Return {(entity, surface)} so assertions read like the address."""

    tokens = text.split()
    return {
        (entity, " ".join(tokens[start:end]))
        for entity, start, end in extract_bio_entities(tag_tokens(tokens))
    }


class SameTypeDesignatorMergeTest(unittest.TestCase):
    def test_stacked_street_designators_form_one_span(self) -> None:
        # Real: npsn_sma_20200670. Previously JALAN[Jl.] + JALAN[Kp. Pabuaran
        # Kaum] -- two spans, so both were wrong against a single gold span.
        self.assertIn(
            ("JALAN", "Jl. Kp. Pabuaran Kaum"),
            spans("Jl. Kp. Pabuaran Kaum , Kec. Ciampea"),
        )

    def test_a_second_stacked_designator_also_merges(self) -> None:
        self.assertIn(("JALAN", "Jl. Gg. Melati"), spans("Jl. Gg. Melati , Kec. Cimahi"))

    def test_a_different_designator_type_still_breaks_the_span(self) -> None:
        # The rule must not swallow a genuine field change.
        result = spans("Jl. Melati Kel. Braga Kec. Sumur")
        self.assertIn(("JALAN", "Jl. Melati"), result)
        self.assertIn(("KELURAHAN", "Kel. Braga"), result)
        self.assertIn(("KECAMATAN", "Kec. Sumur"), result)

    def test_a_segment_break_still_breaks_the_span(self) -> None:
        # Two streets separated by a comma are two streets, not one.
        result = spans("Jl. Melati , Jl. Kenanga")
        self.assertIn(("JALAN", "Jl. Melati"), result)
        self.assertIn(("JALAN", "Jl. Kenanga"), result)

    def test_same_type_merge_does_not_join_across_a_comma(self) -> None:
        result = spans("Kec. Cimahi , Kec. Cimahi Tengah")
        self.assertNotIn(("KECAMATAN", "Kec. Cimahi , Kec. Cimahi Tengah"), result)


class JalanSpanCapTest(unittest.TestCase):
    def test_cap_is_six(self) -> None:
        # Pinned: the value is derived from the gold span-length distribution on
        # the recorded tuning partition, not from whichever value scored best.
        self.assertEqual(MAX_SPAN_LENGTH["JALAN"], 6)

    def test_a_six_token_street_name_survives(self) -> None:
        # Real: npsn_sd_69972992, truncated at five tokens before this change.
        self.assertIn(
            ("JALAN", "jl. mutiara gading city blok s."),
            spans("jl. mutiara gading city blok s. , kce. tarumajaya"),
        )

    def test_the_cap_still_truncates(self) -> None:
        # Non-vacuous: an unbounded span would absorb trailing prose forever.
        text = "Jl. Melati satu dua tiga empat lima enam tujuh"
        jalan = [surface for entity, surface in spans(text) if entity == "JALAN"]
        self.assertTrue(jalan)
        self.assertTrue(
            all(len(surface.split()) <= 6 for surface in jalan),
            f"a JALAN span exceeded the cap: {jalan}",
        )

    def test_other_field_caps_are_unchanged(self) -> None:
        # Only JALAN was re-derived; a silent change elsewhere would be a
        # regression hiding inside this one.
        self.assertEqual(MAX_SPAN_LENGTH["KELURAHAN"], 4)
        self.assertEqual(MAX_SPAN_LENGTH["KECAMATAN"], 4)
        self.assertEqual(MAX_SPAN_LENGTH["KOTA_KABUPATEN"], 4)
        self.assertEqual(MAX_SPAN_LENGTH["PROVINSI"], 3)


class HeldOutImprovementTest(unittest.TestCase):
    """The claim that justified the change must keep holding.

    Skipped where the governed split is absent, which is every clone of the
    public repository.
    """

    PARTITION = ROOT / "data" / "interim" / "evaluation-splits" / (
        "real-dev-tuning-partition.json"
    )
    SPLIT = ROOT / "data" / "interim" / "evaluation-splits" / "real_dev.json"

    def setUp(self) -> None:
        if not (self.PARTITION.is_file() and self.SPLIT.is_file()):
            self.skipTest("governed real_dev split not present; see data/sources.md")
        self.partition = json.loads(self.PARTITION.read_text(encoding="utf-8"))
        payload = json.loads(self.SPLIT.read_text(encoding="utf-8"))
        self.by_id = {e["base_address_id"]: e for e in payload["examples"]}

    def _critical_exact_match(self, ids: list[str]) -> tuple[int, int]:
        correct = 0
        for identifier in ids:
            example = self.by_id[identifier]
            gold = {
                span
                for span in extract_bio_entities(example["labels"])
                if span[0] in CRITICAL_ENTITY_TYPES
            }
            predicted = {
                span
                for span in extract_bio_entities(tag_tokens(list(example["tokens"])))
                if span[0] in CRITICAL_ENTITY_TYPES
            }
            correct += gold == predicted
        return correct, len(ids)

    def test_partition_is_a_disjoint_cover_of_the_split(self) -> None:
        tune = set(self.partition["tune"])
        holdout = set(self.partition["holdout"])
        self.assertFalse(tune & holdout)
        self.assertEqual(tune | holdout, set(self.by_id))

    def test_held_out_critical_exact_match_is_at_least_25_of_35(self) -> None:
        # The measured post-change value on data no rule was tuned against.
        # A regression below it means the rules stopped paying for themselves.
        correct, total = self._critical_exact_match(self.partition["holdout"])
        self.assertEqual(total, 35)
        self.assertGreaterEqual(correct, 25, f"held-out critical EM fell to {correct}/35")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "annotate_human_noised_benchmark",
    ROOT / "scripts" / "annotate_human_noised_benchmark.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

from alamatin.label_schema import validate_bio_sequence  # noqa: E402
from alamatin.tokenizer import tokenize  # noqa: E402


class LabelExampleTest(unittest.TestCase):
    def _labels(self, text: str, kecamatan: str, kabupaten_kota: str) -> tuple[list[str], list[str], list[str]]:
        tokens = tokenize(text)
        labels, flags = MODULE.label_example(tokens, kecamatan, kabupaten_kota)
        valid, reason = validate_bio_sequence(labels)
        self.assertTrue(valid, reason)
        return tokens, labels, flags

    def test_clean_three_segment_address_is_labeled_correctly(self) -> None:
        tokens, labels, flags = self._labels(
            "Jl. Gunung Sentul, Kec Ciemas, Kabupaten Sukabumi", "CIEMAS", "KABUPATEN SUKABUMI"
        )
        self.assertEqual(
            list(zip(tokens, labels)),
            [
                ("Jl.", "B-JALAN"), ("Gunung", "I-JALAN"), ("Sentul", "I-JALAN"), (",", "O"),
                ("Kec", "B-KECAMATAN"), ("Ciemas", "I-KECAMATAN"), (",", "O"),
                ("Kabupaten", "B-KOTA_KABUPATEN"), ("Sukabumi", "I-KOTA_KABUPATEN"),
            ],
        )
        self.assertEqual(flags, [])

    def test_kampung_only_locator_is_labeled_jalan(self) -> None:
        tokens, labels, flags = self._labels("KP. CIHAURSEAH, KCMTN JAMPANGKULON, KB SUKABUMI", "JAMPANGKULON", "KABUPATEN SUKABUMI")
        self.assertEqual(labels[0], "B-JALAN")
        self.assertEqual(labels[1], "I-JALAN")
        self.assertEqual(flags, [])

    def test_rt_rw_as_separate_marker_and_number_tokens(self) -> None:
        tokens, labels, _ = self._labels(
            "Kp. Pajaten Rt 01 Rw. 02, Kecamatan Kertasari, Kabupaten Bandung", "KERTASARI", "KABUPATEN BANDUNG"
        )
        pairs = dict(zip(tokens, labels))
        self.assertEqual(labels[tokens.index("Rt")], "B-RT")
        self.assertEqual(labels[tokens.index("01")], "I-RT")
        self.assertEqual(labels[tokens.index("Rw.")], "B-RW")
        self.assertEqual(labels[tokens.index("02")], "I-RW")

    def test_glued_rt_rw_single_token(self) -> None:
        tokens, labels, _ = self._labels("Jl. Mawar rt.03/rw.07, Kec Foo, Kab Bar", "FOO", "KABUPATEN BAR")
        self.assertEqual(labels[tokens.index("rt.03")], "B-RT")
        self.assertEqual(labels[tokens.index("rw.07")], "B-RW")

    def test_glued_designator_and_name_still_matches_known_value(self) -> None:
        tokens, labels, flags = self._labels("jl.rayaselatan,kecbantarujeg,kbmajalengka", "BANTARUJEG", "KABUPATEN MAJALENGKA")
        self.assertEqual(labels[tokens.index("kecbantarujeg")], "B-KECAMATAN")
        self.assertEqual(labels[tokens.index("kbmajalengka")], "B-KOTA_KABUPATEN")

    def test_typo_tolerant_fuzzy_match(self) -> None:
        tokens, labels, flags = self._labels("dusun passian, kc. tambaksari, kb ciams", "TAMBAKSARI", "KABUPATEN CIAMIS")
        self.assertEqual(labels[tokens.index("tambaksari")], "I-KECAMATAN")
        self.assertIn("KOTA_KABUPATEN", " ".join(labels))

    def test_unmatched_long_segment_is_flagged_not_silently_guessed_as_admin(self) -> None:
        tokens, labels, flags = self._labels(
            "Jl.CimangguPermai1KecTanahSarealKtBogor, Kecamatan Tanah Sareal, Kta Bogor",
            "TANAH SAREAL",
            "KOTA BOGOR",
        )
        self.assertTrue(any("needs_review" in flag for flag in flags))

    def test_never_emits_a_label_outside_the_canonical_schema(self) -> None:
        from alamatin.label_schema import LABEL_TO_ID

        tokens, labels, _ = self._labels("Jl. Mawar No. 7, Kec Foo, Kab Bar", "FOO", "KABUPATEN BAR")
        for label in labels:
            self.assertIn(label, LABEL_TO_ID)


if __name__ == "__main__":
    unittest.main()

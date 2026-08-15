from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.label_schema import validate_bio_sequence  # noqa: E402
from alamatin.regex_baseline import tag_text, tag_tokens  # noqa: E402
from alamatin.tokenizer import tokenize  # noqa: E402


class TagTokensTest(unittest.TestCase):
    def _tag(self, text: str) -> tuple[list[str], list[str]]:
        tokens, labels = tag_text(text)
        valid, reason = validate_bio_sequence(labels)
        self.assertTrue(valid, reason)
        return tokens, labels

    def test_clean_designated_address(self) -> None:
        tokens, labels = self._tag("Jl. Asia Afrika No. 12 Kel. Braga Kec. Sumur Bandung Kota Bandung Jawa Barat 40111")
        pairs = dict(zip(tokens, labels))
        self.assertEqual(labels[tokens.index("Jl.")], "B-JALAN")
        self.assertEqual(labels[tokens.index("No.")], "B-NOMOR")
        self.assertEqual(labels[tokens.index("Kel.")], "B-KELURAHAN")
        self.assertEqual(labels[tokens.index("Kec.")], "B-KECAMATAN")
        self.assertEqual(labels[tokens.index("Kota")], "B-KOTA_KABUPATEN")
        self.assertEqual(labels[tokens.index("Jawa")], "B-PROVINSI")
        self.assertEqual(labels[tokens.index("40111")], "B-KODEPOS")

    def test_rt_rw_marker_and_number_as_separate_tokens(self) -> None:
        tokens, labels = self._tag("RT 04 RW 09 Jl. Mawar")
        self.assertEqual(labels[tokens.index("RT")], "B-RT")
        self.assertEqual(labels[tokens.index("RW")], "B-RW")

    def test_glued_rt_rw(self) -> None:
        tokens, labels = self._tag("Jl. Mawar RT04 RW09")
        self.assertEqual(labels[tokens.index("RT04")], "B-RT")
        self.assertEqual(labels[tokens.index("RW09")], "B-RW")

    def test_kampung_only_locator_is_jalan(self) -> None:
        tokens, labels = self._tag("Kp. Cihaurseah Kec. Jampangkulon Kab. Sukabumi")
        self.assertEqual(labels[0], "B-JALAN")

    def test_pii_placeholders_and_order_junk_are_o(self) -> None:
        tokens, labels = self._tag("[NAME] [PHONE] TUJUAN: Jl. Merdeka")
        self.assertEqual(labels[tokens.index("[NAME]")], "O")
        self.assertEqual(labels[tokens.index("[PHONE]")], "O")

    def test_delivery_time_instruction_stays_o(self) -> None:
        tokens, labels = self._tag("Jl. Pasteur No 154 kirim setelah jam 5 sore")
        for token in ("kirim", "setelah", "jam", "sore"):
            self.assertEqual(labels[tokens.index(token)], "O")

    def test_designator_can_appear_in_any_order(self) -> None:
        tokens, labels = self._tag("No. 153B Jln Asia Afrika Kab. Ciamis 46258 Provinsi Jawa Barat")
        self.assertEqual(labels[tokens.index("No.")], "B-NOMOR")
        self.assertEqual(labels[tokens.index("Jln")], "B-JALAN")
        self.assertEqual(labels[tokens.index("Kab.")], "B-KOTA_KABUPATEN")
        self.assertEqual(labels[tokens.index("Provinsi")], "B-PROVINSI")

    def test_never_emits_a_label_outside_the_canonical_schema(self) -> None:
        from alamatin.label_schema import LABEL_TO_ID

        _, labels = self._tag("Jl. Mawar No. 7 RT 04 RW 09 Kel. Sukamaju Kec. Cilodong Kota Depok Jawa Barat 16415")
        for label in labels:
            self.assertIn(label, LABEL_TO_ID)

    def test_tag_tokens_matches_tag_text_on_pretokenized_input(self) -> None:
        text = "Jl. Mawar No. 7"
        tokens = tokenize(text)
        self.assertEqual(tag_tokens(tokens), tag_text(text)[1])


if __name__ == "__main__":
    unittest.main()

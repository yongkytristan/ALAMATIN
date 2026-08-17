from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.label_schema import validate_bio_sequence  # noqa: E402
from alamatin.libpostal_baseline import tag_tokens  # noqa: E402
from alamatin.tokenizer import tokenize  # noqa: E402


class LibpostalBaselineTest(unittest.TestCase):
    def test_maps_basic_libpostal_components_to_alamatin_bio(self) -> None:
        text = "Jl. Asia Afrika No. 12 Kota Bandung 40111"
        tokens = tokenize(text)

        def fake_parser(_: str):
            return [
                ("jl. asia afrika", "road"),
                ("12", "house_number"),
                ("bandung", "city"),
                ("40111", "postcode"),
            ]

        labels = tag_tokens(tokens, parser=fake_parser)

        self.assertEqual(labels[tokens.index("Jl.")], "B-JALAN")
        self.assertEqual(labels[tokens.index("Asia")], "I-JALAN")
        self.assertEqual(labels[tokens.index("Afrika")], "I-JALAN")

        self.assertEqual(labels[tokens.index("12")], "B-NOMOR")
        self.assertEqual(labels[tokens.index("Bandung")], "B-KOTA_KABUPATEN")
        self.assertEqual(labels[tokens.index("40111")], "B-KODEPOS")

        valid, reason = validate_bio_sequence(labels)
        self.assertTrue(valid, reason)

    def test_unsupported_libpostal_label_is_ignored(self) -> None:
        tokens = tokenize("Gedung Merdeka Jl. Asia Afrika")

        def fake_parser(_: str):
            return [
                ("gedung merdeka", "house"),
                ("jl. asia afrika", "road"),
            ]

        labels = tag_tokens(tokens, parser=fake_parser)

        self.assertEqual(labels[0], "O")
        self.assertEqual(labels[1], "O")
        self.assertEqual(labels[tokens.index("Jl.")], "B-JALAN")

    def test_unaligned_component_is_ignored(self) -> None:
        tokens = tokenize("Jl. Asia Afrika Bandung")

        def fake_parser(_: str):
            return [
                ("sesuatu yang tidak ada", "road"),
                ("bandung", "city"),
            ]

        labels = tag_tokens(tokens, parser=fake_parser)

        self.assertEqual(labels[tokens.index("Bandung")], "B-KOTA_KABUPATEN")

    def test_output_always_matches_token_count(self) -> None:
        tokens = tokenize("Jl. Mawar No. 7")

        def fake_parser(_: str):
            return [
                ("jl. mawar", "road"),
                ("7", "house_number"),
            ]

        labels = tag_tokens(tokens, parser=fake_parser)

        self.assertEqual(len(labels), len(tokens))

    def test_component_order_from_parser_does_not_need_to_match_text_order(self) -> None:
        tokens = tokenize("Jl. Mawar Bandung 40111")

        def fake_parser(_: str):
            return [
                ("40111", "postcode"),
                ("jl. mawar", "road"),
                ("bandung", "city"),
            ]

        labels = tag_tokens(tokens, parser=fake_parser)

        self.assertEqual(labels[tokens.index("Jl.")], "B-JALAN")
        self.assertEqual(labels[tokens.index("Mawar")], "I-JALAN")
        self.assertEqual(labels[tokens.index("Bandung")], "B-KOTA_KABUPATEN")
        self.assertEqual(labels[tokens.index("40111")], "B-KODEPOS")

if __name__ == "__main__":
    unittest.main()
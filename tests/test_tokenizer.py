from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.tokenizer import tokenize  # noqa: E402


class TokenizerTest(unittest.TestCase):
    def test_keeps_abbreviation_periods_attached(self) -> None:
        self.assertEqual(tokenize("Jl. Asia Afrika No. 12"), ["Jl.", "Asia", "Afrika", "No.", "12"])

    def test_splits_trailing_comma_into_its_own_token(self) -> None:
        self.assertEqual(tokenize("Sukamulya, Kec Cikembar"), ["Sukamulya", ",", "Kec", "Cikembar"])

    def test_splits_slash_between_rt_and_rw(self) -> None:
        self.assertEqual(tokenize("RT 03/RW 07"), ["RT", "03", "/", "RW", "07"])

    def test_handles_multiple_trailing_separators(self) -> None:
        self.assertEqual(tokenize("Bandung,,"), ["Bandung", ",", ","])

    def test_matches_the_established_gold_fixture_tokenization(self) -> None:
        text = "Jl. Pahlawan , No. 21 , Semarang , Jawa Tengah , 50241"
        self.assertEqual(
            tokenize(text),
            ["Jl.", "Pahlawan", ",", "No.", "21", ",", "Semarang", ",", "Jawa", "Tengah", ",", "50241"],
        )

    def test_empty_string_yields_no_tokens(self) -> None:
        self.assertEqual(tokenize(""), [])

    def test_round_trips_whitespace_only_input(self) -> None:
        self.assertEqual(tokenize("   "), [])


if __name__ == "__main__":
    unittest.main()

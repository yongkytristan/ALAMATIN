"""Canonical whitespace/punctuation tokenizer shared by annotation and NER.

Matches the convention already used by ``tests/fixtures/ner_gold_examples.json``
and ``scripts/generate_synthetic_addresses.py``: split on whitespace, then pull
a leading/trailing separator (comma, slash, semicolon, colon) off as its own
token, while keeping a lexical period such as ``Jl.`` or ``No.`` attached.
"""

from __future__ import annotations

import re

SEPARATOR_CHARS = ",;/:"
_SEPARATOR_SPLIT = re.compile(f"([{re.escape(SEPARATOR_CHARS)}])")


def tokenize(text: str) -> list[str]:
    """Split ``text`` into address tokens, isolating separator punctuation."""

    tokens: list[str] = []
    for chunk in text.split():
        tokens.extend(piece for piece in _SEPARATOR_SPLIT.split(chunk) if piece)
    return tokens

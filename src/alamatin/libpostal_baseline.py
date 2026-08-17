"""libpostal baseline adapter for the canonical ALAMATIN NER schema."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import re


ParsedComponent = tuple[str, str]
Parser = Callable[[str], list[ParsedComponent]]


LIBPOSTAL_TO_ALAMATIN = {
    "road": "JALAN",
    "house_number": "NOMOR",
    "postcode": "KODEPOS",
    "city": "KOTA_KABUPATEN",
    "state": "PROVINSI",
    "city_district": "KECAMATAN",
}


def _default_parser(text: str) -> list[ParsedComponent]:
    try:
        from postal.parser import parse_address
    except ImportError as exc:
        raise RuntimeError(
            "libpostal Python bindings are not installed"
        ) from exc

    return parse_address(text)


def _normalize_for_alignment(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[.,;:/]+", " ", value)
    return " ".join(value.split())


def _find_component_span(
    tokens: Sequence[str],
    component: str,
    *,
    start_at: int = 0,
) -> tuple[int, int] | None:

    target = _normalize_for_alignment(component)

    for start in range(start_at, len(tokens)):
        for end in range(start + 1, len(tokens) + 1):
            candidate = " ".join(tokens[start:end])

            if _normalize_for_alignment(candidate) == target:
                return start, end

    return None


def tag_tokens(
    tokens: Sequence[str],
    *,
    parser: Parser | None = None,
) -> list[str]:

    if parser is None:
        parser = _default_parser

    labels = ["O"] * len(tokens)

    text = " ".join(tokens)
    components = parser(text)

    cursor = 0

    for value, libpostal_label in components:
        entity = LIBPOSTAL_TO_ALAMATIN.get(libpostal_label)

        if entity is None:
            continue

        span = _find_component_span(
            tokens,
            value,
            start_at=cursor,
        )

        if span is None:
            continue

        start, end = span

        if any(label != "O" for label in labels[start:end]):
            continue

        labels[start] = f"B-{entity}"

        for index in range(start + 1, end):
            labels[index] = f"I-{entity}"

        cursor = end

    return labels
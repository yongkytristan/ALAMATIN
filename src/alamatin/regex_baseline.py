"""ALM-015 regex/rule NER baseline.

A deliberately simple, designator-word-driven tagger with no learned
parameters and no lookup against any real reference database or gold/test
data. It only implements the surface-form rules already documented in
`docs/label_schema.md` (designator words, typo variants, and the
kampung/dusun-as-JALAN clarification) -- nothing here is derived from, or
tuned against, any specific dataset's answers.

It is intentionally weaker than a trained model: it can recognize an
administrative name only when an adjacent designator word marks its role
(per `docs/label_schema.md` section 4, "without a designator, require
structured evidence or an unambiguous hierarchy" -- a rule baseline has
neither). That gap is expected, not a bug.
"""

from __future__ import annotations

import re

from .tokenizer import tokenize

SEGMENT_BREAK_TOKENS = {",", ";", "-"}

JALAN_DESIGNATORS = ("jalan", "jaln", "jln", "jl", "gang", "gg", "kampung", "kp", "dusun", "dsn")
KELURAHAN_DESIGNATORS = ("kelurahan", "kel", "desa", "ds")
KECAMATAN_DESIGNATORS = (
    "kecamatan", "kecamatn", "kecamtan", "kecmatan", "kecmatn", "kmctn", "kcmtn", "kec", "kc",
)
KOTA_KABUPATEN_DESIGNATORS = (
    "kabupaten", "kabupatan", "kabupatn", "kbupatn", "kabpatn", "kab", "kb", "kota", "kta", "kt",
)
PROVINSI_DESIGNATORS = ("provinsi", "prov")
PROVINCE_BARE_FORMS = {"jawabarat", "jabar", "dkijakarta"}
PROVINCE_BARE_TWO_TOKEN_FORMS = {("jawa", "barat"), ("jawa", "brat"), ("dki", "jakarta")}

DESIGNATOR_ENTITY_ORDER = (
    (JALAN_DESIGNATORS, "JALAN"),
    (KELURAHAN_DESIGNATORS, "KELURAHAN"),
    (KECAMATAN_DESIGNATORS, "KECAMATAN"),
    (KOTA_KABUPATEN_DESIGNATORS, "KOTA_KABUPATEN"),
    (PROVINSI_DESIGNATORS, "PROVINSI"),
)

# A real Indonesian place name is rarely more than a few words. Capping how
# far a designator-opened span can extend keeps a run of unrelated trailing
# text (an instruction, a stray word) from being silently absorbed into the
# entity forever just because no further designator happens to follow it.
MAX_SPAN_LENGTH = {
    "JALAN": 5,
    "KELURAHAN": 4,
    "KECAMATAN": 4,
    "KOTA_KABUPATEN": 4,
    "PROVINSI": 3,
}

RT_PATTERN = re.compile(r"^rt\.{0,2}0*(\d+)[a-z]?$")
RW_PATTERN = re.compile(r"^rw\.{0,2}0*(\d+)[a-z]?$")
NOMOR_PATTERN = re.compile(r"^(no|nomor|nomer)\.?0*(\d+[a-z]?)$")
RT_MARKER_ONLY = re.compile(r"^rt\.{0,2}$")
RW_MARKER_ONLY = re.compile(r"^rw\.{0,2}$")
NOMOR_MARKER_ONLY = re.compile(r"^(no|nomor|nomer)\.?$")
BARE_NUMBER = re.compile(r"^0*(\d+)[a-z]?$")
KODEPOS_PATTERN = re.compile(r"^\d{5}$")


def _clean(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def _match_designator(token: str) -> str | None:
    # Bare province forms (no "Provinsi"/"Prov" word) are handled entirely by
    # _extract_bare_province_forms before this function is ever consulted;
    # see that function's docstring for why.
    cleaned = _clean(token)
    if not cleaned:
        return None
    for designators, entity in DESIGNATOR_ENTITY_ORDER:
        for marker in sorted(designators, key=len, reverse=True):
            if cleaned == marker or (cleaned.startswith(marker) and len(cleaned) > len(marker)):
                return entity
    return None


def _extract_rt_rw_nomor_kodepos(tokens: list[str], labels: list[str]) -> set[int]:
    consumed: set[int] = set()
    position = 0
    while position < len(tokens):
        token = tokens[position].lower()
        next_token = tokens[position + 1].lower() if position + 1 < len(tokens) else ""

        for glued_pattern, entity in ((RT_PATTERN, "RT"), (RW_PATTERN, "RW"), (NOMOR_PATTERN, "NOMOR")):
            if glued_pattern.match(token):
                labels[position] = f"B-{entity}"
                consumed.add(position)
                position += 1
                break
        else:
            if RT_MARKER_ONLY.match(token) and BARE_NUMBER.match(next_token):
                labels[position], labels[position + 1] = "B-RT", "I-RT"
                consumed.update({position, position + 1})
                position += 2
                continue
            if RW_MARKER_ONLY.match(token) and BARE_NUMBER.match(next_token):
                labels[position], labels[position + 1] = "B-RW", "I-RW"
                consumed.update({position, position + 1})
                position += 2
                continue
            if NOMOR_MARKER_ONLY.match(token) and BARE_NUMBER.match(next_token):
                labels[position], labels[position + 1] = "B-NOMOR", "I-NOMOR"
                consumed.update({position, position + 1})
                position += 2
                continue
            if KODEPOS_PATTERN.match(token):
                labels[position] = "B-KODEPOS"
                consumed.add(position)
                position += 1
                continue
            position += 1
            continue
        continue
    return consumed


def _label_contiguous(labels: list[str], start: int, end: int, entity: str) -> None:
    for position, index in enumerate(range(start, end)):
        labels[index] = f"{'B' if position == 0 else 'I'}-{entity}"


def _is_provinsi_designator(token: str) -> bool:
    cleaned = _clean(token)
    return any(
        cleaned == marker or (cleaned.startswith(marker) and len(cleaned) > len(marker))
        for marker in PROVINSI_DESIGNATORS
    )


def _extract_bare_province_forms(tokens: list[str], labels: list[str], consumed: set[int]) -> None:
    """Pre-consume a standalone province name so it can never be swallowed by
    a preceding span (e.g. `Kota Bandung Jawa Barat`) or itself swallow
    trailing junk (e.g. `Jabar tolong telepon dulu`).

    A bare form immediately preceded by a `Provinsi`/`Prov` designator is
    left alone -- the designator-driven scan absorbs it as one short span
    (bounded by `MAX_SPAN_LENGTH`), which is what keeps `Provinsi Jawa Barat`
    a single span instead of two adjacent ones.
    """

    index = 0
    while index < len(tokens):
        if index in consumed:
            index += 1
            continue
        preceded_by_designator = index > 0 and (index - 1) not in consumed and _is_provinsi_designator(tokens[index - 1])
        if not preceded_by_designator:
            if index + 1 < len(tokens) and (index + 1) not in consumed:
                pair = (_clean(tokens[index]), _clean(tokens[index + 1]))
                if pair in PROVINCE_BARE_TWO_TOKEN_FORMS:
                    labels[index], labels[index + 1] = "B-PROVINSI", "I-PROVINSI"
                    consumed.update({index, index + 1})
                    index += 2
                    continue
            if _clean(tokens[index]) in PROVINCE_BARE_FORMS:
                labels[index] = "B-PROVINSI"
                consumed.add(index)
                index += 1
                continue
        index += 1


def tag_tokens(tokens: list[str]) -> list[str]:
    """Return a BIO label for every token using only designator/regex rules."""

    labels = ["O"] * len(tokens)
    consumed = _extract_rt_rw_nomor_kodepos(tokens, labels)
    _extract_bare_province_forms(tokens, labels, consumed)

    spans: list[tuple[str | None, int, int]] = []
    current_start: int | None = None
    current_type: str | None = None

    def flush(end: int) -> None:
        nonlocal current_start, current_type
        if current_start is not None and end > current_start:
            spans.append((current_type, current_start, end))
        current_start = None
        current_type = None

    for index, token in enumerate(tokens):
        if index in consumed or token in SEGMENT_BREAK_TOKENS:
            flush(index)
            continue
        designator_type = _match_designator(token)
        if designator_type is not None:
            flush(index)
            current_start, current_type = index, designator_type
        elif current_start is None:
            current_start, current_type = index, None

        cap = MAX_SPAN_LENGTH.get(current_type) if current_type is not None else None
        if cap is not None and current_start is not None and index - current_start + 1 >= cap:
            flush(index + 1)
    flush(len(tokens))

    # An unclaimed (designator-free) span is only ever promoted to JALAN, and
    # only the first one, and only when no real JALAN designator was found
    # anywhere else -- this is the "bare kampung/locality name as the sole
    # locator" case documented in docs/label_schema.md's rule-clarification
    # log. Without that documented pattern, guessing a label for
    # designator-free text (PII placeholders, order-instruction junk, noise
    # prefixes) is exactly the "plausible guess as gold" the schema forbids;
    # it stays O.
    has_real_jalan_designator = any(entity == "JALAN" for entity, _, _ in spans)
    promoted_fallback = False
    for entity, start, end in spans:
        if entity is None:
            if has_real_jalan_designator or promoted_fallback:
                continue
            entity = "JALAN"
            promoted_fallback = True
        _label_contiguous(labels, start, end, entity)

    return labels


def tag_text(text: str) -> tuple[list[str], list[str]]:
    """Tokenize ``text`` with the canonical tokenizer and tag it."""

    tokens = tokenize(text)
    return tokens, tag_tokens(tokens)

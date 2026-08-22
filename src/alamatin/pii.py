"""Conservative PII extraction and redaction for Indonesian address input.

The public result intentionally never contains a raw detected PII value.  Raw
input should be kept only in the caller's request scope and must not be logged.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable, Literal


PII_DETECTED = "PII_DETECTED"
PHONE_REDACTED = "[PHONE_REDACTED]"
NAME_REDACTED = "[NAME_REDACTED]"

PIIType = Literal["PHONE", "RECIPIENT_NAME"]


@dataclass(frozen=True)
class PIIEntity:
    """Safe metadata for one PII span; the original value is never retained."""

    type: PIIType
    start: int
    end: int
    redacted_value: str

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "start": self.start,
            "end": self.end,
            "redacted_value": self.redacted_value,
        }


@dataclass(frozen=True)
class PIIProcessingResult:
    """PII-safe input variants for downstream processing and presentation."""

    address_text: str
    redacted_text: str
    entities: tuple[PIIEntity, ...]
    reason_codes: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_response_dict(self) -> dict[str, object]:
        """Return a JSON-ready response containing no detected raw PII."""

        return {
            "address_text": self.address_text,
            "redacted_text": self.redacted_text,
            "entities": [entity.to_dict() for entity in self.entities],
            "reason_codes": list(self.reason_codes),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class _Detection:
    kind: PIIType
    start: int
    end: int
    removal_start: int
    removal_end: int
    replacement: str


_MOBILE_CANDIDATE_RE = re.compile(
    r"(?<![\w+])(?:\+?62[\s().-]*8(?:[\s().-]*\d){8,11}|08(?:[\s().-]*\d){8,11})(?!\w)"
)
_PHONE_LABEL_RE = re.compile(
    r"(?i)(?:\b(?:tel(?:p|epon)?|telepon|phone|hp|wa|whatsapp|no\.?\s*hp)\b\s*[:.=\-]?\s*)$"
)
_LANDLINE_AFTER_LABEL_RE = re.compile(
    r"(?i)\b(?:tel(?:p|epon)?|telepon|phone)\b\s*[:.=\-]?\s*"
    r"(?P<number>\(?0[2-9]\d{1,3}\)?(?:[\s.-]*\d){5,9})(?!\w)"
)
_IDENTIFIER_LABEL_RE = re.compile(
    r"(?i)(?:\b(?:nik|npsn|resi|order|pesanan|invoice|rekening|kode)\b\s*[:#.=\-]?\s*)$"
)
_NAME_LABEL_RE = re.compile(
    r"(?i)(?<!\w)(?:nama\s+penerima|penerima|a\.?\s*n\.?|atas\s+nama)\s*[:=\-]\s*"
)
_ADDRESS_START_RE = re.compile(
    r"(?i)\s+(?=(?:jl\.?|jalan|jln\.?|gg\.?|gang|kp\.?|kampung|dusun|"
    r"rt\b|rw\b|blok\b|no\.?\s*\d|desa\b|kel\.?|kec\.?|kab\.?|kota\b))"
)
_NAME_WORD_RE = re.compile(r"^[^\W\d_]+(?:[-'][^\W\d_]+)*$", re.UNICODE)
_NAME_TITLES = {"bapak", "bpk", "ibu", "bu", "sdr", "sdri", "pak"}


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _valid_mobile(value: str) -> bool:
    digits = _digits(value)
    if digits.startswith("62"):
        digits = "0" + digits[2:]
    return 10 <= len(digits) <= 13 and digits.startswith("08") and digits[2] != "0"


def _valid_landline(value: str) -> bool:
    digits = _digits(value)
    return 9 <= len(digits) <= 13 and digits.startswith("0") and digits[1] in "2345679"


def _label_before(text: str, start: int, pattern: re.Pattern[str]) -> re.Match[str] | None:
    window_start = max(0, start - 28)
    return pattern.search(text[window_start:start])


def _phone_detections(text: str) -> list[_Detection]:
    detections: list[_Detection] = []

    for match in _MOBILE_CANDIDATE_RE.finditer(text):
        if not _valid_mobile(match.group(0)):
            continue
        positive_label = _label_before(text, match.start(), _PHONE_LABEL_RE)
        if positive_label is None and _label_before(text, match.start(), _IDENTIFIER_LABEL_RE):
            continue
        removal_start = match.start()
        if positive_label is not None:
            removal_start = max(0, match.start() - 28) + positive_label.start()
        detections.append(
            _Detection(
                kind="PHONE",
                start=match.start(),
                end=match.end(),
                removal_start=removal_start,
                removal_end=match.end(),
                replacement=PHONE_REDACTED,
            )
        )

    occupied = [(item.start, item.end) for item in detections]
    for match in _LANDLINE_AFTER_LABEL_RE.finditer(text):
        number = match.group("number")
        start, end = match.span("number")
        if not _valid_landline(number):
            continue
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        detections.append(
            _Detection(
                kind="PHONE",
                start=start,
                end=end,
                removal_start=match.start(),
                removal_end=end,
                replacement=PHONE_REDACTED,
            )
        )

    return sorted(detections, key=lambda item: item.start)


def _valid_recipient_name(value: str) -> bool:
    words = value.split()
    if words and words[0].casefold().rstrip(".") in _NAME_TITLES:
        words = words[1:]
    return 1 <= len(words) <= 5 and all(_NAME_WORD_RE.fullmatch(word.rstrip(".")) for word in words)


def _recipient_name_detections(text: str) -> list[_Detection]:
    detections: list[_Detection] = []
    for marker in _NAME_LABEL_RE.finditer(text):
        tail = text[marker.end() :]
        separator_positions = [position for token in (",", ";", "\n", "\r") if (position := tail.find(token)) >= 0]
        candidate_end = min(separator_positions, default=len(tail))
        address_start = _ADDRESS_START_RE.search(tail[:candidate_end])
        if address_start:
            candidate_end = address_start.start()
        candidate = tail[:candidate_end].strip()
        if not candidate or not _valid_recipient_name(candidate):
            continue
        value_start = marker.end() + len(tail[:candidate_end]) - len(tail[:candidate_end].lstrip())
        value_end = value_start + len(candidate)
        detections.append(
            _Detection(
                kind="RECIPIENT_NAME",
                start=value_start,
                end=value_end,
                removal_start=marker.start(),
                removal_end=value_end,
                replacement=NAME_REDACTED,
            )
        )
    return detections


def _non_overlapping(detections: Iterable[_Detection]) -> list[_Detection]:
    selected: list[_Detection] = []
    for item in sorted(detections, key=lambda value: (value.start, value.end)):
        if selected and item.start < selected[-1].end:
            continue
        selected.append(item)
    return selected


def _replace_value_spans(text: str, detections: Iterable[_Detection]) -> str:
    output = text
    for item in sorted(detections, key=lambda value: value.start, reverse=True):
        output = output[: item.start] + item.replacement + output[item.end :]
    return output


def _remove_pii_fields(text: str, detections: Iterable[_Detection]) -> str:
    output = text
    for item in sorted(detections, key=lambda value: value.removal_start, reverse=True):
        output = output[: item.removal_start] + " " + output[item.removal_end :]
    output = re.sub(r"\s+", " ", output).strip()
    output = re.sub(r"^[,;:\-]+\s*|\s*[,;:\-]+$", "", output).strip()
    output = re.sub(r"(?:,\s*){2,}", ", ", output)
    return output


NameDetector = Callable[[str], list[_Detection]]


def process_pii(
    text: str,
    *,
    _name_detector: NameDetector = _recipient_name_detections,
) -> PIIProcessingResult:
    """Extract confirmed PII and return safe text for each consumer.

    Name extraction is fail-open: an unexpected name-rule failure preserves the
    original address content, while independently confirmed phones remain
    redacted.  The private detector argument exists for deterministic fault
    testing and is not part of the normal integration surface.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    phones = _phone_detections(text)
    warnings: list[str] = []
    try:
        names = _name_detector(text)
    except Exception:  # fail open without exposing exception content or raw input
        names = []
        warnings.append("RECIPIENT_NAME_EXTRACTION_FAILED")

    detections = _non_overlapping([*phones, *names])
    entities = tuple(
        PIIEntity(
            type=item.kind,
            start=item.start,
            end=item.end,
            redacted_value=item.replacement,
        )
        for item in detections
    )
    return PIIProcessingResult(
        address_text=_remove_pii_fields(text, detections),
        redacted_text=_replace_value_spans(text, detections),
        entities=entities,
        reason_codes=(PII_DETECTED,) if detections else (),
        warnings=tuple(warnings),
    )


def redact_for_logging(value: object) -> str:
    """Return a safe representation for logs and debug output."""

    if isinstance(value, PIIProcessingResult):
        return repr(value)
    return process_pii(str(value)).redacted_text


__all__ = [
    "NAME_REDACTED",
    "PHONE_REDACTED",
    "PII_DETECTED",
    "PIIEntity",
    "PIIProcessingResult",
    "process_pii",
    "redact_for_logging",
]

"""Consent-gated geocoding with administrative cross-validation (ALM-029).

Geocoding is P1 and **disabled by default**: with no provider configured the
result is an explicit "not requested" and no external call is ever attempted.
That keeps the P0 decision path unchanged, as the frozen scope requires.

The provider is injected. Credentials belong to the provider implementation and
are read from the environment there, so no key reaches this module, the
response, or a log line.

Representation notes, forced by the frozen ALM-025 contract:

* ``geocoding.status`` has exactly four values, and ``error_code`` is only
  allowed on ``EXTERNAL_FAILURE``. A successful lookup whose precision is too
  coarse, or whose administrative components disagree with ours, therefore maps
  to ``AMBIGUOUS`` -- the contract's "needs a human" state -- rather than
  carrying a ``LOW_PRECISION`` or ``ADMIN_MISMATCH`` error code. The findings
  are still returned: ``precision`` and the geocoder's ``components`` let a
  caller see exactly why.
* Expressing those two as codes would require changing the frozen contract,
  which a P1 feature may not do to P0 semantics. `docs/geocoding.md` records
  this.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .address_normalizer import ValueSource

#: Reason codes this module can attach to a failed lookup.
GEOCODE_NOT_FOUND = "GEOCODE_NOT_FOUND"
GEOCODE_TIMEOUT = "GEOCODE_TIMEOUT"
GEOCODE_RATE_LIMITED = "GEOCODE_RATE_LIMITED"
GEOCODE_UNAVAILABLE = "GEOCODE_UNAVAILABLE"

#: Findings that require human confirmation. They are surfaced as AMBIGUOUS
#: rather than as error codes; see the module docstring.
LOW_PRECISION = "LOW_PRECISION"
ADMIN_MISMATCH = "ADMIN_MISMATCH"

#: Precision labels, coarse to fine. Anything below ``rooftop`` needs a human.
PRECISION_ROOFTOP = "rooftop"
CONFIRMING_PRECISIONS = frozenset({"street", "region", "locality", "approximate"})

#: Administrative fields cross-checked against the ALAMATIN result.
CROSS_CHECKED_FIELDS = ("KOTA_KABUPATEN", "PROVINSI", "KODEPOS")

DEFAULT_TIMEOUT_SECONDS = 5.0


class GeocodeError(RuntimeError):
    """Base class for provider failures that must not crash a request."""


class GeocodeTimeout(GeocodeError):
    """The provider did not answer in time."""


class GeocodeRateLimited(GeocodeError):
    """The provider refused the call for quota reasons."""


class GeocodeUnavailable(GeocodeError):
    """The provider failed for any other reason it chose to report."""


@dataclass(frozen=True, slots=True)
class GeocodeCandidate:
    """One provider result, already stripped of anything provider-specific."""

    latitude: float
    longitude: float
    precision: str
    provider: str
    place_id: str | None = None
    components: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (("latitude", self.latitude), ("longitude", self.longitude)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise GeocodeError(f"{name} must be a number")
        if not -90 <= self.latitude <= 90:
            raise GeocodeError("latitude out of range")
        if not -180 <= self.longitude <= 180:
            raise GeocodeError("longitude out of range")
        if not self.precision.strip():
            raise GeocodeError("precision is required")
        if not self.provider.strip():
            raise GeocodeError("provider is required")


class GeocodeProvider(Protocol):
    """A geocoding backend. Implementations own their own credentials."""

    def lookup(self, address_text: str, *, timeout: float) -> GeocodeCandidate | None:
        """Return a candidate, or None when the address is not found."""


def _not_requested() -> dict[str, Any]:
    """The empty result the contract requires when nothing was looked up."""

    return {
        "status": "NOT_REQUESTED",
        # False because consent describes whether it was *exercised* for this
        # result. Nothing was looked up, so nothing was consented to. The
        # contract enforces this pairing.
        "consent": False,
        "provider": None,
        "precision": None,
        "latitude": None,
        "longitude": None,
        "components": [],
        "error_code": None,
    }


def _failure(provider: str, error_code: str) -> dict[str, Any]:
    return {
        "status": "EXTERNAL_FAILURE",
        "consent": True,
        "provider": provider,
        "precision": None,
        "latitude": None,
        "longitude": None,
        "components": [],
        "error_code": error_code,
    }


def _coordinate(value: float) -> dict[str, Any]:
    return {"value": float(value), "source": ValueSource.RETURNED_BY_GEOCODER.value}


def _components(candidate: GeocodeCandidate) -> list[dict[str, Any]]:
    """Project the geocoder's administrative fields into contract components."""

    from .label_schema import ENTITY_TYPES

    return [
        {
            "field": field_name,
            "result": {
                "value": str(candidate.components[field_name]),
                "source": ValueSource.RETURNED_BY_GEOCODER.value,
                # Never confirmed by the geocoder. A rooftop hit is still not a
                # verified location until a human says so.
                "confirmed": False,
                "model_score": None,
                "previous_value": None,
            },
        }
        for field_name in ENTITY_TYPES
        if field_name in candidate.components
        and str(candidate.components[field_name]).strip()
    ]


def cross_validate(
    candidate: GeocodeCandidate, alamatin_values: Mapping[str, str]
) -> tuple[str, ...]:
    """Return the cross-checked fields where the geocoder disagrees with us.

    Comparison is case- and whitespace-insensitive. A field missing on either
    side is not a disagreement: absence is not evidence of conflict.
    """

    mismatched: list[str] = []
    for field_name in CROSS_CHECKED_FIELDS:
        ours = str(alamatin_values.get(field_name, "")).strip().casefold()
        theirs = str(candidate.components.get(field_name, "")).strip().casefold()
        if not ours or not theirs:
            continue
        if ours != theirs:
            mismatched.append(field_name)
    return tuple(mismatched)


@dataclass(frozen=True, slots=True)
class GeocodingOutcome:
    """The contract block plus the findings a caller may want to explain."""

    block: dict[str, Any]
    findings: tuple[str, ...] = ()
    mismatched_fields: tuple[str, ...] = ()

    @property
    def requires_confirmation(self) -> bool:
        return self.block["status"] == "AMBIGUOUS"


class GeocodingService:
    """Resolve coordinates only when a caller explicitly consented."""

    def __init__(
        self,
        provider: GeocodeProvider | None = None,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise GeocodeError("timeout_seconds must be positive")
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    def resolve(
        self,
        address_text: str,
        *,
        consent: bool,
        alamatin_values: Mapping[str, str] | None = None,
    ) -> GeocodingOutcome:
        """Return the contract geocoding block for this address."""

        # Two independent gates. Either one alone stops the external call, so a
        # configuration mistake cannot turn into an unconsented request.
        if not consent or self.provider is None:
            return GeocodingOutcome(block=_not_requested())

        provider_name = getattr(self.provider, "name", type(self.provider).__name__)
        try:
            candidate = self.provider.lookup(
                address_text, timeout=self.timeout_seconds
            )
        except GeocodeTimeout:
            return GeocodingOutcome(
                block=_failure(provider_name, GEOCODE_TIMEOUT),
                findings=(GEOCODE_TIMEOUT,),
            )
        except GeocodeRateLimited:
            return GeocodingOutcome(
                block=_failure(provider_name, GEOCODE_RATE_LIMITED),
                findings=(GEOCODE_RATE_LIMITED,),
            )
        except Exception:
            # Any other provider fault is reported as unavailable. The exception
            # is deliberately not inspected or logged: it may quote the address.
            return GeocodingOutcome(
                block=_failure(provider_name, GEOCODE_UNAVAILABLE),
                findings=(GEOCODE_UNAVAILABLE,),
            )

        if candidate is None:
            return GeocodingOutcome(
                block=_failure(provider_name, GEOCODE_NOT_FOUND),
                findings=(GEOCODE_NOT_FOUND,),
            )

        mismatched = cross_validate(candidate, alamatin_values or {})
        findings: list[str] = []
        if candidate.precision != PRECISION_ROOFTOP:
            findings.append(LOW_PRECISION)
        if mismatched:
            findings.append(ADMIN_MISMATCH)

        block = {
            # AMBIGUOUS is the contract's "needs a human" state. error_code is
            # reserved for failures, so these findings cannot be encoded there.
            "status": "AMBIGUOUS" if findings else "SUCCESS",
            "consent": True,
            "provider": provider_name,
            "precision": candidate.precision,
            "latitude": _coordinate(candidate.latitude),
            "longitude": _coordinate(candidate.longitude),
            "components": _components(candidate),
            "error_code": None,
        }
        return GeocodingOutcome(
            block=block,
            findings=tuple(findings),
            mismatched_fields=mismatched,
        )


__all__ = [
    "ADMIN_MISMATCH",
    "CONFIRMING_PRECISIONS",
    "CROSS_CHECKED_FIELDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "GEOCODE_NOT_FOUND",
    "GEOCODE_RATE_LIMITED",
    "GEOCODE_TIMEOUT",
    "GEOCODE_UNAVAILABLE",
    "LOW_PRECISION",
    "PRECISION_ROOFTOP",
    "GeocodeCandidate",
    "GeocodeError",
    "GeocodeProvider",
    "GeocodeRateLimited",
    "GeocodeTimeout",
    "GeocodeUnavailable",
    "GeocodingOutcome",
    "GeocodingService",
    "cross_validate",
]

# Consent-gated geocoding (ALM-029)

Geocoding is **P1 and disabled by default**. With no provider configured no
external call is ever attempted and the result is an explicit "not requested",
so the P0 decision path is unchanged. This satisfies the frozen scope, which
requires the P0 API to return a disabled result rather than silently invoking an
external service, and forbids P1 from changing P0 semantics.

Implementation: `alamatin.geocoding`. It is wired into `AddressPipeline` through
an injected `GeocodingService`; the default instance has no provider.

## Two independent gates

An external call happens only when **both** hold:

1. the request granted `geocoding_consent`, and
2. a provider is configured.

Either gate alone stops the call, so a configuration mistake cannot become an
unconsented request. A test asserts the provider records zero calls without
consent.

## Credentials

Providers own their own credentials and read them from their own environment. No
key passes through `alamatin.geocoding`, and no provider exception text is
inspected, returned, or logged — an exception may quote the key or the address.
A test asserts that neither a secret nor the address appears in the result or in
captured logs when a provider raises with both in its message.

## Only PII-safe text leaves the system

The pipeline calls the geocoder with `pii.address_text`, never the raw input, so
a recipient name or phone number is never sent to a third party. A test asserts
this on a mixed-PII address.

## Status mapping

| Situation | `status` | `error_code` |
|---|---|---|
| No consent, or no provider | `NOT_REQUESTED` | none |
| Rooftop precision, administrative fields agree | `SUCCESS` | none |
| Precision coarser than rooftop | `AMBIGUOUS` | none |
| Geocoder's city/province/postcode disagrees with ours | `AMBIGUOUS` | none |
| Address not found | `EXTERNAL_FAILURE` | `GEOCODE_NOT_FOUND` |
| Provider timed out | `EXTERNAL_FAILURE` | `GEOCODE_TIMEOUT` |
| Provider refused for quota | `EXTERNAL_FAILURE` | `GEOCODE_RATE_LIMITED` |
| Any other provider fault | `EXTERNAL_FAILURE` | `GEOCODE_UNAVAILABLE` |

### Why `LOW_PRECISION` and `ADMIN_MISMATCH` are not error codes

The issue asks for `LOW_PRECISION` and `ADMIN_MISMATCH` alongside
`GEOCODE_NOT_FOUND`. The frozen contract does not allow it: `geocoding.status`
has exactly four values, and the contract's own invariants permit `error_code`
only on `EXTERNAL_FAILURE`. A successful lookup that merely needs a human is not
an external failure, so encoding it that way would misreport a working service
as broken and force the coordinates to be discarded.

Both findings therefore map to `AMBIGUOUS`, the contract's "needs a human"
state, and remain fully visible: `precision` carries the coarseness and
`components` carries the geocoder's administrative values for comparison.
`GeocodingOutcome.findings` exposes the codes to in-process callers, and
`mismatched_fields` names the disagreeing fields.

Turning them into wire-level codes would require changing the frozen ALM-025
contract. A P1 feature may not do that to P0 semantics, so it is left as a
decision for the team rather than made here.

## A rooftop hit is not a verified location

Every component the geocoder returns carries `source: returned_by_geocoder` and
`confirmed: false`. Nothing the geocoder says is confirmed on its own; only an
explicit human action may set `confirmed`. The frozen scope forbids claiming a
verified physical location without appropriate evidence and consent.

## A geocoder failure never invalidates an address

Geocoding is resolved **after** the quality gate, and its result is not an input
to the gate. A timeout, a rate limit, or a not-found leaves a `SIAP_DIPROSES`
address ready. Tested directly.

## Cross-validation

`KOTA_KABUPATEN`, `PROVINSI`, and `KODEPOS` are compared case- and
whitespace-insensitively. A field missing on either side is not a disagreement:
absence is not evidence of conflict.

## Enabling it

Implement the `GeocodeProvider` protocol — `lookup(address_text, *, timeout)`
returning a `GeocodeCandidate` or `None`, raising `GeocodeTimeout`,
`GeocodeRateLimited`, or any other exception for a fault — and pass
`GeocodingService(provider)` to `AddressPipeline`.

Not done here, and deliberately: no provider has been selected, no credentials
exist, and enabling a P1 feature would put it in the release candidate, which
the freeze forbids. `POST /geocode` therefore still answers `403 CONSENT_REQUIRED`
without consent and `501 FEATURE_NOT_ENABLED` with it.

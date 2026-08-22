# Data handling: sources, consent, logging, cache, retention

What this system holds, for how long, and what it is permitted to do with it.
Every statement here is checkable against the file named beside it.

## Sources, licences, and attribution

Per-source provenance, licence status, PII decision, and any documented
acquisition exception live in [`data/sources.md`](../data/sources.md) — that file
is the record, and this section only states the obligations that follow from it.

| Source family | Licence status | Obligation this places on us |
|---|---|---|
| `kemendagri_wilayah_2025` | public administrative reference | cite the source and its retrieval date |
| `open_data_jabar_*` | `internal_noncommercial_only` | never redistribute the raw extract; only approved derived files may go public |
| `kodepos_dev_rest_api` | redistribution prohibited without written permission | internal validation only; raw observations stay internal |
| `pos_indonesia_postcode_search` | hold | spot-check only, under a documented exception; no bulk acquisition |
| `osm_geofabrik_java_2026_08_14` | ODbL 1.0 | carry the attribution below wherever OSM-derived data is shown |
| `alamatin_synthetic_*` | ours | no obligation; also no evidentiary weight for real input |

**Required OSM attribution**, verbatim: `Copyright OpenStreetMap contributors;
data available under ODbL 1.0`, linked to
<https://www.openstreetmap.org/copyright>.

Exactly **four** derived files are approved for the public repository by the
project-owner decision dated 2026-08-13:
`data/processed/jabar-reference-v1-verified.json`,
`data/final/jabar-postal-app-lookup.csv`,
`jabar-reference-v1-exceptions.csv`, and `jabar-reference-v1-summary.json`.
Raw extracts, per-source value columns, reviewer worksheets, and raw
Kodepos.dev / Pos Indonesia observations are excluded by name. The list is
enforced by `scripts/check_repository.py`, not by memory.

## Consent

Two separate consents, neither implied by the other.

**Geocoding.** No address text leaves the process without an explicit
`consent.geocoding` flag on the request *and* a configured provider. Both gates
are independent, and the release candidate configures no provider — so in this
build no external call is possible at all. `/geocode` answers `403` without
consent. See [`geocoding.md`](geocoding.md).

**Interviews.** Each of the four transcripts in
[`docs/research/interviews/`](research/interviews/R01-fulfillment.md) opens with
a recorded consent confirmation: voluntary participation, the right to skip a
question or stop at any time, no sharing of customer personal data, and
anonymised notes. Participants are referred to by code (`R01`…`R04`).

**User study.** Not yet run. The protocol requires consent to be taken before
any comment — purpose and recording explained, and quote permission asked and
recorded *before* a comment is taken; a verbatim quote may be published only
when that flag is true. The record schema has no field for a name, contact
detail, employer, age, or gender, and a test asserts none can be added. See
[`user-study-protocol.md`](user-study-protocol.md).

## What is logged

`alamatin.api` logs exactly four events, all through
`logging.getLogger("alamatin.api")`:

| Event | Fields |
|---|---|
| `api_request` | route, HTTP status, request id, error code |
| `api_client_disconnected` | route |
| `api_error_document_rejected` | error code |
| internal handler failure | route, error code |

**Address text is never logged, and neither is exception text.** The fields
above are the whole set — a route, a status, an opaque request id, and a frozen
error code. Where a value must appear in a diagnostic at all,
`pii.redact_for_logging` routes it through the same redaction the response uses.

The request id is client-supplied and opaque to us; it is a correlation handle,
not an identifier of a person, and nothing joins it to anything else.

## Cache

**There is none.** No response cache, no result store, no memoization of parse
results. Every response carries `cache-control: no-store`, so an intermediary
is instructed not to retain it either.

The governed reference is read from disk at startup; that is a read of our own
data, not a cache of user input.

## Retention

**Address text is retained for the lifetime of the request and no longer.**

| What | Where it lives | How long |
|---|---|---|
| submitted address text | request scope in memory | until the response is sent |
| parse result | the HTTP response | not stored server-side |
| redacted text | inside the response document | as long as the client keeps it |
| logs | stdout / journal | per node policy; contains no address text |
| governed reference | disk, read-only | version-controlled |

The process writes nothing to disk on the request path. Re-validation is
stateless: `/validate` re-evaluates the text it is given, because the server
holds no record of an earlier submission or of which suggestion a user accepted
— the client must send the corrected text. A result is therefore reproducible
from its input alone, and there is no accumulated store to breach, export, or
have to delete.

There is no user account, no session, and no analytics collection, so there is
nothing to delete on request beyond the log lines described above.

## Related

- [`pii-handling.md`](pii-handling.md) — how detection and redaction work, and
  what the conservative name rule deliberately does not catch.
- [`artifact-policy.md`](artifact-policy.md) — which artifacts may be committed.
- [`architecture.md`](architecture.md) — the boundaries this document describes.
- [`limitations.md`](limitations.md) — what none of this may be claimed to prove.

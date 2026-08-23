# ALAMATIN Product Scope and Claim Contract

- Scope version: `1.0.0`
- Freeze date: 22 August 2026
- Geographic release scope: Jawa Barat
- Product mode: single-address, pre-fulfillment review
- Change policy: frozen for the COMPFEST 18 submission candidate

## Frozen positioning

**ALAMATIN is a pre-fulfillment address quality gate that helps Indonesian seller operators identify incomplete, ambiguous, or administratively conflicting address components and request human confirmation before a waybill is created.**

This positioning is supported by the four anonymized interviews synthesized in
[`docs/research/persona-interview-synthesis.md`](research/persona-interview-synthesis.md).
It does not claim that ALAMATIN verifies a physical location or prevents a
delivery failure.

## Primary user and decision

The primary user is a seller-side admin fulfillment operator, warehouse staff
member, or UMKM owner handling an order before courier handoff. ALAMATIN helps
that user decide whether the address can continue, requires clarification, or
contains an explicit conflict. The buyer, platform, or another authorized human
remains responsible for confirming substantive corrections.

## Priority freeze

### P0: required for the submission candidate

P0 is one auditable single-address path:

1. redact recipient PII from downstream-safe text and logs;
2. extract the ten canonical address component types;
3. normalize deterministic formatting while retaining provenance;
4. validate the Jawa Barat administrative chain and postcode against the
   governed reference version;
5. return one operational status with reason codes, affected fields, and a
   clarification question;
6. require explicit confirmation for substantive suggestions;
7. expose the shared output contract through the backend and single-address UI;
8. demonstrate the integrated path with privacy, reproducibility, evaluation,
   documentation, and submission evidence.

The P0 delivery set is represented by the issues labeled `priority:P0`, with
feature scope centered on ALM-021 through ALM-028 and evidence/submission work
in ALM-032 through ALM-042. Evaluation metrics may only be reported from the
frozen protocol and recorded artifacts.

### P1: useful but not required by P0

- OSM street/landmark extraction (ALM-009) and the libpostal comparison
  (ALM-016) may be used as evidence but are not runtime dependencies.
- Consent-gated geocoding (ALM-029) and map confirmation (ALM-030) are optional.
  The P0 API returns an explicit disabled/not-requested result instead of
  silently invoking an external service.
- Batch CSV processing (ALM-031) is optional. A bounded contract may exist, but
  the operational endpoint remains disabled until its issue is completed.

P1 cannot delay, weaken, or change the P0 single-address decision semantics.

### P2: post-submission backlog

- interactive draggable map (ALM-101);
- batch analytics dashboard (ALM-102);
- anonymized feedback loop (ALM-103);
- model-lite or ONNX optimization (ALM-104).

P2 work must not begin before the P0 release and evidence package are stable.

## Explicitly outside the current scope

- national reference coverage beyond the documented Jawa Barat release;
- proof that an address is deliverable or that a courier visited a location;
- delivery-failure prediction, fraud detection, or a delivery risk score;
- autonomous changes to substantive address values;
- background tracking, courier dispatch, route optimization, or SLA decisions;
- account management, history dashboards, and multi-tenant administration;
- mandatory external geocoding or map services;
- production learning from customer corrections;
- replacing the marketplace, buyer, courier, or human as the final authority.

## Canonical component and critical-field policy

The canonical extracted component types are `JALAN`, `NOMOR`, `RT`, `RW`,
`KELURAHAN`, `KECAMATAN`, `KOTA_KABUPATEN`, `PROVINSI`, `KODEPOS`, and
`DETAIL_LOKASI`.

For quality-gate v1, the critical deterministic validation fields are:

- `KELURAHAN`;
- `KECAMATAN`;
- `KOTA_KABUPATEN`;
- `PROVINSI`;
- `KODEPOS`.

These fields are critical because they can be compared against a versioned
administrative reference. `JALAN`, `NOMOR`, `RT`, `RW`, and `DETAIL_LOKASI`
remain visible and useful for clarification, but the current reference does not
justify treating their absence or form as proof that an address is invalid.

One completeness requirement applies outside that set: an address must name a
street-level locator -- `JALAN` or `DETAIL_LOKASI` -- or the gate raises a
**medium** `MISSING_STREET_LOCATOR` issue and returns `PERLU_KONFIRMASI`. A
perfect administrative chain with no street is not deliverable. It stays medium
because the reference cannot check a street name, so this asks rather than
declares. `NOMOR` is **not** required: 71% of real evaluation addresses carry no
house number, and requiring one would flag most valid Indonesian addresses. See
[`decision-log.md`](decision-log.md) DEC-010.
Names and phone numbers are handled as PII, not NER address components.

## Frozen operational statuses

The first matching rule wins:

1. `TIDAK_VALID`: at least one high-severity, reference-supported conflict is
   unresolved.
2. `PERLU_KONFIRMASI`: there is no high-severity conflict, but at least one
   medium issue remains, such as missing administrative context, ambiguity, a
   reference coverage gap, or an unapplied semantic suggestion.
3. `SIAP_DIPROSES`: the frozen quality gate returns no unresolved issue, which
   now includes naming a street-level locator.

`SIAP_DIPROSES` means only that no issue was found by the frozen rules and
reference version. It does not mean the physical location is verified, the
recipient is reachable, or delivery will succeed. A reference coverage gap is
not proof that the user's address is wrong. An external geocoder failure cannot
turn a locally valid address into `TIDAK_VALID`.

## Allowed claims

ALAMATIN may claim, when supported by the linked implementation and evidence,
that it:

- extracts the ten documented address component types;
- performs deterministic formatting normalization with provenance;
- checks a supplied administrative chain and postcode against the governed
  Jawa Barat reference version;
- identifies documented conflicts, ambiguity, missing administrative context,
  or reference coverage gaps;
- redacts supported PII patterns from downstream-safe output and logs;
- returns explainable status, reason codes, affected fields, clarification
  questions, versions, and audit events;
- requires human confirmation before a substantive suggestion becomes final;
- achieved a specifically named metric on a specifically named frozen dataset
  under the documented evaluation protocol.

## Claims that are not allowed

The proposal, UI, API, video, README, and spoken presentation must not claim:

- a delivery risk score or probability of delivery failure;
- a reduction in failed deliveries, returns, time, or cost unless measured by a
  controlled study and linked to its evidence;
- a verified, accurate, or ground-truth physical location without appropriate
  geospatial evidence and consent;
- that `model_score` is calibrated confidence or probability;
- that a reference coverage gap proves an address is invalid;
- national, all-marketplace, or all-courier coverage;
- that any important correction was applied without human confirmation;
- causal conclusions from the four exploratory interviews.

## H-1 feasibility cut-line

The internal submission target is 24 August 2026. P0 remains feasible only
under the following frozen cut-line:

| Date | Required outcome | Parallel owners |
|---|---|---|
| 22 August | Freeze this contract; close completed backend contracts; finish UI and end-to-end integration | Product/Delivery + Frontend |
| 23 August | Run automated/privacy/clean-clone QA; freeze the release candidate; execute evaluation, latency/failure analysis, and the prepared user-study protocol | QA + ML/Evaluation + Research |
| 24 August | Freeze evidence; finalize documentation, proposal, and videos; run final cross-artifact and submission QA | Whole team |

No P1 or P2 implementation may enter the release candidate after this freeze.
If a P0 item cannot meet its acceptance criteria, the team must remove the
dependent claim or demo path rather than substitute a placeholder or unverified
result.

## Scope change control

After version `1.0.0`, any proposed scope change must:

1. be filed as a new or existing backlog issue;
2. state its priority, dependencies, evidence requirement, privacy impact, and
   effect on the H-1 critical path;
3. leave the frozen release candidate unchanged unless the whole team approves
   a versioned superseding decision;
4. update this document and the decision log through a reviewed pull request;
5. never retroactively broaden claims supported by existing evidence.

## Approval record

The scope is approved only when all three repository collaborators approve the
scope-freeze pull request:

| Team member | Role represented | Approval evidence |
|---|---|---|
| `@yongkytristan` | Project owner / Product and Delivery | Scope-freeze PR approval or explicit issue approval |
| `@Kevinsweep` | ML and Evaluation | Scope-freeze PR approval |
| `@JasonEvan` | Frontend / Product implementation | Scope-freeze PR approval |

Until those approvals are recorded, the document is a proposed freeze and the
"scope approved by the whole team" acceptance criterion remains incomplete.

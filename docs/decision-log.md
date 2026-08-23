# Decision log

Record durable technical, data, product, and governance decisions here. Do not
overwrite previous decisions; add a superseding entry that links to the old one.

## Numbering

Numbers are unique and permanent once published. A published number is never
reused for a different decision, even if a gap results.

`DEC-003` and `DEC-004` are **reserved** for the postal-review adjudication
decisions dated 12 August 2026, which are recorded in the internal repository
and not yet published here. They are not missing; they belong to work whose
supporting evidence is governed by [`../data/sources.md`](../data/sources.md).

The scope-freeze entry below was originally recorded as `DEC-003` and is now
`DEC-006`. That renumbering is deliberate: the postal decisions predate it by
ten days, so `DEC-003` was already theirs, and two different decisions cannot
share a number across the two repositories. This note exists so the change is
auditable rather than silent.

## DEC-001 — Repository workflow baseline

- Date: 2026-08-10
- Status: accepted
- Decision: use `main` with short-lived `feat/*` and `fix/*` branches, small pull
  requests, at least one approving reviewer, and required repository checks.
- Rationale: supports fast delivery while retaining reviewable evidence.
- Consequences: direct changes to `main` should be disabled through branch
  protection once the first collaborator is added.

## DEC-002 — Dependency-free skeleton validation

- Date: 2026-08-10
- Status: accepted
- Decision: use Python 3.11 standard-library checks until the implementation
  stack is frozen.
- Rationale: avoids selecting dependencies before architecture decisions.
- Consequences: `requirements.lock` remains intentionally empty for now.

## DEC-005 — Pin uvicorn as the ASGI server

- Date: 2026-08-22
- Status: accepted
- Supersedes: the DEC-002 consequence that `requirements.lock` remains
  intentionally empty. DEC-002 itself still stands: the address pipeline in
  `src/alamatin/` continues to use only the Python standard library.
- Decision: adopt `uvicorn==0.52.4` as the ASGI server and pin it, with
  `click`, `h11`, and the conditional `colorama` and `typing_extensions`, in
  `requirements.lock` with wheel and sdist hashes.
- Rationale: `src/alamatin/api.py` is a dependency-free ASGI application, but
  the Dewacloud deploy needs something to serve it, and the node has neither
  `uvicorn` nor `gunicorn` installed. Pinning with hashes keeps the repository
  dependency policy intact; the deploy installs with `--require-hashes`, so an
  unpinned or unhashed requirement fails the deploy rather than fetching an
  unverified package.
- Consequences: the runtime stack is no longer standard-library-only, so a
  clean-clone check must install this lock file. Bumping the server is a
  reviewed change to this lock file, not an ad-hoc install on the node. The
  node requires Python 3.10+ for both this server and the application's use of
  `dataclass(slots=True)`; its system `python3` is 3.9, so deploys pin
  `python3.11` (see [`deployment.md`](deployment.md)).
- Amendment, 2026-08-22: this entry originally named `alamatin.api:app` as the
  service entrypoint. ALM-028 wired the pipeline into
  `alamatin.service:app`, which is what deployments must serve;
  `alamatin.api:app` is the transport with unconfigured handlers and answers
  `503` by design. See [`integration.md`](integration.md).

## DEC-006 — Freeze the single-address product scope and claim boundary

- Date: 2026-08-22
- Renumbered from `DEC-003` on 2026-08-23; see the Numbering section above.
- Status: accepted. The whole-team approval was given outside GitHub and is
  recorded on the project owner's confirmation in
  [issue #4](https://github.com/yongkytristan/ALAMATIN/issues/4); no formal
  review was left on the scope-freeze pull request.
- Decision: freeze ALAMATIN `1.0.0` as a Jawa Barat, single-address,
  pre-fulfillment quality gate with the status and claim semantics in
  [`product-scope.md`](product-scope.md). Geocoding and batch processing remain
  optional P1 work; P2 remains post-submission backlog.
- Rationale: the persona interviews support an explainable pre-waybill check,
  while current evidence does not support delivery-risk, failed-delivery, or
  verified-location claims.
- Consequences: new scope enters the backlog; P1/P2 cannot delay the release;
  unsupported claims and incomplete optional paths must be removed rather than
  represented by placeholders.

## DEC-007 — Descope the user-study execution from the 1.0.0 submission

- Date: 2026-08-23
- Status: accepted by the project owner.
- Decision: ALM-037's deliverable for `1.0.0` is the **study apparatus**, not a
  study result. The protocol, counterbalanced task generator, recording
  instrument, anonymisation schema, and the ALM-038 analysis harness are the
  shipped artifacts. Recruiting participants and running sessions moves to
  post-submission work.
- Rationale: the sessions require target-like participants and a facilitator,
  neither of which the remaining submission window can supply. The alternative
  considered and rejected was recording sessions that did not happen, which
  would be fabricated research data.
- Consequences:
  - No user-study number may be quoted anywhere. Every study field stays
    `not_measured` in [`../experiments/evidence/index.json`](../experiments/evidence/index.json),
    and the analysis harness must keep reporting `not_measured` rather than
    defaulting to a value.
  - The comparison this study was to supply — manual review against ALAMATIN on
    time, correct decisions, critical-error recall, and false corrections —
    remains **unmeasured**, and no claim may stand in for it. Recorded in
    [`limitations.md`](limitations.md).
  - The apparatus must stay runnable: whoever runs the study later inherits a
    tested generator, instrument, and analysis path, so their first session
    produces analysable data with no rework.
  - ALM-037 and ALM-038 close against this reduced scope. Their checklists were
    rewritten to the delivered scope on this date, with the execution items
    moved to the post-submission backlog rather than silently ticked.

## DEC-008 — Ship `regex-baseline-v1.1` and let the sealed figures go stale

- Date: 2026-08-23
- Status: accepted by the project owner.
- Decision: adopt two JALAN span rules in the rule extractor -- a second
  designator of the same type continues the span instead of opening a rival
  one, and the JALAN span cap moves from 5 to 6 tokens -- bump the extractor to
  `regex-baseline-v1.1`, and re-freeze the ALM-034 manifest around it.
- Measurement that justified it: on a pre-registered held-out half of
  `real_dev` (35 addresses; the partition is recorded as
  `data/interim/evaluation-splits/real-dev-tuning-partition.json` in the
  internal repository, alongside the governed split it partitions),
  entity F1 rises `0.8949` to `0.9027` and critical exact match `24/35` to
  `25/35`. The tuning half showed a larger gain, `+3` addresses against the
  held-out `+1`; the held-out figure is the one that counts.
- Cost accepted: on the synthetic split the change is marginally **worse**,
  entity F1 `0.8923` to `0.8922`. The synthetic generator does not produce the
  stacked-designator and long-street-name patterns the rules address, which is
  further evidence that synthetic performance is not a proxy for real.
- Consequences:
  - **The sealed evaluation now describes a previous extractor.** Its figures --
    entity F1 `0.8984`, critical exact match `87/130`, `0 of 130` reaching
    `SIAP_DIPROSES` -- were measured against `regex-baseline-v1`. Recorded in
    [`evaluation-results.md`](evaluation-results.md) and
    [`release-candidate.md`](release-candidate.md).
  - **The sealed set is not re-run.** One opening was authorised and is spent. A
    second opening would destroy the property that makes the number worth
    quoting. A stale figure that is honest about being stale beats a fresh
    figure with no guarantee behind it.
  - A test enforces that *only* the extractor may differ between the sealed
    record and the frozen manifest, so a silent change to the gate, normalizer,
    validator, or contract still fails.
  - The rule baseline was tuned on 35 of the 70 `real_dev` addresses, so no
    figure over the full 70 is a clean estimate for it. The comparison in
    [`approach-comparison.md`](approach-comparison.md) is ranked on the held-out
    half, where no approach in the table was tuned.
  - Rejected: the configuration that scored highest on the tuning half
    (`JALAN` cap 8, entity F1 `0.9338` there). It won by capturing a single
    eight-token example, which is fitting to one address rather than a rule. The
    cap was taken from the gold span-length distribution instead.
  - Also rejected: adding noise-specific designator spellings (`kat` for
    `kab`, a space-split `k ecamatan`) that would each have fixed exactly one
    tuning example.

## DEC-009 — Issues must name the reference value, not only the field

- Date: 2026-08-23
- Status: accepted by the project owner.
- Decision: every administrative issue states what the governed reference holds
  beside what the address carries. `"Komponen administratif berikut saling
  bertentangan: KECAMATAN."` becomes `"Menurut data wilayah Jawa Barat,
  Kelurahan/desa Braga tercatat berada di Kecamatan Sumur Bandung, sedangkan
  alamat ini menulis Coblong."`
- Rationale: naming only the field told a seller which field disagreed and
  nothing they could act on. The reference value was already available in the
  validator's candidate; it simply never reached the response.
- A value absent from the reference is described as **not matching the Jawa
  Barat reference data**, never as unrecognised and never as a wrong address.
  The first is unhelpful, the second is a claim the reference cannot support: a
  village missing from a 5,957-row Jawa Barat reference is a gap in that
  reference. The message keeps an explicit sentence saying the address is
  unverified rather than wrong, and a test asserts it.
- Consequences:
  - `evaluate_quality_gate` gains an optional `submitted` mapping. It affects
    prose only; a test asserts that wildly different submitted values leave the
    status, severities, and reason codes identical.
  - **The frozen contract is untouched.** The issue object has
    `additionalProperties: false` and six fixed fields, so no field was added;
    the reference value travels inside `message` and `clarification_question`,
    which are free-form strings.
  - `RULES_VERSION` stays `quality-gate-v1`. The rules it names -- status
    precedence, severities, and reason codes -- are unchanged; only prose
    changed, and the change is recorded by the manifest's file digests. Bumping
    it would imply the sealed evaluation's gate figures no longer apply, which
    would be false.
  - Reference values are shown as **evidence**, never applied. The frozen scope
    forbids applying a substantive change without a human, so no correction is
    proposed or written into any component.
  - The three UI demo addresses were replaced. Against the real backend all
    three previously returned `PERLU_KONFIRMASI`, so the product tour
    demonstrated nothing; and the fixture path routed by substring, which
    mis-classified an address as soon as its wording changed. Routing now
    matches the demo constants themselves.

## DEC-010 — Require a street locator, and deliberately not a house number

- Date: 2026-08-23
- Status: accepted by the project owner.
- Problem: `Kel. Braga, Kec. Sumur Bandung, Kota Bandung, Jawa Barat 40111`
  returned `SIAP_DIPROSES`. The administrative chain was perfect and the address
  was undeliverable -- nothing named a street, a kampung, or a landmark.
- Decision: a medium-severity `MISSING_STREET_LOCATOR` issue when neither
  `JALAN` nor `DETAIL_LOKASI` carries a value. Status becomes
  `PERLU_KONFIRMASI`.
- **`NOMOR` is deliberately not required.** On the `real_dev` split 71% of
  genuine addresses carry no house number and 53% carry no house-level locator
  of any kind. `KP. CIMANGGU, KECAMATAN CIBEBER, KAB CIANJUR` is a normal
  kampung address, not a defect. A rule that flagged half of all valid addresses
  would teach sellers to ignore the flag, so the requested "street and number"
  check ships as street only, with the measurement recorded here.
- Severity is medium, never high. [`product-scope.md`](product-scope.md) forbids
  treating the absence of `JALAN` as proof an address is invalid, because the
  governed reference cannot check a street name. Asking is allowed; declaring is
  not.
- Contract amendment, `1.0.0` -> `1.1.0`:
  - `MISSING_STREET_LOCATOR` is appended to the `reason_code` enum. The existing
    six keep their meaning and order, so a consumer switching on them still
    works.
  - Requests accept `1.0.0` **or** `1.1.0`; responses declare `1.1.0`. No client
    breaks, and the request examples stay at `1.0.0` on purpose as the proof.
  - `versions.contract` moves to `1.1.0` in the same amendment.
- Consequences:
  - `evaluate_quality_gate`'s `submitted` mapping now affects the status through
    this one rule. That was previously prose-only (DEC-009), so the test
    asserting it could not affect the status was restated to cover the conflict
    path specifically, with this rule named as the declared exception.
  - The sealed evaluation's figures are unaffected: the rule can only add
    issues, `SIAP_DIPROSES` was already `0 of 130`, and the entity metrics are
    extraction metrics no gate rule touches. The sealed drift allowance is now
    an explicit table naming each component and the decision that authorised it.
  - The release candidate is re-frozen around contract `1.1.0`.

### Amendment, 2026-08-23 — a house locator is required after all

The decision above skipped `NOMOR` on the strength of 71% of `real_dev`
addresses carrying none. **That evidence came from the wrong population.**
`real_dev` is 200 *school* addresses from the NPSN dataset (108 SD, 92 SMA), and
a school is a landmark in its own right, so `JL. PASIRLAYUNG, KECAMATAN
CIMENYAN` identifies it. This product serves sellers shipping to homes, where a
street with no door does not.

The target-domain evidence says the opposite, and it was already in the
repository. R01 (fulfillment) reported a package that looked normal for three
days, failed, and returned after eight -- "ternyata hanya nama perumahan tanpa
nomor rumah" -- and, asked what warning would help, answered "satu baris yang
menyebut bagian mana yang bermasalah dan alasannya, misalnya nomor rumah tidak
ada".

- Decision: a second medium issue, `MISSING_HOUSE_LOCATOR`, when none of
  `NOMOR`, `RT`, `RW`, or `DETAIL_LOKASI` carries a value. Contract `1.1.0` ->
  `1.2.0`, additive on the same terms: requests still accept `1.0.0`.
- `RT`, `RW`, and `DETAIL_LOKASI` satisfy it alongside `NOMOR`, because a kampung
  address is normally written that way and a courier can work with it. Requiring
  `NOMOR` alone would flag those.
- Two separate codes rather than one "incomplete", because R01 asked for the
  line to name *which* part is missing.
- Severity stays medium for the same reason as the street rule: the reference
  cannot check a house number, so this asks rather than declares.
- **Limitation, stated rather than measured away:** there is no consumer-address
  benchmark, so the false-positive rate of this rule on the target population is
  unmeasured. The 53%-of-school-addresses figure does not describe it. What
  bounds the cost is the severity: a flagged address gets a question, not a
  rejection.
- Any **one** house locator satisfies the rule; it is an OR, not an AND. Two
  stricter shapes were considered on 2026-08-23 and declined by the project
  owner:

  | Option | Rule | Passes on `real_dev` |
  |---|---|---|
  | **A (chosen)** | any one of `NOMOR`, `RT`, `RW`, `DETAIL_LOKASI` | 47% |
  | B | `NOMOR`, or (`RT` **and** `RW`), or `DETAIL_LOKASI` | 40% |
  | C | `NOMOR` **and** `RT` **and** `RW` | 4% |

  C is wrong for any population, not merely this one: on a formal street `RT`/`RW`
  is genuinely optional, and in a kampung a house number often does not exist --
  0 of the 17 kampung-style addresses in `real_dev` carry one. Requiring it would
  ask a seller for something that cannot be supplied.

  **Accepted consequence of choosing A:** `RT` without `RW`, or `RW` without
  `RT`, passes, and that does not truly pin one house -- RT 03 exists in every
  RW. Three `real_dev` addresses are in that state. Option B would close it for
  a cost of three addresses. It is left open deliberately; if it is revisited,
  B is the shape to adopt, not C.

  As above, the percentages come from 200 **school** addresses and must not be
  read as an estimate for consumer addresses.

## DEC-011 — Numeric tokens tolerate a trailing period

- Date: 2026-08-23
- Status: accepted by the project owner.
- Reported from use: in `Jl. Braga No. 5, RT. 5, RW. 6. Kel. Braga, ...` the `RW`
  field was not detected. A period used as a separator attaches to the token
  before it, so the tokenizer yields `RW.` then `6.`, and every numeric pattern
  allowed leading dots but not trailing ones. The number was silently dropped.
- Affected six patterns, not one: `RT_PATTERN`, `RW_PATTERN`, `NOMOR_PATTERN`,
  `NOMOR_MARKER_ONLY`, `BARE_NUMBER`, and `KODEPOS_PATTERN`. All now accept up to
  two trailing dots, symmetrically with the leading dots they already allowed.
- **The first attempt made things worse and that is the part worth remembering.**
  Fixing detection alone let the value `40111.` reach the administrative
  validator, which compared it with `40111` and reported a conflict -- a correct
  address declared `TIDAK_VALID` at high severity. Detection without
  canonicalisation converted a missing field into a false rejection.
  `_normalize_rt_rw` and `_normalize_postcode` were fixed in the same change.
- Extractor bumped to `regex-baseline-v1.2` and the release re-frozen, per the
  DEC-008 rule that behaviour must not change under a version with published
  numbers attached.
- **No measurable effect on either benchmark.** `real_dev` and `synthetic_dev`
  both score exactly as before: entity F1 `0.9149` and `0.8922`. The pattern does
  not occur in either. The evidence for this change is the reproduced input, not
  a metric -- and that is stated rather than dressed up as an improvement.
- Related finding: the synthetic generator's `separator` noise inserts commas
  only, never periods, which is why 5,250 generated examples never exercised
  this path. Another instance of synthetic coverage not matching real input.

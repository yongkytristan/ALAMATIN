# User-study protocol (ALM-037)

## Status: materials complete, sessions not run

Everything that can be built without people is built and tested:

| Item | State |
|---|---|
| Protocol and ground truth | complete, this document |
| Counterbalanced 20-task sets per participant | complete, `scripts/build_user_study_tasks.py` |
| Recording instrument | complete, emitted by the same script |
| Anonymisation rules | complete, enforced by the schema and tested |
| Analysis harness | ALM-038 |
| **Participant recruitment** | **not done — requires people** |
| **Session execution and data collection** | **not done — requires people** |

No participant has been recruited and no session has been run, so **no result
exists**. Nothing in this repository reports a user-study outcome, and the two
execution items above are deliberately left unticked on the issue. Recording a
participant who does not exist would be fabricated research data, which is not
something a submission can carry.

## Question

Does reviewing an address with ALAMATIN change how long a decision takes, and
how many real defects the reviewer catches, compared with reviewing it manually?

Nothing about delivery outcomes is asked, and no claim about deliveries,
returns, or failed deliveries can be drawn from this design. The frozen scope
forbids it and the sample size could not support it regardless.

## Participants

Three to five people whose day involves checking an address before a shipment:
seller-side admin or fulfilment staff, warehouse staff, or UMKM owners. The
generator refuses any count outside 3–5.

Recruitment is by direct approach. Participation is voluntary, unpaid, and can
stop at any point without giving a reason.

## Design

Within-participant, two conditions, counterbalanced.

* 20 tasks per participant: **10 manual, 10 with ALAMATIN**.
* **No address appears in both conditions for the same participant.** A second
  exposure would measure memory rather than the tool.
* **Condition order alternates across participants** — P01 starts manual, P02
  starts with ALAMATIN, and so on — so a learning or fatigue effect cannot be
  read as a tool effect.
* No address is shared between participants either, so one facilitator's
  phrasing of a tricky address cannot leak between sessions.

All four properties are asserted by tests in `tests/test_user_study_tasks.py`,
and the assignment is reproducible from its seed.

## Ground truth

Each task carries its answer, taken from the source dataset's gold labels rather
than a facilitator's judgement: the correct components, the injected noise
categories, and the subset of those categories a reviewer is expected to notice.

Cosmetic noise — casing, separators, abbreviation style — is **excluded** from
the scored set. A participant who ignores `jl.` versus `Jalan` has not made an
error, and scoring it as one would inflate the tool's apparent advantage, since
normalization handles exactly that class.

Scored defects: `typo`, `missing_provinsi`, `missing_kodepos`, `missing_rt_rw`,
`missing_city`, `prefix_junk`, `fused_admin`, `fused_token`, `bare_location`,
`district_only`, `other_surface_form`.

## Task source

The generator defaults to the public synthetic split so it is runnable and
testable anywhere. **The study itself should use the ALM-012 human-noised
benchmark** in the custodian's environment: those are real public-facility
addresses with human-introduced noise, which is far better ecological validity
than generated text.

Generated task sheets contain address text and therefore inherit the source
dataset's restrictions. Output goes to a gitignored directory; only the
generator, this protocol, and the recording schema are published.

## Procedure per session

1. Explain the purpose, that participation is voluntary, and what is recorded.
   Ask explicitly whether comments may be quoted, and record the answer before
   any comment is taken.
2. Two practice tasks, not scored, to settle the interface.
3. Block one: 10 tasks in the assigned condition. For each, record the time from
   the address appearing to a decision, the defects the participant names, any
   issue they raise that is not in the ground truth, and their final decision of
   proceed, needs confirmation, or reject.
4. Short break.
5. Block two: the other condition, same recording.
6. Three usability items, each 1–5: the tool was easy to use; I understood why
   it flagged an address; I would use this before printing a label.
7. Open comments. Record verbatim **only** if permission was given.
8. Record any deviation from this protocol, however small.

In the ALAMATIN condition, also record which suggestions were accepted and which
were rejected.

Note for the facilitator: on this release candidate the pipeline emits **no
correction suggestions** — see `docs/evaluation-results.md`. The
`corrections_accepted` field will therefore be empty unless the build changes,
and that is a property of the system, not a recording failure.

## What is recorded, and what is not

Per task: participant id, task id, condition, block order, seconds to decision,
defects found, defects missed (derived, never asked), false defects, corrections
accepted and rejected, final decision, whether the decision matches ground
truth.

Per session: participant id, a free-text role description with no employer name,
three usability scores, comments, the quote-permission flag, and protocol
deviations.

The schema has **no** field for a name, contact detail, employer, age, or
gender. A test asserts none of those keys exists, so an identifying field cannot
be added without the suite failing.

Raw session records stay in the custodian's restricted location. Only
aggregates, and quotes whose permission flag is true, are published. Comments
are reviewed for identifying detail before any use.

## Reporting rules

* The participant count and task count are reported with every figure.
* Any protocol deviation is reported, including ones that make the tool look
  better.
* With 3–5 participants no significance test is appropriate. Report medians and
  the spread, and say plainly that the sample cannot support an inferential
  claim.
* No claim about downstream delivery outcomes, under any framing.

## To run it

```bash
python scripts/build_user_study_tasks.py --participants 4 --seed <seed> --write
```

Writes `task-sheets.json` and `recording-schema.json` to the gitignored output
directory. Record the seed: it is what makes the assignment reproducible.

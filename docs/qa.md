# QA, automated tests, and privacy checks (ALM-032)

Three commands, all run by CI on every push and pull request:

```bash
python scripts/check_repository.py     # tracked-file and repository policy
python -m unittest discover -s tests   # the full suite
python scripts/qa_privacy_scan.py      # secrets and raw PII in tracked files
python scripts/qa_report.py            # critical-path coverage and skip inventory
```

`qa_report.py` exits non-zero on any failure, error, or privacy finding, so a
green build means all four passed.

## Why there is no coverage percentage

Line coverage can be raised by executing code without asserting anything about
it, which makes the number a poor signal and a tempting target. `qa_report.py`
instead maps each critical path to the test modules that assert its behaviour,
and reports any path with no tests as an explicit gap.

Current state: every critical path is covered except the Maps URL builder, which
does not exist because ALM-030 was not shipped. That is recorded in the report
rather than left looking like an oversight.

| Critical path | Asserted by |
|---|---|
| PII redaction | `test_pii` |
| Token alignment | `test_token_alignment` |
| Component extraction | `test_regex_baseline`, `test_tokenizer` |
| Normalization and provenance | `test_address_normalizer` |
| Administrative validation | `test_administrative_validator`, `test_reference_hierarchy` |
| Quality gate and reason codes | `test_quality_gate` |
| Output contract schema | `test_output_contract` |
| HTTP transport and error contract | `test_api` |
| End-to-end pipeline | `test_pipeline` |
| Served application | `test_service` |
| Consent-gated geocoding | `test_geocoding` |
| Product scope contract | `test_product_scope` |
| Secret and raw-PII scan | `test_qa_privacy_scan` |
| Maps URL builder | not shipped (ALM-030) |

## Secret and raw-PII scan

`scripts/qa_privacy_scan.py` walks the files git tracks, so untracked scratch
work and ignored build output are out of scope by construction. It reports the
file, line, and rule — **never the matched text**, because printing it would
copy the very value the scan exists to keep out of logs and CI output.

Rules cover private-key blocks, AWS/Google/GitHub/Slack key shapes, credentials
assigned to long literals, and raw Indonesian mobile numbers.

Exemptions live in an `ALLOWLIST` keyed by `(path, rule)` and **each one states
its reason**, so an exemption is a recorded decision rather than a silent hole.
A test asserts every entry has a reason and names a rule that actually exists.

The scanner has its own tests, including false-positive cases: postal codes,
village codes, `RT 03 RW 04`, empty credential assignments, and references to
environment variables must not be flagged. A scanner that cries wolf gets
ignored, which is worse than no scanner.

## Skipped tests are listed, never hidden

25 tests skip in the public repository. Every one is an evidence gate whose
required governed input or recorded baseline is not redistributed.
`qa_report.py` prints each reason with a count.

| Count | Reason |
|---|---|
| 1 | recorded synthetic-dev baseline is not present |
| 9 | `real_dev` split is governed data; see `data/sources.md` |
| 12 | governed dataset not present in this repository; see `data/sources.md` |
| 2 | governed `real_dev` split not present; see `data/sources.md` |
| 1 | restricted `section-1/2/3` review artifacts are not redistributed |

The custodian-side validation suite runs with **zero skips**, which confirms
that these guards are conditional rather than a permanent disable.

## Robustness

`ServiceRobustnessTest` drives the real ASGI app with hostile and degenerate
input: empty, whitespace-only, punctuation-only, digits-only, emoji, NUL and
control characters, repeated newlines, right-to-left overrides, a 20,000
character address, an oversized body, a wrong `document_type`, and malformed
request ids. None crash; each is answered or refused with the frozen error
contract.

## Findings from this pass

Two defects were found while writing these checks, and both are fixed:

**Whitespace-only input returned `503 PIPELINE_FAILED` with `retryable: true`.**
That reported a client input problem as a retryable server failure, so a client
would retry forever over its own unusable input. It was also inconsistent:
punctuation-only text returned `200 PERLU_KONFIRMASI`. Whitespace-only now
extracts no components and gets the same answer.

**`tests/test_evaluation_metrics.py` imported through `src.`,** which only
resolves when the suite is run from the repository root. Under any other
discovery root the module failed to import and its 9 tests silently did not run.
The import is now resolved from the test file's own location.

## Known limitations

- Recipient-name redaction is marker-based; a bare name with no `Penerima:`,
  `a.n.`, or `atas nama` marker is not redacted. Conservative by design from
  ALM-021, and documented in `docs/integration.md`.
- The scan is pattern-based. It catches the shapes listed above and will not
  catch a credential that looks like ordinary prose.
- No flaky test is known. If one appears it belongs in this section with its
  symptom, not in a retry loop.

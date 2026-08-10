# NER schema review record

- Review date: 2026-08-10
- Schema version: `1.0.0`
- Review method: joint team review
- Reviewer group: ALAMATIN team
- Project-owner confirmation: `yongkytristan`
- Material reviewed: 20 examples in `tests/fixtures/ner_gold_examples.json`
- Result: accepted
- Unresolved blocking disagreement: none reported

## Review scope

The team accepted:

- the 10 entity types and their definitions;
- the 21-label BIO order and ID mapping;
- boundary and punctuation rules;
- separation of recipient name and phone into the PII module;
- treatment of abbreviations and observed typos;
- escalation of insufficiently supported ambiguity to adjudication;
- handoff of administrative conflicts to the validator.

This record reflects the team's explicit decision to use joint review rather
than require two independent annotators for schema version `1.0.0`.

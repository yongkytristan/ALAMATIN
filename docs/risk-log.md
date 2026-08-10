# Risk log

| ID | Risk | Likelihood | Impact | Mitigation | Owner role | Status |
|---|---|---|---|---|---|---|
| R-001 | Secret or API key committed | Medium | Critical | Ignore local env files, use a secret store, run repository checks | Product & Delivery | Open |
| R-002 | Raw personal addresses enter Git history | Medium | Critical | Use public/synthetic fixtures, ignore raw/private data, require PII review | Data & Research | Open |
| R-003 | Large model/data artifacts make clones unreliable | Medium | High | Ignore checkpoints and generated data; document reproducible retrieval | ML & Evaluation | Open |
| R-004 | Unlicensed source is redistributed | Medium | High | Record provenance, terms, redistribution decision, and source version | Data & Research | Open |
| R-005 | Unreviewed changes break the demo | Medium | High | Small PRs, one reviewer, required CI, clean-clone verification | Whole Team | Open |

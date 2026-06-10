## Summary



## Closes

<!-- Use "Closes #N" — checkboxes in the issue do NOT auto-close it -->

## Change type

- [ ] New translation rule / Java construct support
- [ ] Rule-layer skeleton improvement (`translate/skeleton.py`)
- [ ] LLM prompt change
- [ ] Bug fix
- [ ] Refactor (no behaviour change)
- [ ] Docs / ADR
- [ ] CI / tooling

## Material change?

A **material change** is: new/changed translation of a Java construct, pipeline stage
change, LLM model/prompt change, Python output version change, or breaking API change.

- [ ] Not a material change
- [ ] Material change — ADR: <!-- link to docs/decisions/NNNN-*.md -->

## Fixtures

For translation rule changes:
- [ ] Java fixture added/updated in `tests/fixtures/java/`
- [ ] Expected Python fixture added/updated in `tests/fixtures/python/`
- [ ] Test parametrised entry added

## Verification

- [ ] `make ci-local-pr` passed locally
- [ ] No `# type: ignore` added without an explanatory comment
- [ ] No live Anthropic API calls in new tests

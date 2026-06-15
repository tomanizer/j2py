# Harvest → GitHub issue draft (pattern family)

Copy into `gh issue create --body-file` or the [rule-layer-pattern](../ISSUE_TEMPLATE/rule-layer-pattern.md) template.

Automated draft: `make harvest-promote-dry ISSUES=1` or `make harvest-promote-issues` (see [docs/LLM_HARVEST.md](../../docs/LLM_HARVEST.md)).

**Title format:** `Rule layer: <pattern description> (harvest: <signal-name>)`

**Labels:** `enhancement`, `rule-layer`

---

## Pattern family (not a single-file fix)

**Family:** …

**Do not** special-case `<MinimalFixture>.java`. …

## Mechanism

| Layer | Detail |
|-------|--------|
| AST node / construct | |
| Rule-layer diagnostic | |
| Harvest signal(s) | |
| Translator home | |
| Mapping / policy | |

## Harvest evidence

| Source | Role |
|--------|------|
| `tests/fixtures/...` | Minimal fixture |
| `tests/fixtures/corpus/constructs/...` | Regression peer |
| `.corpus/...` | Corpus evidence |

## Acceptance criteria (pattern-level)

- [ ] General rule for all instances of the pattern
- [ ] Parametrised tests (≥2 variants)
- [ ] All evidence-table files improve on re-harvest
- [ ] `make check` green

## Anti-patterns

- Filename checks, one-file LLM diff copy, single xfail fix

## Verify

```bash
make check
make test-targets
make harvest-promote-dry    # or make harvest-run / harvest-gemini slice
grep REPAIR_SIGNAL .j2py/harvest/records.jsonl
```

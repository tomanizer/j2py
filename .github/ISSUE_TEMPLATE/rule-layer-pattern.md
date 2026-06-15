---
name: Rule layer pattern (from harvest)
about: File a pattern-family rule-layer issue — not a single-fixture point fix
title: "Rule layer: "
labels:
  - enhancement
  - rule-layer
assignees: []
---

## Pattern family (not a single-file fix)

**Family:** <!-- e.g. Java assert statements → Python assert; all assert_statement nodes -->

**Do not** special-case one fixture filename. Implement the general visitor/registry rule for the whole pattern class.

## Mechanism

| Layer | Detail |
|-------|--------|
| AST node / construct | <!-- e.g. assert_statement --> |
| Rule-layer diagnostic | <!-- e.g. unsupported statement assert_statement --> |
| Harvest signal(s) | <!-- e.g. unsupported-stmt-removed --> |
| Translator home | <!-- e.g. j2py/translate/statements.py --> |
| Mapping / policy | <!-- general rule, not one file's LLM diff --> |

## Harvest evidence (pattern, not one file)

Run before filing (or use `make harvest-promote-dry` to draft from triage automatically):

```bash
make harvest-prune && make harvest-triage
make harvest-promote-dry ISSUES=1   # optional: automated pattern-family draft
uv run python scripts/harvest/aggregate_llm_harvest.py --top 50
# List all clean sources for this signal (exclude /pytest- temp paths):
grep '"repair_signals".*SIGNAL_NAME' .j2py/harvest/records.jsonl | python3 -c "
import json, sys
for line in sys.stdin:
    r = json.loads(line)
    print(r['source_path'], r.get('repair_signals'))
"
```

| Source | Role |
|--------|------|
| <!-- path/to/MinimalFixture.java --> | **Minimal fixture** (develop the rule here) |
| <!-- path/to/second.java --> | Regression peer |
| <!-- .corpus/... --> | Corpus evidence (extract minimal repro if large) |

## Acceptance criteria (pattern-level)

- [ ] **General rule:** <!-- describe behavior for all instances of the pattern -->
- [ ] **Minimal fixture** passes without LLM / without harvest signal on re-run
- [ ] **Parametrised tests:** ≥2 variants of the pattern (not only one fixture stem)
- [ ] **Regression peers:** all evidence-table files improve (skeleton bar or LLM skip)
- [ ] Re-harvest: signal count drops for this diagnostic family
- [ ] `make check` green; update `FUTURE_TARGETS` / graduate fixtures if applicable

## Anti-patterns (reject in review)

- `if source_path.endswith("SomeFixture.java")` or fixture-name branching
- Copy-pasting one harvest `diff_excerpt` without a visitor rule
- Fixing only one `FUTURE_TARGETS` xfail while the general diagnostic remains
- String-matching one `__j2py_todo__` literal instead of handling the AST node

## Related issues

- <!-- #NNN — overlapping or prerequisite pattern -->

## Verify

```bash
make check
make test-targets
uv run pytest tests/translate/ -k PATTERN_KEYWORD -v
make harvest-run   # or harvest-gemini slice
grep REPAIR_SIGNAL .j2py/harvest/records.jsonl
```

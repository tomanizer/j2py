---
name: add-translation-rule
description: >-
  Add a deterministic j2py rule-layer translation for a Java construct pattern family:
  Java/Python fixture pair, visitor in translate/, parametrised tests, make check.
  Use when implementing rules, fixing unhandled diagnostics or TODO(j2py) placeholders,
  or closing a FUTURE_TARGETS xfail. Rule layer only — never use_llm in these tests.
---

# Add a translation rule

Implements **general visitor/registry rules** for an AST node or diagnostic class — not
one-file hacks. Tests use **`translate_skeleton` / rule layer only** (`use_llm=False`).

Read first: [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-a-translation-rule),
[AGENTS.md](../../../AGENTS.md).

## When to use

| Situation | Skill |
|-----------|--------|
| Implement a construct now | This skill |
| Defer a gap to backlog | Add `FUTURE_TARGETS` — see [graduate-translation-target § Defer](../graduate-translation-target/SKILL.md#defer-a-gap-not-ready-to-implement) |
| Rule done, xfail passes | [graduate-translation-target](../graduate-translation-target/SKILL.md) |
| Found gap via corpus/harvest | [corpus-gap-triage](../corpus-gap-triage/SKILL.md) / [harvest-promote](../harvest-promote/SKILL.md) first |

## Pick the home module

| Construct area | Start here |
|----------------|------------|
| Statements (`if`, `for`, `try`, `assert`, …) | `j2py/translate/statements.py` |
| Expressions (calls, ops, lambdas, streams, …) | `j2py/translate/expr_*.py` (facade: `expressions.py`) |
| Classes (methods, fields, enums, nested, …) | `j2py/translate/class_*.py` (facade: `classes.py`) |
| Method overloading / dispatch tiers | `j2py/translate/overloads.py` ([ADR 0009](../../../docs/decisions/0009-two-tier-overload-translation.md)) |
| Types, imports, literals | `j2py/translate/rules/` |
| Name binding / resolution | `j2py/translate/name_resolution.py` |

`skeleton.py` orchestrates; add rules in the split modules above — not in removed
selector/transform prototypes ([ADR 0003](../../../docs/decisions/0003-layered-translation-pipeline.md)).

## Workflow

### 1. Reproduce the gap

```bash
uv run python -c "
from pathlib import Path
from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
p = Path('tests/fixtures/java/Feature.java')
r = translate_skeleton_with_diagnostics(parse_file(p), extract_symbols(parse_file(p)), ConfigLoader().add_defaults().build())
print('coverage', r.coverage)
print('unhandled', r.diagnostics.unhandled)
print(r.source[:800])
"
```

Note the **tree-sitter node type** and `diagnostics.unhandled` reason — fix the class,
not one file path.

### 2. Minimal fixture pair

```text
tests/fixtures/java/<Feature>.java           # general pattern (preferred)
tests/fixtures/python/<Feature>.py           # exact expected skeleton output
tests/fixtures/java/targets/<Feature>.java   # optional: roadmap-only before graduation
```

- Python fixture = **rule-layer output** (camelCase → snake_case, structural correspondence)
- Add ≥2 variants via parametrised fixtures or focused tests when the pattern has branches
- Generate expected Python by implementing the rule, then `ruff format` the output; hand-audit

### 3. Register tests

**Primary gate** — add to the parametrised list in
[tests/translate/skeleton/test_fixtures.py](../../../tests/translate/skeleton/test_fixtures.py):

```python
@pytest.mark.parametrize(
    ("fixture_name", "expected_coverage"),
    [
        ("Feature", 1.0),           # full rule-layer coverage expected
        # ("PartialFeature", None),  # only when deliberately partial
    ],
)
def test_translate_fixture_with_rule_layer(...):
    ...
```

**Focused tests** — `tests/translate/skeleton/test_*.py`, `tests/translate/test_*.py` for
edge cases that do not need full-file equality.

**Never** call live LLM APIs in these tests (`make check` / CI must stay offline).

### 4. Implement the rule

- Match the **AST node** or diagnostic for all instances
- Emit `diagnostics` when Java semantics cannot be preserved exactly
- Keep helpers stateless; match module style
- `confidence` / `coverage` must stay honest (semantic warnings ≠ coverage loss)

### 5. Verify

```bash
uv run pytest tests/translate/skeleton/test_fixtures.py -k Feature -v
make check
make test-equivalence                    # if touching tested equivalence methods
make test-targets                      # if a FUTURE_TARGETS xfail should now pass
make ci-local-pr                         # before push — same as CI gate
```

Corpus (needs clones; worktrees: `export J2PY_CORPUS_ROOT=/path/to/main/j2py`):

```bash
make corpus-<relevant>-dense-check
```

### 6. Material changes

Non-obvious translation policy (new idiom, overload tier, JDK stub policy):

- ADR in `docs/decisions/`
- `CHANGELOG.md` under `## Unreleased` when user-visible
- PR body links the ADR

## Anti-patterns

- `if source_path.endswith("SomeFixture.java")` or fixture-name branching
- Copy-pasting one harvest `diff_excerpt` without a visitor rule
- Fixing one xfail while the general diagnostic remains
- `# type: ignore` without comment; faking `coverage == 1.0`
- Live LLM in unit tests

## After the rule lands

[graduate-translation-target](../graduate-translation-target/SKILL.md) if the change
closes a deferred target or harvest-promoted issue.

## Related docs

- [docs/TRANSLATION_TARGETS.md](../../../docs/TRANSLATION_TARGETS.md)
- [docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md)
- [docs/EQUIVALENCE_TESTING.md](../../../docs/EQUIVALENCE_TESTING.md)

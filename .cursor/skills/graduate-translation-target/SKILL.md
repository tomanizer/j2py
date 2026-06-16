---
name: graduate-translation-target
description: >-
  Graduate or defer j2py FUTURE_TARGETS xfails: add strict xfail contracts when deferring,
  remove and move to make check when implementing. Use for TranslationTarget registry,
  GRADUATED_LLM_FIXTURES, TRANSLATION_TARGETS.md updates, and strict xfail graduation.
---

# Graduate (or defer) a translation target

Manages the **`FUTURE_TARGETS`** registry in
[tests/targets/test_translation_targets.py](../../../tests/targets/test_translation_targets.py).

Read first: [docs/TRANSLATION_TARGETS.md](../../../docs/TRANSLATION_TARGETS.md).

## When to use

| Situation | Action |
|-----------|--------|
| Defer a gap you will not fix now | [Defer](#defer-a-gap-not-ready-to-implement) |
| Strict xfail **failed** because target passes | [Graduate](#graduate-after-rule-implementation) |
| User asks to graduate / close target issue | Graduate |

### Strict xfail behavior

Future targets use `pytest.mark.xfail(..., strict=True)`. When the rule **starts passing**,
pytest reports **XPASS → test failure**. That is the signal to graduate — not success while
the entry remains in `FUTURE_TARGETS`.

When `FUTURE_TARGETS` is empty, `make test-targets` collects **0 tests** (expected). Graduated
fixtures still run inside `make check`.

## Lanes

| Lane | Fixture root | Graduation mechanism |
|------|--------------|----------------------|
| Roadmap | `tests/fixtures/java/targets/` | Remove from `FUTURE_TARGETS` → auto in `GRADUATED_TARGET_FIXTURES` |
| Corpus construct | `tests/fixtures/corpus/constructs/` | Remove from `FUTURE_TARGETS` → auto in `CORPUS_GRADUATED_FIXTURES` |
| Harvest probe | `tests/fixtures/llm/` | Remove from `FUTURE_TARGETS` + add to `GRADUATED_LLM_FIXTURES` |

While a construct stays in `FUTURE_TARGETS`, it is **excluded** from graduated parametrised
lists (glob minus future set).

---

## Defer a gap (not ready to implement)

Use before leaving backlog — pair with [corpus-gap-triage](../corpus-gap-triage/SKILL.md) or
[harvest-promote](../harvest-promote/SKILL.md) for issue filing.

1. Add minimal Java fixture (paths above)
2. Append to `FUTURE_TARGETS`:

```python
TranslationTarget(
    fixture="ExampleGap.java",
    fixture_root=TARGET_FIXTURES,          # or LLM_FIXTURES / CORPUS_CONSTRUCT_FIXTURES
    tracking="issue-NNN",
    reason="Short description of missing rule-layer capability",
    expected_fragments=("expected_python_snippet(",),
    forbidden_fragments=(
        "TODO(j2py): unsupported",
        "__j2py_todo__",
    ),
)
```

3. Update [docs/TRANSLATION_TARGETS.md](../../../docs/TRANSLATION_TARGETS.md) — replace
   empty-backlog sentence with the new row when backlog is non-empty
4. File a **pattern-family** issue ([harvest-promote](../harvest-promote/SKILL.md) or template)
5. Verify:

```bash
make test-targets
uv run pytest tests/targets/test_translation_targets.py::test_future_targets_have_actionable_contract_metadata -v
```

---

## Graduate (after rule implementation)

Implement the rule first: [add-translation-rule](../add-translation-rule/SKILL.md).

### 1. Confirm contract

```bash
uv run pytest tests/targets/test_translation_targets.py -k <fixture-stem> -v
# strict xfail should XPASS-fail until you remove the entry
make check
```

Bar: `coverage == 1.0`, valid AST, no unhandled diagnostics, no forbidden fragments.

### 2. Update registry

In `tests/targets/test_translation_targets.py`:

- **Remove** the `TranslationTarget(...)` from `FUTURE_TARGETS`
- **LLM fixtures only:** append filename to `GRADUATED_LLM_FIXTURES`
- Target/construct fixtures need no tuple edit (auto-graduate)

### 3. Normal fixture pair (recommended)

```text
tests/fixtures/java/<Feature>.java
tests/fixtures/python/<Feature>.py
```

Add to `test_translate_fixture_with_rule_layer` parametrize list when not redundant.

### 4. Docs and changelog

- [docs/TRANSLATION_TARGETS.md](../../../docs/TRANSLATION_TARGETS.md) — graduated table;
  restore empty-backlog wording if `FUTURE_TARGETS == ()`
- `CHANGELOG.md` under `## Unreleased`
- PR: `Closes #NNN`
- Optional: mark harvest record `"status": "resolved"` + `make harvest-prune`

### 5. Verify

```bash
make check
make test-targets
make test-equivalence
make corpus-<relevant>-dense-check
make ci-local-pr
```

## Empty `FUTURE_TARGETS` checklist

- [ ] `TRANSLATION_TARGETS.md` contains “intentional while no deferred concrete construct gap”
- [ ] Graduated fixtures documented in table
- [ ] `GRADUATED_LLM_FIXTURES` lists harvest probes (e.g. `MultiDimArray.java`)

Enforced by `test_future_targets_empty_state_is_explicitly_documented`.

## Anti-patterns

- Leaving xfail after rule works (strict XPASS breaks CI)
- Graduating one fixture without a general rule
- Deleting Java fixtures
- Omitting doc update when empty-state test applies

## Related skills

- [add-translation-rule](../add-translation-rule/SKILL.md)
- [corpus-gap-triage](../corpus-gap-triage/SKILL.md)
- [harvest-promote](../harvest-promote/SKILL.md)

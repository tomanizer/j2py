## Summary

Track the behavior-neutral completion of the `j2py/translate/expressions.py` split into
focused `expr_*.py` modules. No translation semantics change — structure only.

Parent issue: #232

## Motivation

`expressions.py` is still ~1,026 LOC even though phase 1 extracted `expr_ops.py`,
`expr_streams.py`, `expr_lambdas.py`, `expr_objects.py`, and `expr_types.py`. The facade
still owns call/access/cast logic and ~140 lines of bottom-of-file wrapper re-exports.
Mirror the completed `classes.py` → `class_*` pattern, not the `statements.py` wrapper
pattern.

## Target layout

| Module | Role | ~LOC |
|--------|------|------|
| `expressions.py` | Public API + `_translate_expression` router only | <250 |
| `expr_access.py` | identifier, field/array, cast, `instanceof` | ~200 |
| `expr_calls.py` | method/static calls, `String.format`, collection shims | ~350 |
| `expr_ops.py` | unary/binary/ternary/switch/assignment (+ moved inline blocks) | ~750 |
| `expr_streams.py` | stream pipelines (exists) | ~600 |
| `expr_lambdas.py` | lambdas, method references (exists) | ~240 |
| `expr_objects.py` | `new`, anonymous classes (exists) | ~260 |
| `expr_types.py` | inference + shared type helpers (expand) | ~220 |

## Child PRs (merge in order)

- [ ] **PR 0** — Remove bottom wrapper layer; inline `expr_*` calls from `_translate_expression`
- [ ] **PR 1** — Extract `expr_access.py`
- [ ] **PR 2** — Extract `expr_calls.py`
- [ ] **PR 3** — Move assignment + binary blocks from dispatcher → `expr_ops.py`
- [ ] **PR 4** — Move `_java_type_of_value` / integral helpers → `expr_types.py`
- [ ] **PR 5** — Facade cleanup + `ARCHITECTURE.md` + `AGENTS.md` module map
- [ ] **PR 6 (optional)** — Extract router to `expr_dispatch.py` if facade still >300 LOC

## Anti-duplication rules

1. **One router** — `_translate_expression` is the only dispatch table.
2. **No wrapper functions** — no `def foo(): return impl()` at file bottom; call handlers
   inline in the router (like `classes.py` does for enums/interfaces).
3. **Move once** — cut from facade, paste into `expr_*`, update one `if node.type` branch;
   no stubs left in `expressions.py`.
4. **No re-exports** — do not export `expr_*` symbols from `expressions.py` except
   `translate_expression` and `infer_expression_py_type`.
5. **Cycle rule** — `expressions.py` never top-level-imports `expr_*`; submodules may
   `from j2py.translate.expressions import translate_expression` for recursion.
6. **Shared helpers live once** — e.g. `_java_type_of_value` → `expr_types.py`;
   precedence helpers → `expr_ops.py`; argument parsing → `expr_calls.py`.

## Router pattern (target)

```python
if node.type == "field_access":
    from j2py.translate.expr_access import translate_field_access
    return translate_field_access(node, ctx)
if node.type == "method_invocation":
    from j2py.translate.expr_calls import translate_method_invocation
    return translate_method_invocation(node, ctx)
if node.type == "binary_expression":
    from j2py.translate.expr_ops import translate_binary_expression
    return translate_binary_expression(node, ctx)
```

## Rules for every child PR

1. **Behavior-neutral** — output Python must be byte-identical for all existing tests.
2. **Public API unchanged** — external imports stay
   `from j2py.translate.expressions import translate_expression, infer_expression_py_type`.
3. **Lazy imports** at module boundaries that would create cycles (`expressions` → `expr_*`
   only inside router branches; `expr_*` → `translate_expression` for recursion).
4. Run `make check` before opening PR.
5. No new ADR (internal refactor only).

## What not to do

- Re-export every `expr_*` symbol from `expressions.py`
- Split into many micro-modules (`expr_cast.py`, `expr_binary.py`, …)
- Change callers (`statements.py`, `class_fields.py`, …) to import `expr_*` directly
- Combine PRs 1–3 in one diff

## Done when

All child work merged; `expressions.py` is a thin facade (<300 LOC); zero bottom wrappers;
`docs/ARCHITECTURE.md` and `AGENTS.md` list the full `expr_*` module map (parity with
`class_*`).

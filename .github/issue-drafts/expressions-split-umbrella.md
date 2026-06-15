## Summary

Track the behavior-neutral completion of the `j2py/translate/expressions.py` split into
focused `expr_*.py` modules. No translation semantics change — structure only.

## Motivation

`expressions.py` remained over 1,000 lines after the first extraction pass, with access,
call, cast, assignment, binary, and wrapper re-export logic still mixed into the facade.
The class split established the desired pattern: keep the public module as a thin router
and move implementation detail into focused helper modules.

## Child issues (merge in order)

- [x] #236 — PR 0: Remove bottom wrapper layer; inline `expr_*` calls from router
- [x] #237 — PR 1: Extract `expr_access.py`
- [x] #238 — PR 2: Extract `expr_calls.py`
- [x] #239 — PR 3: Move assignment + binary blocks to `expr_ops.py`
- [x] #240 — PR 4: Move shared Java type helpers to `expr_types.py`
- [x] #241 — PR 5: Facade cleanup + `ARCHITECTURE.md` + `AGENTS.md`
- [x] #242 — PR 6 (optional): Not needed; `expressions.py` is already below the 300
  LOC target after PR 5

## Rules for every child PR

1. **Behavior-neutral** — output Python must be byte-identical for all existing tests.
2. **Public API unchanged** — external imports stay
   `from j2py.translate.expressions import translate_expression, infer_expression_py_type`.
3. **Lazy imports** at module boundaries that would create cycles.
4. Run `make check` before opening PR.
5. No new ADR (internal refactor only).

## Done when

All required child work is merged; `expressions.py` is a thin facade under 300 LOC; no
bottom wrapper functions remain; `docs/ARCHITECTURE.md` and agent guidance list the
focused `expr_*` modules.

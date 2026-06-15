## Summary

Track the behavior-neutral split of `j2py/translate/classes.py` into focused `class_*.py` modules. No translation semantics change — structure only.

## Motivation

`classes.py` was ~1,850 lines and mixed declaration dispatch, enum/interface/annotation emitters, member indexing, and method emission. Prior extractions (`class_fields.py`, `class_model.py`, `overloads.py`) established the pattern; this completes it.

## Child issues (merge in order)

- [x] Extract `class_enums.py` — implemented in single refactor PR
- [x] Extract `class_methods.py` (+ repoint `overloads.py`, `expr_objects.py`)
- [x] Extract `class_annotations.py`
- [x] Extract `class_members.py`
- [x] Extract `class_interfaces.py` + `class_nested.py`
- [x] Facade cleanup + `ARCHITECTURE.md`

## Rules for every child PR

1. **Behavior-neutral** — output Python must be byte-identical for all existing tests.
2. **Public API unchanged** — external imports stay `from j2py.translate.classes import translate_class, top_level_classes, collect_file_class_static_methods, FieldInfo, ParameterInfo, field_infos_from_declaration`.
3. **Lazy imports** at module boundaries that would create cycles.
4. Run `make check` before opening PR.
5. No new ADR (internal refactor only).

## Done when

All child work merged; `classes.py` is a thin facade; `docs/ARCHITECTURE.md` lists new modules.

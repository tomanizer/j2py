# ADR 0018 — Cross-file class hierarchy translation

**Date:** 2026-06-16
**Status:** Accepted

## Context

The commons-lang `tuple` case study (issue #311, [docs/CASE_STUDY.md](../CASE_STUDY.md))
translated a real multi-file inheritance hierarchy and exposed two rule-layer defects that
node-coverage scoreboards could not see, because they only manifest when the output is
actually imported and executed.

1. **Generic cross-file superclass dropped.** `class ImmutablePair<L, R> extends
   Pair<L, R>` translated to `class ImmutablePair:` — no base class. The `extends` clause
   wraps the type name in a tree-sitter `generic_type` node, and the superclass extractor
   only looked for a bare `type_identifier`/`scoped_type_identifier`, so the generic
   supertype was silently lost. Every inherited method disappeared.

2. **Class-body forward self-reference.** `private static final ImmutablePair NULL = new
   ImmutablePair<>(null, null)` became a class-body statement
   `NULL = ImmutablePair(None, None)` that executes during class creation, before the
   class name is bound, raising `NameError` at import.

## Decision

**Generic superclasses are extracted and bound through the name resolver.** The superclass
extractor descends into a `generic_type` wrapper to recover the type name, then resolves
the Python base name and its import through the existing deterministic
`NameResolver` (ADR 0016): an explicit import / import-map binding wins, then a
same-package sibling import (`from <package>.<Class> import <Class>`), with a
`translate_class_name` fallback that always keeps a class name. A superclass declared in
the same compilation unit (same Python module) is detected first and needs no import.

**Self-referential static fields are deferred to module scope.** A `static` field whose
translated initializer references the class being defined is not emitted in the class body.
Instead it is recorded on `TranslationDiagnostics.deferred_module_lines` and emitted as a
module-level assignment after the class block — `ImmutablePair.NULL = ImmutablePair(None,
None)` — matching Java's "statics initialize after the class is loaded" semantics.

## Consequences

+ Real cross-file inheritance hierarchies translate with their base classes and inherited
  behaviour intact, and self-referential singletons (`NULL`, `EMPTY`, `INSTANCE`) no
  longer crash at import.
+ Both behaviours reuse the existing name-resolution and diagnostics machinery rather than
  introducing a parallel mechanism.
- Deferral qualifies the target with the immediate class name only, so a self-referential
  static field on a *nested* class is not yet handled (the common top-level case is).
- Fixing cross-file inheritance exposes a downstream limitation: a base class that
  delegates to a concrete subclass (`Pair.of` → `ImmutablePair.of`) now forms a circular
  import under eager Python `from X import Y`. Breaking that cycle (function-local sibling
  imports) is tracked separately and will warrant its own ADR.

## References

- [Issue #311](https://github.com/tomanizer/j2py/issues/311) and [docs/CASE_STUDY.md](../CASE_STUDY.md)
- [ADR 0016](0016-class-reference-expression-imports.md) — name resolver / type bindings
- [ADR 0003](0003-layered-translation-pipeline.md)

# ADR 0021 — Same-package sibling type references in method bodies use function-local imports

**Status:** Accepted  
**Date:** 2026-06-16  
**Issue:** #325

## Context

After [ADR 0018](0018-cross-file-class-hierarchies.md) enabled cross-file inheritance
(e.g. `class ImmutablePair(Pair):`), a circular import emerged in the translated tuple
package:

- `ImmutablePair.py` imports `Pair` at module level (superclass — must be eager).
- `Pair.py` imports `ImmutablePair` at module level (factory delegation —
  `Pair.of()` → `ImmutablePair.of()`).

Java tolerates this via lazy class loading; eager Python `from X import Y` at module
level raises `ImportError: cannot import name 'Pair' from partially initialized module`.

The base⇄derived factory pattern is common (Pair/ImmutablePair, AbstractX/X) so a
general rule is needed, not a one-off workaround.

## Decision

**Same-package sibling type references that appear inside method bodies are emitted as
function-local imports (`from pkg.Sibling import Sibling` inside the `def` body) rather
than at module level.**

The key insight: the superclass reference (`class ImmutablePair(Pair):`) is a class
*definition* dependency and must remain an eager module-level import.  A factory
delegation (`return ImmutablePair.of(...)` in a method body) is a *call-time* dependency
and can be deferred.

### Scope

Only **`"package_type"`** references are affected — types inferred from the same Java
package that have no explicit `import` in the Java source.  This class excludes:

- Types with explicit Java imports (`"imported_type"`): unchanged (were never
  auto-imported via constructor expressions anyway).
- Types declared in the same compilation unit (`"compilation_unit_type"`): unchanged —
  they share the Python module and need no import at all.
- Superclass references: handled by `_superclass_binding` in `class_members.py`, which
  always emits at module level (unaffected).
- Qualified inner-class names (`Outer.Inner`): skipped — they cannot form a valid Python
  `from … import` statement.

### Affected call sites

Two call sites in the expression layer now route package_type imports to body-local
when `ctx.in_method_body` is `True`:

1. **`_translate_identifier`** (`expr_access.py`) — handles standalone identifier
   expressions such as `ImmutablePair.of(…)` where `ImmutablePair` appears as a
   receiver.
2. **`_request_constructor_import`** (`expr_objects.py`) — handles `new SiblingClass()`
   object-creation expressions, which previously bypassed the import system entirely.

`TranslationContext` gains two new fields managed by `translate_method`
(`class_methods.py`):

- `in_method_body: bool` — set `True` around `translate_body`, reset after.
- `body_local_imports: set[str]` — collected during body translation, flushed as
  indented `from … import …` lines at the start of the method body.

## Consequences

**Positive:**
- Breaks base↔derived circular import cycles without any cycle-detection pass.
- Translated packages can be imported as real Python modules in dependency order.
- Consistent with Python conventions: circular-import-breaking local imports are a
  well-established Python pattern.

**Negative / Trade-offs:**
- Function-local imports are slightly slower than module-level imports (the interpreter
  checks `sys.modules` on every call instead of once at load time).  For typical
  factory patterns this overhead is negligible.
- Same-package sibling calls from method bodies look slightly different from explicitly-
  imported calls (local vs. module-level `from`).  Reviewers should be aware that local
  imports in translated output indicate cross-file same-package references, not unusual
  control flow.
- Only method/constructor bodies are scoped (`in_method_body`).  Field initializers at
  class-body level still use module-level imports.  A class-body `new SiblingClass()`
  field default is rare and still causes a circular import — handle if encountered.

# ADR 0010 — synchronized(this) translation

**Date:** 2026-06-11
**Status:** Accepted

## Context

Java `synchronized (this) { ... }` acquires the monitor of the current instance. The
rule layer previously emitted `with self:`, which is not a lock and does not preserve
Java semantics or match the LLM prompt guidance.

Line-level structural correspondence requires a reviewable Python equivalent that:
- uses a real lock object,
- initializes that lock once per instance,
- keeps the synchronized block as a `with` statement.

## Decision

1. **`synchronized (this)` in instance methods** translates to `with self._j2py_lock:`.
2. When a class uses `synchronized (this)`, emit `self._j2py_lock = threading.Lock()`:
   - in a synthetic `__init__` when Java has no explicit constructor, or
   - at the start of each emitted constructor body (including merged overload constructors).
3. **`synchronized (expr)` where `expr` is not `this`** translates to
   `with _j2py_monitor(<expr>):` with a semantic review warning. See the Amendment
   below — the original `with <expr>:` form was unsound (plain objects are not context
   managers and raise `AttributeError` at runtime).
4. **`synchronized (this)` in static methods** is invalid Java usage; emit a
   `# TODO(j2py)` stub and mark the construct unhandled.

The skeleton layer adds `import threading` when `_j2py_lock` appears in generated output.

## Consequences

- Graduated target `StaticAndSynchronized.java` now expects `_j2py_lock` initialization
  and `with self._j2py_lock`.
- Classes without constructors gain a synthetic `__init__` solely to hold the lock when
  needed — this is intentional and reviewable.
- Non-`this` monitors remain approximate and flagged for human review.

## Amendment (2026-06-13, #137) — non-`this` monitors via `_j2py_monitor`

The original decision item 3 (`synchronized (expr)` → `with <expr>:`) was unsound: a
translated Python object has no `__enter__`/`__exit__`, so the `with` statement raised
`AttributeError` at runtime — the block never ran. Decision item 3 is superseded as
follows.

**Decision.** `synchronized (expr)` (non-`this`) translates to
`with _j2py_monitor(<expr>):`, where `_j2py_monitor` is a context manager in the
vendored runtime (`j2py_runtime.py`). The skeleton layer emits
`from j2py_runtime import _j2py_monitor` when the call appears in output. The semantic
review warning is retained.

**Monitor semantics.** Java intrinsic monitors are keyed by *object identity*, not by
`equals`/`hashCode`, and are *reentrant*. `_j2py_monitor` therefore:

- binds one `threading.RLock` per object, keyed on `id(obj)` (not via a
  `WeakKeyDictionary`, which would route through `__eq__`/`__hash__` and wrongly merge
  locks for value-like translated objects, or drop them for unhashable ones);
- uses `RLock` so a thread may re-enter the same monitor — matching Java;
- evicts an object's entry via `weakref.finalize` when the object is garbage-collected,
  so its `id()` cannot be recycled onto an unrelated object while a lock is registered;
- for objects that cannot be weakly referenced (`object()`, `list`, `dict`, `str`,
  `int`, …) retains a strong reference for the life of the process so their `id()`
  stays stable. This is a deliberate, bounded leak: such dedicated lock objects are
  typically few and long-lived.

**Known limitations (flagged by the review warning).** Identity is preserved within a
single translated program run, but cross-run identity and Java's interning of boxed
primitives / string literals are not modelled. Reviewers must confirm the Python lock
object's identity matches the intended Java monitor.

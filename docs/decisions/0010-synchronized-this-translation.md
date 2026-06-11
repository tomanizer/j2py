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
3. **`synchronized (expr)` where `expr` is not `this`** continues to translate as
   `with <expr>:` with a semantic review warning — Java monitors are not always Python
   context managers.
4. **`synchronized (this)` in static methods** is invalid Java usage; emit a
   `# TODO(j2py)` stub and mark the construct unhandled.

The skeleton layer adds `import threading` when `_j2py_lock` appears in generated output.

## Consequences

- Graduated target `StaticAndSynchronized.java` now expects `_j2py_lock` initialization
  and `with self._j2py_lock`.
- Classes without constructors gain a synthetic `__init__` solely to hold the lock when
  needed — this is intentional and reviewable.
- Non-`this` monitors remain approximate and flagged for human review.

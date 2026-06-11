# ADR 0006 — Overload translation policy

**Date:** 2026-06-10
**Status:** Accepted (extended by [ADR 0009](0009-two-tier-overload-translation.md):
chained delegation merges, sentinel defaults, and runtime dispatch for
type-dispatch groups)

## Context

Java allows multiple constructors or methods with the same name as long as their
parameter signatures differ. Python does not support runtime overload dispatch by
signature, but Python type checkers support `typing.overload` stubs followed by one
runtime implementation.

j2py must avoid silently emitting duplicate Python definitions because the later
definition overwrites the earlier one. At the same time, line-level reviewability
requires preserving the original Java signatures where possible.

## Decision

For overloaded constructors and methods, deterministic skeleton translation uses this
policy:

1. Emit `@overload` stubs for each original Java signature.
2. Emit one runtime implementation only when the overload group is mechanically
   mergeable.
3. Merge constructor overloads when delegating constructors contain only `this(...)`
   and forward literals or identifiers to a single implementation constructor. Literal
   forwarding becomes Python default parameter values.
4. Merge method overloads when every overload has the same Python parameter names,
   the same arity, the same static/instance shape, and the same body text. Parameter
   and return annotations become ordered `|` unions.
5. For all other overload groups, emit the stubs plus a single valid fallback body
   containing a `TODO(j2py)` and `NotImplementedError`.

`super(...)` constructor invocations translate to `super().__init__(...)`.

## Consequences

+ Duplicate Python definitions are no longer emitted silently.
+ Simple Spring-style constructors such as `this("default")` become idiomatic Python
  default parameters.
+ Reviewers still see every original Java overload signature.
− Runtime dispatch for complex overload groups remains unsupported until a later rule
  can prove a safe implementation shape.
− The rule uses body-text equality for simple method merges; semantically equivalent
  but textually different overload bodies remain TODO fallbacks.

## References

- [Issue #8](https://github.com/tomanizer/j2py/issues/8)
- [ADR 0005](0005-python-311-target-with-type-hints.md)

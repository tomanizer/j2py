# ADR 0012 — Sealed type metadata

**Date:** 2026-06-13
**Status:** Accepted

## Context

Java sealed classes and interfaces constrain which subclasses may extend or implement a
type. Python has no direct sealed-type declaration, and runtime enforcement would add
machinery that distracts from j2py's side-by-side review goal.

The existing type-declaration policy in ADR 0007 preserves Java declaration shape in
valid Python. Sealed metadata should follow that style: visible, reviewable, and simple.

## Decision

j2py preserves sealed metadata in the rule-layer output without runtime enforcement:

- `sealed` declarations emit a comment showing the `permits` list.
- `final` permitted classes emit `# final`.
- `non-sealed` classes emit `# non-sealed`.
- When every permitted type is a direct nested type in the same declaration body, emit a
  nested union alias named `<TypeName>Permitted`.

The alias is a structural review aid, not a runtime guard. Cross-file `permits` clauses
are preserved as comments in this slice; cross-file union aliasing would require symbol
table coordination and can be added separately.

## Consequences

+ Reviewers can see `sealed`, `permits`, `final`, and `non-sealed` semantics in the
  Python output.
+ Nested permitted record/class declarations remain near the sealed declaration.
+ Output stays dependency-free and consistent with ADR 0007.
- Python code can still subclass sealed translations at runtime; enforcement is deferred.

## References

- [Issue #122](https://github.com/tomanizer/j2py/issues/122)
- [ADR 0007](0007-type-declaration-translation.md)

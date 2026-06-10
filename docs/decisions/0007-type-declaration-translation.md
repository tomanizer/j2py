# ADR 0007 — Type declaration translation

**Date:** 2026-06-10
**Status:** Accepted

## Context

Spring code frequently uses Java declarations beyond simple top-level classes:
nested classes, interfaces, enums, records, and annotation types. j2py needs valid
Python output for these declarations while preserving the original structure for
side-by-side review.

## Decision

j2py translates type declarations as follows:

1. Java classes translate to Python classes. Nested Java classes remain nested Python
   classes.
2. Java interfaces translate to `typing.Protocol` classes with method stubs.
3. Java enums translate to Python `Enum` classes with string-valued constants.
4. Java records translate to frozen dataclasses with fields from the record header.
5. Java annotation type declarations translate to valid Python placeholder classes with
   an explicit `TODO(j2py)`.

The skeleton generator emits imports for `dataclass`, `Enum`, and `Protocol` only when
the generated output uses those symbols.

## Consequences

+ Nested and top-level type declarations now produce syntactically valid Python.
+ Reviewers can see the Java declaration shape directly in the Python skeleton.
+ Record value semantics are represented with frozen dataclasses.
− Interface default methods and enum constructors remain future work.
− Annotation types are intentionally placeholders because Python has no direct
  declaration equivalent.

## References

- [Issue #9](https://github.com/tomanizer/j2py/issues/9)
- [ADR 0005](0005-python-311-target-with-type-hints.md)

# ADR 0008 — Expression narrowing and bitwise translation

**Date:** 2026-06-11
**Status:** Accepted

## Context

Spring corpus translation showed repeated deterministic gaps around Java expression
semantics that Python can only approximate directly:

- `instanceof` expressions, including Java pattern variables
- cast expressions such as `(Class<?>) value`
- bitwise and shift operators used heavily by bytecode-oriented code

Leaving these unsupported forced valid Java methods into unresolved Python stubs even
when the surrounding control flow was otherwise straightforward. At the same time,
Java casts and unsigned right shift do not have exact Python syntax equivalents.

## Decision

`instanceof` translates to Python runtime type checks:

```python
isinstance(value, RuntimeType)
```

For Java pattern variables, the `if` true branch receives a local binding after the
runtime check:

```python
if isinstance(value, str):
    text = value
```

Cast expressions are erased to the operand expression and emit a warning diagnostic:

```python
value
```

The warning reason is `dropped Java cast; verify runtime type`.

Java bitwise operators `&`, `|`, `^`, `<<`, and `>>` translate to the matching Python
operators. Compound assignment for these operators translates to the matching Python
compound assignment form.

Java unsigned right shift (`>>>`) translates to a masked Python signed shift based on
the known Java operand width:

```python
(value & 0xFFFFFFFF) >> bits
(value & 0xFFFFFFFFFFFFFFFF) >> bits
```

The 32-bit mask is used for known `int`, `byte`, `short`, `char`, and boxed
equivalents. The 64-bit mask is used for known `long` and `Long`. Unsigned right shift
assignment (`>>>=`) translates to an explicit assignment to the same masked expression.

When the Java operand width is unknown, the translator emits the 32-bit form and warns:
`unsigned right shift assumed 32-bit int width; verify operand type`.

## Consequences

+ Common Spring corpus expression shapes now translate deterministically instead of
  becoming unresolved regions.
+ Generated code remains valid Python and side-by-side reviewable.
+ Unsigned right shift on known integral widths preserves Java results for negative
  operands.
+ Unknown-width unsigned right shift remains valid Python and is marked with an
  explicit diagnostic.
- Cast runtime checks are not preserved.

## References

- `tests/fixtures/java/targets/InstanceofExpression.java`
- `tests/fixtures/java/targets/CastExpression.java`
- `tests/fixtures/java/targets/BitwiseOperators.java`
- `tests/fixtures/java/targets/CompoundAssignment.java`

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

Cast expressions translate based on the cast target type:

**Primitive numeric casts** map to Python builtins or bit-level equivalents:

| Java cast | Source type | Python translation |
|---|---|---|
| `(int) x` / `(long) x` | numeric | `int(x)` |
| `(int) c` / `(long) c` | `char` | `ord(c)` |
| `(float) x` / `(double) x` | numeric | `float(x)` |
| `(float) c` / `(double) c` | `char` | `float(ord(c))` |
| `(byte) x` | numeric | `((int(x) & 0xFF) ^ 0x80) - 0x80` |
| `(byte) c` | `char` | `((ord(c) & 0xFF) ^ 0x80) - 0x80` |
| `(short) x` | numeric | `((int(x) & 0xFFFF) ^ 0x8000) - 0x8000` |
| `(short) c` | `char` | `((ord(c) & 0xFFFF) ^ 0x8000) - 0x8000` |
| `(char) x` | numeric | `chr(int(x) & 0xFFFF)` |
| `(char) c` | `char` | `c` (identity) |

The byte/short XOR formula (`(v ^ sign_bit) - sign_bit`) reinterprets the unsigned
masked value as a two's-complement signed integer without a conditional branch. The
`char` source type is detected from variable and field Java type metadata in the
translation context; if the source type is unknown the translator falls back to `int()`
for integral casts.

**Reference casts** emit `typing.cast()` and record a reviewer warning:

```python
cast(TargetType, value)
```

The warning reason is `Java reference cast translated to typing.cast; verify runtime type`.
`typing.cast` is a no-op at runtime (it exists for type checkers only), which matches
Java reference cast semantics: the JVM also performs no widening or narrowing on the
bits — it only checks assignability at runtime. The `cast` name is auto-imported from
`typing` when it appears in generated class output.

Java bitwise operators `&`, `|`, `^`, `<<`, and `>>` translate to the matching Python
operators. Java bitwise complement (`~`) translates to Python `~` for integral
operands, preserving explicit grouping around lower-precedence operands such as
`~(left | right)`. Compound assignment for these operators translates to the matching
Python compound assignment form.

Java unsigned right shift (`>>>`) translates to a masked Python signed shift based on
the known Java operand width:

```python
(value & 0xFFFFFFFF) >> (bits & 0x1F)
(value & 0xFFFFFFFFFFFFFFFF) >> (bits & 0x3F)
```

Java masks the shift distance to 5 bits for `int` operands and 6 bits for `long`
operands before applying the unsigned right shift.

The 32-bit mask is used for known `int`, `byte`, `short`, `char`, and boxed
equivalents. The 64-bit mask is used for known `long` and `Long`. Unsigned right shift
assignment (`>>>=`) translates to an explicit assignment to the same masked expression.

When the Java operand width is unknown, the translator emits the 32-bit form and warns:
`unsigned right shift assumed 32-bit int width; verify operand type`.

## Consequences

+ Common Spring corpus expression shapes now translate deterministically instead of
  becoming unresolved regions.
+ Generated code remains valid Python and side-by-side reviewable.
+ Numeric casts preserve Java semantics including two's-complement narrowing for
  byte and short.
+ Unsigned right shift on known integral widths preserves Java results for negative
  operands.
+ Unknown-width unsigned right shift remains valid Python and is marked with an
  explicit diagnostic.
+ Reference casts are now visible in generated output as `typing.cast(...)` rather
  than being silently dropped, improving side-by-side reviewability.
- Java reference cast runtime `ClassCastException` checks are not preserved; the
  generated Python raises no equivalent exception for a wrong type.
- Primitive cast source-type detection is limited to simple identifiers and
  `this`-field accesses; complex expressions involving `char` fall back to `int()`.

## References

- `tests/fixtures/java/targets/InstanceofExpression.java`
- `tests/fixtures/java/targets/CastExpression.java`
- `tests/fixtures/java/targets/BitwiseOperators.java`
- `tests/fixtures/java/targets/CompoundAssignment.java`

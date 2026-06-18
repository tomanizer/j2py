# NumberUtils equivalence case study

Apache Commons Lang `NumberUtils` is the current end-to-end equivalence case study for
the gap between structural translation and semantic proof. The rule layer can translate
large parts of the fixture, but the verified number is the runtime surface exercised by
literal-oracle tests in `tests/equivalence/test_number_utils.py`, not the node-coverage
score.

As of the current equivalence surface floor, `NumberUtils.java` has **60 of 61** public
method signatures verified by the
equivalence gate. The verified methods are:

| Java surface | Verified signatures |
|---|---:|
| `toInt` | `NumberUtils.toInt(String)`, `NumberUtils.toInt(String,int)` |
| `toLong` | `NumberUtils.toLong(String)`, `NumberUtils.toLong(String,long)` |
| `toDouble` | String and BigDecimal overloads, including default-value overloads |
| `toFloat` | `NumberUtils.toFloat(String)`, `NumberUtils.toFloat(String,float)` |
| `toByte` | `NumberUtils.toByte(String)`, `NumberUtils.toByte(String,byte)` |
| `toShort` | `NumberUtils.toShort(String)`, `NumberUtils.toShort(String,short)` |
| `toScaledBigDecimal` | BigDecimal, Double, Float, and String overloads, including scale/rounding overloads |
| `create*` | `createNumber`, `createInteger`, `createLong`, `createFloat`, `createDouble`, `createBigDecimal` |
| `compare` | byte, short, int, and long overloads |
| `min` / `max` | byte, short, int, long, float, and double fixed-arity and varargs overloads |
| `isParsable` | `NumberUtils.isParsable(String)` |
| `isDigits` | `NumberUtils.isDigits(String)` |
| `isCreatable` | `NumberUtils.isCreatable(String)` |
| `isNumber` | `NumberUtils.isNumber(String)` |

The current post-0.6.0b1 equivalence wave raised the repository floor to **96/97**
public signatures. Within `NumberUtils`, the only remaining unverified public method is
`NumberUtils.createBigInteger(String)`.

## Stub boundary

The test harness deliberately avoids a Python JDK runtime. `tests/equivalence/harness.py`
installs only the import-time and parser stubs needed to load and exercise this fixture:
`Long`, `Integer`, `Double`, `Character`, `StringUtils`, `Validate`, `Array`, and
`RoundingMode` are identity, no-op, or constant-bearing stubs. The behavior-bearing
boundary for this slice includes `Float.parse_float`, `Byte.parse_byte`,
`Short.parse_short`, and a small `BigDecimal` shim backed by Python `decimal.Decimal`.
The byte and short stubs enforce Java range limits so fallback-default behavior remains
meaningful, while the BigDecimal shim exists only to exercise the Commons-Lang conversion
contract in this fixture.

Those stubs are harness dependencies, not translator output under test. They exist to make
the translated class importable and to isolate the `NumberUtils` methods with
literal-oracle expectations.

## Exclusions

The following `NumberUtils` areas remain intentionally outside this case-study surface:

| Excluded surface | Reason |
|---|---|
| `createBigInteger(String)` | Still outside the fixture harness because Python's unbounded `int` does not exercise Java `BigInteger` construction and radix parsing through the same path. |

These exclusions are why the headline must stay **node coverage is not verification**.
Coverage says whether the rule layer emitted Python for Java syntax. The equivalence
surface says which public signatures have passed independent, literal-oracle runtime
checks.

See the 2026-06-17 audit snapshot in
[docs/decisions/AUDIT-2026-06-17.md](decisions/AUDIT-2026-06-17.md) and the tracking case
study issue [#372](https://github.com/tomanizer/j2py/issues/372).

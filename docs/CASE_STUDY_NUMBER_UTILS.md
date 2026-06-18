# NumberUtils equivalence case study

Apache Commons Lang `NumberUtils` is the current end-to-end equivalence case study for
the gap between structural translation and semantic proof. The rule layer can translate
large parts of the fixture, but the verified number is the runtime surface exercised by
literal-oracle tests in `tests/equivalence/test_number_utils.py`, not the node-coverage
score.

As of the current equivalence surface floor, `NumberUtils.java` has **19 of 61** public
method signatures verified by the
equivalence gate. The verified methods are:

| Java surface | Verified signatures |
|---|---:|
| `toInt` | `NumberUtils.toInt(String)`, `NumberUtils.toInt(String,int)` |
| `toLong` | `NumberUtils.toLong(String)`, `NumberUtils.toLong(String,long)` |
| `toDouble` | `NumberUtils.toDouble(String)`, `NumberUtils.toDouble(String,double)` |
| `toFloat` | `NumberUtils.toFloat(String)`, `NumberUtils.toFloat(String,float)` |
| `toByte` | `NumberUtils.toByte(String)`, `NumberUtils.toByte(String,byte)` |
| `toShort` | `NumberUtils.toShort(String)`, `NumberUtils.toShort(String,short)` |
| `compare` | `NumberUtils.compare(byte,byte)`, `NumberUtils.compare(short,short)`, `NumberUtils.compare(int,int)`, `NumberUtils.compare(long,long)` |
| `isParsable` | `NumberUtils.isParsable(String)` |
| `isDigits` | `NumberUtils.isDigits(String)` |
| `isCreatable` | `NumberUtils.isCreatable(String)` |

The NumberUtils slice raised the checked-in equivalence surface from **28/97** to
**34/97** public signatures as `compare` and `isParsable` landed. Later fixes for
`StringUtils.isBlank`, `StringUtils.strip`, `StringUtils.contains`,
`StringUtils.startsWith`, `StringUtils.endsWith`, `NumberUtils.isDigits`, and
`NumberUtils.isCreatable` moved the repository floor to **41/97**.

## Stub boundary

The test harness deliberately avoids a Python JDK runtime. `tests/equivalence/harness.py`
installs only the import-time and parser stubs needed to load and exercise this fixture:
`Long`, `Integer`, `Double`, `Character`, `StringUtils`, `Validate`, `Array`, and
`RoundingMode` are identity, no-op, or constant-bearing stubs. The behavior-bearing
boundary for this slice is limited to `Float.parse_float`, `Byte.parse_byte`, and
`Short.parse_short`, because the translated `toFloat`, `toByte`, and `toShort` methods
delegate through those Java parser names. The byte and short stubs enforce Java range
limits so fallback-default behavior remains meaningful.

Those stubs are harness dependencies, not translator output under test. They exist to make
the translated class importable and to isolate the `NumberUtils` methods with
literal-oracle expectations.

## Exclusions

The following `NumberUtils` areas remain intentionally outside this case-study surface:

| Excluded surface | Reason |
|---|---|
| `createNumber` | The method depends on broader numeric-construction, BigInteger/BigDecimal, suffix, and radix semantics that are outside the current harness boundary. `isCreatable` is now covered, but the object-construction method itself remains outside the verified surface. |
| `createBigInteger`, `createBigDecimal`, BigInteger/BigDecimal converters, `toScaledBigDecimal` | Python has no direct parity with Java `BigInteger`/`BigDecimal` construction, scale, and rounding contracts in the current harness boundary. |
| `min` / `max` | Deferred because the Java overload set mixes varargs and fixed arity, and the erased Python dispatch policy is still ambiguous. |

These exclusions are why the headline must stay **node coverage is not verification**.
Coverage says whether the rule layer emitted Python for Java syntax. The equivalence
surface says which public signatures have passed independent, literal-oracle runtime
checks.

See the 2026-06-17 audit snapshot in
[docs/decisions/AUDIT-2026-06-17.md](decisions/AUDIT-2026-06-17.md) and the tracking case
study issue [#372](https://github.com/tomanizer/j2py/issues/372).

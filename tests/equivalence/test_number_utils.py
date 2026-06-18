"""Equivalence gate for NumberUtils — Phase 1 literal-oracle tests.

  Bug 2 (FIXED in #216): ``RuntimeException`` catch was mapped to ``RuntimeError``
      instead of ``Exception``.  The structural test below asserts the fix holds.

Class-body stubs
----------------
The module-scoped ``_java_lang_stubs`` fixture (autouse) installs identity stubs
for the boxed-type classes the class body references at definition time
(``Long.value_of``, ``Short.value_of``, ..., ``Integer.min_value``).

``to_float`` / ``to_byte`` / ``to_short`` each delegate to ``Float.parse_float``,
``Byte.parse_byte``, ``Short.parse_short`` — the stubs implement Java-compatible
numeric parsing, including byte/short range checks.
"""

from __future__ import annotations

import sys

import pytest

from tests.equivalence.comparator import (
    approx_double,
    approx_float,
    assert_equivalent,
    assert_raises_mapped,
)
from tests.equivalence.harness import (
    BigDecimal,
    RoundingMode,
    install_java_lang_stubs,
    load_translated_module,
    number_utils_runtime_globals,
    translate_rule_layer,
)

JAVA_CLASS = "NumberUtils.java"
surface = pytest.mark.equivalence_surface


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def number_utils_source() -> str:
    return translate_rule_layer(JAVA_CLASS)


@pytest.fixture(scope="module", autouse=True)
def _java_lang_stubs():
    """Install Java boxed-type stubs once for the whole test module, then clean up."""
    stub_modules = install_java_lang_stubs()
    yield
    for name in reversed(stub_modules):
        sys.modules.pop(name, None)


# ── Structural tests (always run) ─────────────────────────────────────────────


@pytest.mark.equivalence
def test_to_int_defined(number_utils_source: str) -> None:
    assert "def to_int(str_: str, default_value: int = 0) -> int:" in number_utils_source


@pytest.mark.equivalence
def test_to_long_defined(number_utils_source: str) -> None:
    assert "def to_long(str_: str, default_value: int = 0) -> int:" in number_utils_source


@pytest.mark.equivalence
def test_to_double_defined(number_utils_source: str) -> None:
    # String overload: 1-arg Java method becomes a delegating overload (not default_value=0.0).
    assert "def to_double(str_: str) -> float:" in number_utils_source
    assert "return NumberUtils.to_double(str_, 0.0)" in number_utils_source


@pytest.mark.equivalence
def test_to_float_defined(number_utils_source: str) -> None:
    # Plain literal default (0.0f) inlines as a parameter default, like to_int/to_long.
    assert "def to_float(str_: str, default_value: float = 0.0) -> float:" in number_utils_source


@pytest.mark.equivalence
def test_to_byte_defined(number_utils_source: str) -> None:
    # Cast default ((byte) 0) can't inline as a literal default, so the merge uses the
    # None-sentinel pattern and reconstructs the value in the body.
    assert "def to_byte(str_: str, default_value: int | None = None) -> int:" in number_utils_source


@pytest.mark.equivalence
def test_to_short_defined(number_utils_source: str) -> None:
    assert (
        "def to_short(str_: str, default_value: int | None = None) -> int:" in number_utils_source
    )


@pytest.mark.equivalence
def test_exception_mapping_is_exception_not_runtime_error(number_utils_source: str) -> None:
    """Bug 2 regression: to_int/to_long/to_double must catch Exception, not RuntimeError.

    Fixed in PR #216 — ``RuntimeException`` → ``Exception`` in EXCEPTION_MAP.
    """
    assert "except RuntimeError" not in number_utils_source
    assert number_utils_source.count("except Exception") >= 3


# ── Module-load gate (xfail until Bug 1 is fixed) ─────────────────────────────


@pytest.mark.equivalence
def test_module_compiles(number_utils_source: str) -> None:
    """Module must compile cleanly before any behavioral tests can activate."""
    compile(number_utils_source, "<NumberUtils>", "exec")


@pytest.mark.equivalence
def test_number_utils_string_utils_stub_helpers() -> None:
    string_utils = sys.modules["org.apache.commons.lang3.StringUtils"].StringUtils

    assert string_utils.is_empty(None) is True
    assert string_utils.is_empty("") is True
    assert string_utils.is_empty(" ") is False
    assert string_utils.is_blank(None) is True
    assert string_utils.is_blank(" ") is True
    assert string_utils.is_blank("a") is False
    assert string_utils.is_numeric("123") is True
    assert string_utils.is_numeric("12.3") is False


# ── Behavioral tests — adapted from upstream NumberUtilsTest.java ──────────────
#
# Literal-oracle source: NumberUtilsTest.java lines 1681–1721 (toInt, toLong)
# and lines 1586–1616 (toDouble).  Expression-oracle assertions (MAX_VALUE etc.)
# are omitted to avoid correlated-failure risk.


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toInt(String)")
@surface(JAVA_CLASS, "NumberUtils.toInt(String,int)")
def test_to_int_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toInt")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 1681–1684
    assert NumberUtils.to_int("12345") == 12345
    assert NumberUtils.to_int("abc") == 0
    assert NumberUtils.to_int("") == 0
    assert NumberUtils.to_int(None) == 0
    # from NumberUtilsTest.java lines 1692–1695
    assert NumberUtils.to_int("12345", 5) == 12345
    assert NumberUtils.to_int("1234.5", 5) == 5
    assert NumberUtils.to_int("", 5) == 5
    assert NumberUtils.to_int(None, 5) == 5


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toLong(String)")
@surface(JAVA_CLASS, "NumberUtils.toLong(String,long)")
def test_to_long_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toLong")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 1703–1710
    assert NumberUtils.to_long("12345") == 12345
    assert NumberUtils.to_long("abc") == 0
    assert NumberUtils.to_long("1L") == 0  # Java long suffix — not a valid int literal
    assert NumberUtils.to_long("1l") == 0
    assert NumberUtils.to_long("") == 0
    assert NumberUtils.to_long(None) == 0
    # from NumberUtilsTest.java lines 1718–1721
    assert NumberUtils.to_long("12345", 5) == 12345
    assert NumberUtils.to_long("1234.5", 5) == 5
    assert NumberUtils.to_long("", 5) == 5
    assert NumberUtils.to_long(None, 5) == 5


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toDouble(String)")
@surface(JAVA_CLASS, "NumberUtils.toDouble(String,double)")
def test_to_double_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toDouble")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 1586–1600
    assert NumberUtils.to_double("-1.2345") == approx_double(-1.2345)
    assert NumberUtils.to_double("1.2345") == approx_double(1.2345)
    assert NumberUtils.to_double("abc") == 0.0
    assert NumberUtils.to_double("-001.2345") == approx_double(-1.2345)
    assert NumberUtils.to_double("+001.2345") == approx_double(1.2345)
    assert NumberUtils.to_double("001.2345") == approx_double(1.2345)
    assert NumberUtils.to_double("000.00000") == approx_double(0.0)
    assert NumberUtils.to_double("") == 0.0
    assert NumberUtils.to_double(None) == 0.0
    # from NumberUtilsTest.java lines 1608–1616
    assert NumberUtils.to_double("1.2345", 5.1) == approx_double(1.2345)
    assert NumberUtils.to_double("a", 5.0) == approx_double(5.0)
    assert NumberUtils.to_double("001.2345", 5.1) == approx_double(1.2345)
    assert NumberUtils.to_double("-001.2345", 5.1) == approx_double(-1.2345)
    assert NumberUtils.to_double("+001.2345", 5.1) == approx_double(1.2345)
    assert NumberUtils.to_double("000.00", 5.1) == approx_double(0.0)
    assert NumberUtils.to_double("", 5.1) == approx_double(5.1)
    assert NumberUtils.to_double(None, 5.1) == approx_double(5.1)


# ── BigDecimal conversions ───────────────────────────────────────────────────


def _load_number_utils_with_big_decimal(number_utils_source: str, name: str):
    return load_translated_module(
        number_utils_source,
        name,
        injected_globals=number_utils_runtime_globals(),
    )


def _assert_decimal_equivalent(expected: BigDecimal, actual: BigDecimal) -> None:
    assert actual == expected
    assert actual.as_tuple().exponent == expected.as_tuple().exponent


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toDouble(BigDecimal)")
@surface(JAVA_CLASS, "NumberUtils.toDouble(BigDecimal,double)")
def test_to_double_big_decimal_equivalence(number_utils_source: str) -> None:
    mod = _load_number_utils_with_big_decimal(number_utils_source, "_NumberUtils_toDoubleBD")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    assert NumberUtils.to_double(BigDecimal("3.14")) == approx_double(3.14)
    assert NumberUtils.to_double(BigDecimal("0")) == approx_double(0.0)
    assert NumberUtils.to_double(None) == approx_double(0.0)
    assert NumberUtils.to_double(BigDecimal("2.5"), 99.9) == approx_double(2.5)
    assert NumberUtils.to_double(None, 99.9) == approx_double(99.9)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(BigDecimal)")
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(BigDecimal,int,RoundingMode)")
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(Double)")
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(Double,int,RoundingMode)")
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(Float)")
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(Float,int,RoundingMode)")
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(String)")
@surface(JAVA_CLASS, "NumberUtils.toScaledBigDecimal(String,int,RoundingMode)")
def test_to_scaled_big_decimal_equivalence(number_utils_source: str) -> None:
    mod = _load_number_utils_with_big_decimal(number_utils_source, "_NumberUtils_scaledBD")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    for value, expected in [
        (BigDecimal("3.14159"), BigDecimal("3.14")),
        (BigDecimal("2.345"), BigDecimal("2.34")),
        (None, BigDecimal("0")),
        (3.14159, BigDecimal("3.14")),
        (3.14, BigDecimal("3.14")),
        ("3.14159", BigDecimal("3.14")),
    ]:
        _assert_decimal_equivalent(expected, NumberUtils.to_scaled_big_decimal(value))

    for value, scale, rounding_mode, expected in [
        (BigDecimal("3.14159"), 3, RoundingMode.HALF_UP, BigDecimal("3.142")),
        (BigDecimal("3.14159"), 3, RoundingMode.DOWN, BigDecimal("3.141")),
        (BigDecimal("3.14159"), 3, None, BigDecimal("3.142")),
        (None, 2, RoundingMode.HALF_EVEN, BigDecimal("0")),
        (3.14159, 3, RoundingMode.HALF_UP, BigDecimal("3.142")),
        (3.0, 0, RoundingMode.HALF_UP, BigDecimal("3")),
        ("3.14159", 4, RoundingMode.FLOOR, BigDecimal("3.1415")),
        (None, 2, RoundingMode.HALF_EVEN, BigDecimal("0")),
    ]:
        _assert_decimal_equivalent(
            expected,
            NumberUtils.to_scaled_big_decimal(value, scale, rounding_mode),
        )


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.createBigDecimal(String)")
def test_create_big_decimal_equivalence(number_utils_source: str) -> None:
    mod = _load_number_utils_with_big_decimal(number_utils_source, "_NumberUtils_createBD")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    for value, expected in [
        ("3.14", BigDecimal("3.14")),
        ("1e10", BigDecimal("1e10")),
    ]:
        _assert_decimal_equivalent(expected, NumberUtils.create_big_decimal(value))
    assert_equivalent(None, NumberUtils.create_big_decimal(None))
    for invalid in ["", " ", "not-a-number"]:
        with assert_raises_mapped("NumberFormatException"):
            NumberUtils.create_big_decimal(invalid)


# ── create* null-return converters ────────────────────────────────────────────


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.createInteger(String)")
def test_create_integer_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_createInteger")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    for value, expected in [
        ("42", 42),
        ("0", 0),
        ("-7", -7),
        ("0x1F", 31),
        ("077", 63),
        (None, None),
    ]:
        assert_equivalent(expected, NumberUtils.create_integer(value))
    for invalid in ["abc", " 123", "123 "]:
        with assert_raises_mapped("NumberFormatException"):
            NumberUtils.create_integer(invalid)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.createLong(String)")
def test_create_long_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_createLong")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    for value, expected in [
        ("1000000000000", 1_000_000_000_000),
        ("0", 0),
        ("0X1F", 31),
        ("077", 63),
        (None, None),
    ]:
        assert_equivalent(expected, NumberUtils.create_long(value))
    for invalid in ["xyz", " 123", "123 "]:
        with assert_raises_mapped("NumberFormatException"):
            NumberUtils.create_long(invalid)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.createFloat(String)")
def test_create_float_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_createFloat")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    for value, expected in [
        ("3.14", 3.14),
        ("0.0", 0.0),
    ]:
        assert NumberUtils.create_float(value) == approx_float(expected)
    assert_equivalent(None, NumberUtils.create_float(None))
    with assert_raises_mapped("NumberFormatException"):
        NumberUtils.create_float("nope")


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.createDouble(String)")
def test_create_double_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_createDouble")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    for value, expected in [
        ("2.718", 2.718),
        ("1e10", 1e10),
    ]:
        assert NumberUtils.create_double(value) == approx_double(expected)
    assert_equivalent(None, NumberUtils.create_double(None))
    with assert_raises_mapped("NumberFormatException"):
        NumberUtils.create_double("nope")


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.compare(byte,byte)")
@surface(JAVA_CLASS, "NumberUtils.compare(int,int)")
@surface(JAVA_CLASS, "NumberUtils.compare(long,long)")
@surface(JAVA_CLASS, "NumberUtils.compare(short,short)")
def test_compare_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_compare")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from Apache Commons Lang NumberUtilsTest.java lines 59-98:
    # https://github.com/apache/commons-lang/blob/master/src/test/java/org/apache/commons/lang3/math/NumberUtilsTest.java#L59-L98
    assert NumberUtils.compare(5, 2) > 0
    assert NumberUtils.compare(2, 5) < 0
    assert NumberUtils.compare(3, 3) == 0
    assert NumberUtils.compare(-128, 127) < 0
    # Test short boundaries
    assert NumberUtils.compare(-32768, 32767) < 0
    assert NumberUtils.compare(32767, -32768) > 0
    # Test int boundaries
    assert NumberUtils.compare(-2147483648, 2147483647) < 0
    assert NumberUtils.compare(2147483647, -2147483648) > 0
    # Test long boundaries
    assert NumberUtils.compare(-9223372036854775808, 9223372036854775807) < 0
    assert NumberUtils.compare(9223372036854775807, -9223372036854775808) > 0


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.max(byte,byte,byte)")
@surface(JAVA_CLASS, "NumberUtils.max(double,double,double)")
@surface(JAVA_CLASS, "NumberUtils.max(float,float,float)")
@surface(JAVA_CLASS, "NumberUtils.max(int,int,int)")
@surface(JAVA_CLASS, "NumberUtils.max(long,long,long)")
@surface(JAVA_CLASS, "NumberUtils.max(short,short,short)")
def test_max_three_arg_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_maxThree")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    assert NumberUtils.max_(-128, 0, 127) == 127
    assert NumberUtils.max_(-32768, 32767, 0) == 32767
    assert NumberUtils.max_(-2147483648, 2147483647, 0) == 2147483647
    assert NumberUtils.max_(-9223372036854775808, 0, 9223372036854775807) == (9223372036854775807)
    assert NumberUtils.max_(-1.25, 3.5, 2.0) == approx_double(3.5)
    assert NumberUtils.max_(1.0, -4.25, 0.5) == approx_double(1.0)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.max(byte...)")
@surface(JAVA_CLASS, "NumberUtils.max(double...)")
@surface(JAVA_CLASS, "NumberUtils.max(float...)")
@surface(JAVA_CLASS, "NumberUtils.max(int...)")
@surface(JAVA_CLASS, "NumberUtils.max(long...)")
@surface(JAVA_CLASS, "NumberUtils.max(short...)")
def test_max_varargs_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_maxVarargs")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    assert NumberUtils.max_(-128, 0, 127, 12) == 127
    assert NumberUtils.max_(-32768, 32767, 0, 22) == 32767
    assert NumberUtils.max_(-2147483648, 0, 2147483647) == 2147483647
    assert NumberUtils.max_(-9223372036854775808, 0, 9223372036854775807) == (9223372036854775807)
    assert NumberUtils.max_(-1.25, 3.5, 2.0, 0.0) == approx_double(3.5)
    assert NumberUtils.max_(1.0, -4.25, 0.5) == approx_double(1.0)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.min(byte,byte,byte)")
@surface(JAVA_CLASS, "NumberUtils.min(double,double,double)")
@surface(JAVA_CLASS, "NumberUtils.min(float,float,float)")
@surface(JAVA_CLASS, "NumberUtils.min(int,int,int)")
@surface(JAVA_CLASS, "NumberUtils.min(long,long,long)")
@surface(JAVA_CLASS, "NumberUtils.min(short,short,short)")
def test_min_three_arg_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_minThree")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    assert NumberUtils.min_(-128, 0, 127) == -128
    assert NumberUtils.min_(0, 32767, -32768) == -32768
    assert NumberUtils.min_(2147483647, 0, -2147483648) == -2147483648
    assert NumberUtils.min_(9223372036854775807, 0, -9223372036854775808) == (-9223372036854775808)
    assert NumberUtils.min_(-1.25, 3.5, 2.0) == approx_double(-1.25)
    assert NumberUtils.min_(1.0, -4.25, 0.5) == approx_double(-4.25)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.min(byte...)")
@surface(JAVA_CLASS, "NumberUtils.min(double...)")
@surface(JAVA_CLASS, "NumberUtils.min(float...)")
@surface(JAVA_CLASS, "NumberUtils.min(int...)")
@surface(JAVA_CLASS, "NumberUtils.min(long...)")
@surface(JAVA_CLASS, "NumberUtils.min(short...)")
def test_min_varargs_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_minVarargs")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    assert NumberUtils.min_(-128, 0, 127, 12) == -128
    assert NumberUtils.min_(0, 32767, -32768, 22) == -32768
    assert NumberUtils.min_(2147483647, 0, -2147483648) == -2147483648
    assert NumberUtils.min_(9223372036854775807, 0, -9223372036854775808) == (-9223372036854775808)
    assert NumberUtils.min_(-1.25, 3.5, 2.0, 0.0) == approx_double(-1.25)
    assert NumberUtils.min_(1.0, -4.25, 0.5) == approx_double(-4.25)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.isNumber(String)")
def test_is_number_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_isNumber")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]

    assert NumberUtils.is_number("12345") is True
    assert NumberUtils.is_number("1234.5") is True
    assert NumberUtils.is_number(".12345") is True
    assert NumberUtils.is_number("1234E+5") is True
    assert NumberUtils.is_number("-1234") is True
    assert NumberUtils.is_number("-0xABC123") is True
    assert NumberUtils.is_number("22338L") is True
    assert NumberUtils.is_number("+0xF") is True
    assert NumberUtils.is_number(None) is False
    assert NumberUtils.is_number("") is False
    assert NumberUtils.is_number(" ") is False
    assert NumberUtils.is_number("--2.3") is False
    assert NumberUtils.is_number(".12.3") is False
    assert NumberUtils.is_number("-123E") is False
    assert NumberUtils.is_number("0xGF") is False
    assert NumberUtils.is_number(".") is False
    assert NumberUtils.is_number("11a") is False
    assert NumberUtils.is_number("1.1L") is False


# ── Phase 2 converters (toFloat / toByte / toShort) ───────────────────────────
#
# Literal-oracle source: NumberUtilsTest.java testToFloatString / testToFloatStringF,
# testToByteString / testToByteStringI, testToShortString / testToShortStringI.
# The translated converters delegate to the Float.parse_float / Byte.parse_byte /
# Short.parse_short stubs; decimal results use approx_double because the Python
# translation widens to double rather than 32-bit float.


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toFloat(String)")
@surface(JAVA_CLASS, "NumberUtils.toFloat(String,float)")
def test_to_float_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toFloat")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # toFloat(String)
    assert NumberUtils.to_float("-1.2345") == approx_double(-1.2345)
    assert NumberUtils.to_float("1.2345") == approx_double(1.2345)
    assert NumberUtils.to_float("abc") == 0.0
    assert NumberUtils.to_float("-001.2345") == approx_double(-1.2345)
    assert NumberUtils.to_float("+001.2345") == approx_double(1.2345)
    assert NumberUtils.to_float("001.2345") == approx_double(1.2345)
    assert NumberUtils.to_float("000.00000") == approx_double(0.0)
    assert NumberUtils.to_float("") == 0.0
    assert NumberUtils.to_float(None) == 0.0
    # toFloat(String, float)
    assert NumberUtils.to_float("1.2345", 5.1) == approx_double(1.2345)
    assert NumberUtils.to_float("a", 5.0) == approx_double(5.0)
    assert NumberUtils.to_float("", 5.1) == approx_double(5.1)
    assert NumberUtils.to_float(None, 5.1) == approx_double(5.1)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toByte(String)")
@surface(JAVA_CLASS, "NumberUtils.toByte(String,byte)")
def test_to_byte_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toByte")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # toByte(String)
    assert NumberUtils.to_byte("123") == 123
    assert NumberUtils.to_byte("abc") == 0
    assert NumberUtils.to_byte("") == 0
    assert NumberUtils.to_byte(None) == 0
    # toByte(String, byte)
    assert NumberUtils.to_byte("123", 5) == 123
    assert NumberUtils.to_byte("12.3", 5) == 5
    assert NumberUtils.to_byte("", 5) == 5
    assert NumberUtils.to_byte(None, 5) == 5
    assert NumberUtils.to_byte("128", 5) == 5
    assert NumberUtils.to_byte("-129", 5) == 5


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.toShort(String)")
@surface(JAVA_CLASS, "NumberUtils.toShort(String,short)")
def test_to_short_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toShort")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # toShort(String)
    assert NumberUtils.to_short("12345") == 12345
    assert NumberUtils.to_short("abc") == 0
    assert NumberUtils.to_short("") == 0
    assert NumberUtils.to_short(None) == 0
    # toShort(String, short)
    assert NumberUtils.to_short("12345", 5) == 12345
    assert NumberUtils.to_short("1234.5", 5) == 5
    assert NumberUtils.to_short("", 5) == 5
    assert NumberUtils.to_short(None, 5) == 5
    assert NumberUtils.to_short("32768", 5) == 5
    assert NumberUtils.to_short("-32769", 5) == 5


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.isParsable(String)")
def test_is_parsable_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_isParsable")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 1006-1024
    assert NumberUtils.is_parsable(None) is False
    assert NumberUtils.is_parsable("") is False
    assert NumberUtils.is_parsable("0xC1AB") is False
    assert NumberUtils.is_parsable("65CBA2") is False
    assert NumberUtils.is_parsable("pendro") is False
    assert NumberUtils.is_parsable("64, 2") is False
    assert NumberUtils.is_parsable("64.2.2") is False
    assert NumberUtils.is_parsable("64.") is False  # trailing-dot guard
    assert NumberUtils.is_parsable("64L") is False
    assert NumberUtils.is_parsable("-") is False
    assert NumberUtils.is_parsable("--2") is False
    assert NumberUtils.is_parsable("64.2") is True
    assert NumberUtils.is_parsable("64") is True
    assert NumberUtils.is_parsable("018") is True
    assert NumberUtils.is_parsable(".18") is True
    assert NumberUtils.is_parsable("-65") is True
    assert NumberUtils.is_parsable("-018") is True
    assert NumberUtils.is_parsable("-018.2") is True
    assert NumberUtils.is_parsable("-.236") is True


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.isDigits(String)")
def test_is_digits_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_isDigits")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 888-893
    assert NumberUtils.is_digits(None) is False
    assert NumberUtils.is_digits("") is False
    assert NumberUtils.is_digits("12345") is True
    assert NumberUtils.is_digits("1234.5") is False
    assert NumberUtils.is_digits("1ab") is False
    assert NumberUtils.is_digits("abc") is False


@pytest.mark.equivalence
@surface(JAVA_CLASS, "NumberUtils.isCreatable(String)")
def test_is_creatable_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_isCreatable")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 822-884 (literal-only subset)
    assert NumberUtils.is_creatable("12345") is True
    assert NumberUtils.is_creatable("1234.5") is True
    assert NumberUtils.is_creatable(".12345") is True
    assert NumberUtils.is_creatable("1234E5") is True
    assert NumberUtils.is_creatable("1234E+5") is True
    assert NumberUtils.is_creatable("1234E-5") is True
    assert NumberUtils.is_creatable("-1234") is True
    assert NumberUtils.is_creatable("0") is True
    assert NumberUtils.is_creatable("-0xABC123") is True
    assert NumberUtils.is_creatable("22338L") is True
    assert NumberUtils.is_creatable("2.") is True
    assert NumberUtils.is_creatable("+0xF") is True
    assert NumberUtils.is_creatable(".0") is True
    assert NumberUtils.is_creatable("0.") is True
    assert NumberUtils.is_creatable("0e1") is True
    assert NumberUtils.is_creatable(None) is False
    assert NumberUtils.is_creatable("") is False
    assert NumberUtils.is_creatable(" ") is False
    assert NumberUtils.is_creatable("--2.3") is False
    assert NumberUtils.is_creatable(".12.3") is False
    assert NumberUtils.is_creatable("-123E") is False
    assert NumberUtils.is_creatable("0xGF") is False
    assert NumberUtils.is_creatable(".") is False
    assert NumberUtils.is_creatable("11a") is False
    assert NumberUtils.is_creatable("1.1L") is False
    assert NumberUtils.is_creatable(".D") is False
    assert NumberUtils.is_creatable(".e10") is False

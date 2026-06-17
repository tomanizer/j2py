"""Equivalence gate for NumberUtils — Phase 1 literal-oracle tests.

  Bug 2 (FIXED in #216): ``RuntimeException`` catch was mapped to ``RuntimeError``
      instead of ``Exception``.  The structural test below asserts the fix holds.

Class-body stubs
----------------
The module-scoped ``_java_lang_stubs`` fixture (autouse) installs identity stubs
for the boxed-type classes the class body references at definition time
(``Long.value_of``, ``Short.value_of``, ..., ``Integer.min_value``).

``to_float`` / ``to_byte`` / ``to_short`` each delegate to ``Float.parse_float``,
``Byte.parse_byte``, ``Short.parse_short`` — the stubs implement these as
``float(x)`` / ``int(x)`` so they are semantically correct.
"""

from __future__ import annotations

import sys

import pytest

from tests.equivalence.comparator import approx_double
from tests.equivalence.harness import (
    install_java_lang_stubs,
    load_translated_module,
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


# ── Phase 2 converters (toFloat / toByte / toShort) ───────────────────────────
#
# Literal-oracle source: NumberUtilsTest.java testToFloatString / testToFloatStringF,
# testToByteString / testToByteStringI, testToShortString / testToShortStringI.
# The translated converters delegate to the Float.parse_float / Byte.parse_byte /
# Short.parse_short stubs (float(x) / int(x)); decimal results use approx_double
# because the Python translation widens to double rather than 32-bit float.


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

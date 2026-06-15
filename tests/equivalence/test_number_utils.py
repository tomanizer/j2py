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


# ── Behavioral tests — adapted from upstream NumberUtilsTest.java ──────────────
#
# Literal-oracle source: NumberUtilsTest.java lines 1681–1721 (toInt, toLong)
# and lines 1586–1616 (toDouble).  Expression-oracle assertions (MAX_VALUE etc.)
# are omitted to avoid correlated-failure risk.


@pytest.mark.equivalence
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
def test_to_long_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toLong")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 1703–1710
    assert NumberUtils.to_long("12345") == 12345
    assert NumberUtils.to_long("abc") == 0
    assert NumberUtils.to_long("1L") == 0   # Java long suffix — not a valid int literal
    assert NumberUtils.to_long("1l") == 0
    assert NumberUtils.to_long("") == 0
    assert NumberUtils.to_long(None) == 0
    # from NumberUtilsTest.java lines 1718–1721
    assert NumberUtils.to_long("12345", 5) == 12345
    assert NumberUtils.to_long("1234.5", 5) == 5
    assert NumberUtils.to_long("", 5) == 5
    assert NumberUtils.to_long(None, 5) == 5


@pytest.mark.equivalence
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

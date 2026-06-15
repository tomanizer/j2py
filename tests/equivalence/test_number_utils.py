"""Equivalence gate for NumberUtils — Phase 1 literal-oracle tests.

Known bugs tracked by xfail(strict=True) below:

  Bug 1 (OPEN): ``isCreatable`` SyntaxError — ``StringUtils.contains(str, '.')``
      is mis-translated to ``not str_, "." in StringUtils`` at line 517.
      Blocks ``compile()`` of the whole module, so all behavioral tests are xfailed.
      Fix requires a rule-layer change in expression translation (method call on
      external class whose first argument shadows a Python builtin).

  Bug 2 (FIXED in #216): ``RuntimeException`` catch was mapped to ``RuntimeError``
      instead of ``Exception``.  The structural test below asserts the fix holds.

Stubs needed once Bug 1 is fixed
---------------------------------
The class body (at definition time) calls ``Long.value_of(0)``,
``Short.value_of(...)``, ``Byte.value_of(...)``, ``Double.value_of(0.0)``,
``Float.value_of(0.0)`` — all imported as ``from org.apache.commons.lang3.math.*``.
``install_java_lang_stubs()`` must be added to harness.py before the module can
be loaded and behavioral tests can activate.

Additionally ``to_float`` translates ``Float.parseFloat(str)`` as
``Float.parse_float(str_)`` and ``to_byte``/``to_short`` similarly — the stub for
those types must implement ``parse_float``/``parse_byte``/``parse_short`` as
``float(x)`` / ``int(x)`` respectively, or the rule layer must map them directly.
"""

from __future__ import annotations

import pytest

from tests.equivalence.harness import load_translated_module, translate_rule_layer

JAVA_CLASS = "NumberUtils.java"


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def number_utils_source() -> str:
    return translate_rule_layer(JAVA_CLASS)


# ── Structural tests (always run) ─────────────────────────────────────────────


@pytest.mark.equivalence
def test_to_int_defined(number_utils_source: str) -> None:
    assert "def to_int(str_: str, default_value: int = 0) -> int:" in number_utils_source


@pytest.mark.equivalence
def test_to_long_defined(number_utils_source: str) -> None:
    assert "def to_long(str_: str, default_value: int = 0) -> int:" in number_utils_source


@pytest.mark.equivalence
def test_to_double_defined(number_utils_source: str) -> None:
    assert "def to_double(str_: str, default_value: float) -> float:" in number_utils_source


@pytest.mark.equivalence
def test_exception_mapping_is_exception_not_runtime_error(number_utils_source: str) -> None:
    """Bug 2 regression: to_int/to_long/to_double must catch Exception, not RuntimeError.

    Fixed in PR #216 — ``RuntimeException`` → ``Exception`` in EXCEPTION_MAP.
    """
    assert "except RuntimeError" not in number_utils_source
    assert number_utils_source.count("except Exception") >= 3


# ── Module-load gate (xfail until Bug 1 is fixed) ─────────────────────────────


@pytest.mark.equivalence
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Bug 1: isCreatable mis-translates StringUtils.contains — "
        "produces `not str_, '.' in StringUtils` (SyntaxError at line 517)"
    ),
)
def test_module_compiles(number_utils_source: str) -> None:
    """Module must compile cleanly before any behavioral tests can activate."""
    compile(number_utils_source, "<NumberUtils>", "exec")


# ── Behavioral tests — adapted from upstream NumberUtilsTest.java ──────────────
#
# All tests below are xfailed because ``load_translated_module`` raises SyntaxError
# at the ``compile()`` step (Bug 1).  Remove xfail once:
#   1. Bug 1 (SyntaxError) is fixed
#   2. install_java_lang_stubs() is added to harness.py and called in the fixture
#
# Literal-oracle source: NumberUtilsTest.java lines 1681–1721 (toInt, toLong)
# and lines 1586–1616 (toDouble).  Expression-oracle assertions (MAX_VALUE etc.)
# are omitted to avoid correlated-failure risk.


@pytest.mark.equivalence
@pytest.mark.xfail(
    strict=True,
    reason="Bug 1 (SyntaxError) blocks module loading; also needs class-body stubs",
)
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
@pytest.mark.xfail(
    strict=True,
    reason="Bug 1 (SyntaxError) blocks module loading; also needs class-body stubs",
)
def test_to_long_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toLong")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 1703–1710
    assert NumberUtils.to_long("12345") == 12345
    assert NumberUtils.to_long("abc") == 0
    assert NumberUtils.to_long("1L") == 0   # Java suffix — not a valid int literal
    assert NumberUtils.to_long("1l") == 0
    assert NumberUtils.to_long("") == 0
    assert NumberUtils.to_long(None) == 0
    # from NumberUtilsTest.java lines 1718–1721
    assert NumberUtils.to_long("12345", 5) == 12345
    assert NumberUtils.to_long("1234.5", 5) == 5
    assert NumberUtils.to_long("", 5) == 5
    assert NumberUtils.to_long(None, 5) == 5


@pytest.mark.equivalence
@pytest.mark.xfail(
    strict=True,
    reason="Bug 1 (SyntaxError) blocks module loading; also needs class-body stubs",
)
def test_to_double_equivalence(number_utils_source: str) -> None:
    mod = load_translated_module(number_utils_source, "_NumberUtils_toDouble")
    NumberUtils = mod.NumberUtils  # type: ignore[attr-defined]
    # from NumberUtilsTest.java lines 1586–1600
    assert NumberUtils.to_double("-1.2345") == pytest.approx(-1.2345)
    assert NumberUtils.to_double("1.2345") == pytest.approx(1.2345)
    assert NumberUtils.to_double("abc") == 0.0
    assert NumberUtils.to_double("-001.2345") == pytest.approx(-1.2345)
    assert NumberUtils.to_double("+001.2345") == pytest.approx(1.2345)
    assert NumberUtils.to_double("001.2345") == pytest.approx(1.2345)
    assert NumberUtils.to_double("000.00000") == pytest.approx(0.0)
    assert NumberUtils.to_double("") == 0.0
    assert NumberUtils.to_double(None) == 0.0
    # from NumberUtilsTest.java lines 1608–1616
    assert NumberUtils.to_double("1.2345", 5.1) == pytest.approx(1.2345)
    assert NumberUtils.to_double("a", 5.0) == pytest.approx(5.0)
    assert NumberUtils.to_double("001.2345", 5.1) == pytest.approx(1.2345)
    assert NumberUtils.to_double("-001.2345", 5.1) == pytest.approx(-1.2345)
    assert NumberUtils.to_double("+001.2345", 5.1) == pytest.approx(1.2345)
    assert NumberUtils.to_double("000.00", 5.1) == pytest.approx(0.0)
    assert NumberUtils.to_double("", 5.1) == pytest.approx(5.1)
    assert NumberUtils.to_double(None, 5.1) == pytest.approx(5.1)

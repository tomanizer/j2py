"""Unit tests for the equivalence comparator — verifying the normalisation helpers.

The comparator is a trust anchor (see docs/EQUIVALENCE_TESTING.md §2); its own
correctness must be independently verified, never assumed.
"""

from __future__ import annotations

import pytest

from tests.equivalence.comparator import (
    BYTE_MAX,
    BYTE_MIN,
    INT_MAX,
    INT_MIN,
    LONG_MAX,
    LONG_MIN,
    SHORT_MAX,
    SHORT_MIN,
    approx_double,
    approx_float,
    assert_raises_mapped,
    java_int,
    java_long,
)


# ---------------------------------------------------------------------------
# Integer range constants
# ---------------------------------------------------------------------------


def test_int_constants_match_java_spec() -> None:
    assert INT_MIN == -(2**31)
    assert INT_MAX == 2**31 - 1
    assert INT_MAX - INT_MIN == 2**32 - 1


def test_long_constants_match_java_spec() -> None:
    assert LONG_MIN == -(2**63)
    assert LONG_MAX == 2**63 - 1


def test_byte_short_constants() -> None:
    assert BYTE_MIN == -128
    assert BYTE_MAX == 127
    assert SHORT_MIN == -32768
    assert SHORT_MAX == 32767


# ---------------------------------------------------------------------------
# java_int — boundary wrapping
# ---------------------------------------------------------------------------


def test_java_int_identity_in_range() -> None:
    assert java_int(0) == 0
    assert java_int(1) == 1
    assert java_int(-1) == -1
    assert java_int(INT_MAX) == INT_MAX
    assert java_int(INT_MIN) == INT_MIN


def test_java_int_wraps_overflow() -> None:
    assert java_int(INT_MAX + 1) == INT_MIN    # +1 overflow wraps to MIN
    assert java_int(INT_MIN - 1) == INT_MAX    # -1 underflow wraps to MAX
    assert java_int(2**32) == 0


def test_java_int_large_positive() -> None:
    assert java_int(2**31) == INT_MIN
    assert java_int(2**32 - 1) == -1


# ---------------------------------------------------------------------------
# java_long — boundary wrapping
# ---------------------------------------------------------------------------


def test_java_long_identity_in_range() -> None:
    assert java_long(0) == 0
    assert java_long(LONG_MAX) == LONG_MAX
    assert java_long(LONG_MIN) == LONG_MIN


def test_java_long_wraps_overflow() -> None:
    assert java_long(LONG_MAX + 1) == LONG_MIN
    assert java_long(LONG_MIN - 1) == LONG_MAX
    assert java_long(2**64) == 0


# ---------------------------------------------------------------------------
# Float approximation
# ---------------------------------------------------------------------------


def test_approx_float_matches_within_single_precision() -> None:
    assert 1.2345001 == approx_float(1.2345)   # within 1e-5 rel
    assert 0.0 == approx_float(0.0)


def test_approx_float_rejects_large_difference() -> None:
    with pytest.raises(AssertionError):
        assert 1.5 == approx_float(1.2345)


def test_approx_double_matches_within_double_precision() -> None:
    assert 1.234500001 == approx_double(1.2345)   # within 1e-9 rel
    assert -1.2345 == approx_double(-1.2345)


def test_approx_double_rejects_single_precision_error() -> None:
    # A difference that passes approx_float (1e-5) but fails approx_double (1e-9)
    with pytest.raises(AssertionError):
        assert 1.2345001 == approx_double(1.2345)


# ---------------------------------------------------------------------------
# assert_raises_mapped
# ---------------------------------------------------------------------------


def test_assert_raises_mapped_number_format_exception() -> None:
    with assert_raises_mapped("NumberFormatException"):
        int("not-a-number")


def test_assert_raises_mapped_illegal_argument_exception() -> None:
    with assert_raises_mapped("IllegalArgumentException"):
        raise ValueError("bad arg")


def test_assert_raises_mapped_unknown_exception_raises_key_error() -> None:
    with pytest.raises(KeyError, match="NoSuchJavaException"):
        with assert_raises_mapped("NoSuchJavaException"):
            pass


def test_assert_raises_mapped_wrong_exception_fails() -> None:
    with pytest.raises(Exception):
        with assert_raises_mapped("NumberFormatException"):
            raise TypeError("wrong type")  # not ValueError

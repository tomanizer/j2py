"""Equivalence gate for Commons-Lang ``CharUtils`` (Phase 1 — see docs/EQUIVALENCE_TESTING.md).

Literal-oracle assertions ported from upstream ``CharUtilsTest.java`` (referenced by line)
run against the rule-layer-only translation of ``CharUtils.java``. The asserted values are
the literals the upstream test uses, which are JVM-independent — a failure here is a
transpiler divergence.

Overloaded methods (``toChar``, ``toIntValue``, ``toCharacterObject``, ``toString``,
``unicodeEscaped``) are intentionally out of the first surface: Java's ``char`` and
``Character`` both erase to Python ``str``, making same-arity overloads ambiguous at
dispatch. Non-overloaded static predicates and constants are fully covered here.
"""

from __future__ import annotations

import sys

import pytest

from tests.equivalence.harness import (
    install_array_utils_stub_package,
    load_translated_module,
    translate_rule_layer,
)

pytestmark = pytest.mark.equivalence


@pytest.fixture(scope="module")
def char_utils_source() -> str:
    return translate_rule_layer("CharUtils.java")


@pytest.fixture(scope="module")
def char_utils(char_utils_source: str):
    # Stub ArrayUtils so the class body static cache initializer can run and
    # the pure CharUtils methods under test become callable.
    stub_modules = install_array_utils_stub_package()
    module = load_translated_module(char_utils_source, "char_utils_fixture")
    yield module.CharUtils
    sys.modules.pop("char_utils_fixture", None)
    for name in reversed(stub_modules):
        sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Constants (LF, CR, NUL) — CharUtils.java:44,52,60
#
# The rule layer emits Java CONSTANT_CASE fields as lowercase Python attributes
# (lf, cr, nul). Python convention (PEP 8) wants UPPER_CASE — this is a
# known naming-rule bug; tracked separately. Test the actual emitted names so
# that values are verified even while the naming issue is open.
# ---------------------------------------------------------------------------


def test_constants_values(char_utils):
    assert char_utils.lf == "\n"  # CharUtils.java:44
    assert char_utils.cr == "\r"  # CharUtils.java:52
    assert char_utils.nul == "\0"  # CharUtils.java:60


@pytest.mark.xfail(
    strict=True,
    reason="rule layer lowercases CONSTANT_CASE fields; should be LF/CR/NUL per PEP 8",
)
def test_constants_names_are_upper(char_utils):
    # When the naming bug is fixed, this xfail becomes an error and must be removed.
    assert hasattr(char_utils, "LF") and hasattr(char_utils, "CR") and hasattr(char_utils, "NUL")


# ---------------------------------------------------------------------------
# compare — CharUtilsTest:43-47
# ---------------------------------------------------------------------------


def test_compare_less(char_utils):
    assert char_utils.compare("a", "b") < 0  # CharUtilsTest:44


def test_compare_equal(char_utils):
    assert char_utils.compare("c", "c") == 0  # CharUtilsTest:45


def test_compare_greater(char_utils):
    assert char_utils.compare("c", "a") > 0  # CharUtilsTest:46


# ---------------------------------------------------------------------------
# isAscii — CharUtilsTest:57-71
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", True),  # CharUtilsTest:58
        ("A", True),  # CharUtilsTest:59
        ("3", True),  # CharUtilsTest:60
        ("-", True),  # CharUtilsTest:61
        ("\n", True),  # CharUtilsTest:62
        ("©", False),  # CharUtilsTest:63 CHAR_COPY (non-ASCII)
    ],
)
def test_is_ascii(char_utils, ch, expected):
    assert char_utils.is_ascii(ch) is expected


@pytest.mark.parametrize("i", range(128))
def test_is_ascii_range_true(char_utils, i):
    assert char_utils.is_ascii(chr(i)) is True  # CharUtilsTest:65-67


@pytest.mark.parametrize("i", range(128, 196))
def test_is_ascii_range_false(char_utils, i):
    assert char_utils.is_ascii(chr(i)) is False  # CharUtilsTest:65-67


# ---------------------------------------------------------------------------
# isAsciiAlpha — CharUtilsTest:73-88
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", True),  # CharUtilsTest:74
        ("A", True),  # CharUtilsTest:75
        ("3", False),  # CharUtilsTest:76
        ("-", False),  # CharUtilsTest:77
        ("\n", False),  # CharUtilsTest:78
        ("©", False),  # CharUtilsTest:79
    ],
)
def test_is_ascii_alpha(char_utils, ch, expected):
    assert char_utils.is_ascii_alpha(ch) is expected


@pytest.mark.parametrize(
    "i",
    [i for i in range(196) if ord("A") <= i <= ord("Z") or ord("a") <= i <= ord("z")],
)
def test_is_ascii_alpha_range_true(char_utils, i):
    assert char_utils.is_ascii_alpha(chr(i)) is True  # CharUtilsTest:81-87


@pytest.mark.parametrize(
    "i",
    [i for i in range(196) if not (ord("A") <= i <= ord("Z") or ord("a") <= i <= ord("z"))],
)
def test_is_ascii_alpha_range_false(char_utils, i):
    assert char_utils.is_ascii_alpha(chr(i)) is False  # CharUtilsTest:81-87


# ---------------------------------------------------------------------------
# isAsciiAlphaLower — CharUtilsTest:90-105
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", True),  # CharUtilsTest:91
        ("A", False),  # CharUtilsTest:92
        ("3", False),  # CharUtilsTest:93
        ("-", False),  # CharUtilsTest:94
        ("\n", False),  # CharUtilsTest:95
        ("©", False),  # CharUtilsTest:96
    ],
)
def test_is_ascii_alpha_lower(char_utils, ch, expected):
    assert char_utils.is_ascii_alpha_lower(ch) is expected


@pytest.mark.parametrize("i", [i for i in range(196) if ord("a") <= i <= ord("z")])
def test_is_ascii_alpha_lower_range_true(char_utils, i):
    assert char_utils.is_ascii_alpha_lower(chr(i)) is True  # CharUtilsTest:98-104


@pytest.mark.parametrize("i", [i for i in range(196) if not (ord("a") <= i <= ord("z"))])
def test_is_ascii_alpha_lower_range_false(char_utils, i):
    assert char_utils.is_ascii_alpha_lower(chr(i)) is False  # CharUtilsTest:98-104


# ---------------------------------------------------------------------------
# isAsciiAlphaUpper — CharUtilsTest:107-122
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", False),  # CharUtilsTest:108
        ("A", True),  # CharUtilsTest:109
        ("3", False),  # CharUtilsTest:110
        ("-", False),  # CharUtilsTest:111
        ("\n", False),  # CharUtilsTest:112
        ("©", False),  # CharUtilsTest:113
    ],
)
def test_is_ascii_alpha_upper(char_utils, ch, expected):
    assert char_utils.is_ascii_alpha_upper(ch) is expected


@pytest.mark.parametrize("i", [i for i in range(196) if ord("A") <= i <= ord("Z")])
def test_is_ascii_alpha_upper_range_true(char_utils, i):
    assert char_utils.is_ascii_alpha_upper(chr(i)) is True  # CharUtilsTest:115-121


@pytest.mark.parametrize("i", [i for i in range(196) if not (ord("A") <= i <= ord("Z"))])
def test_is_ascii_alpha_upper_range_false(char_utils, i):
    assert char_utils.is_ascii_alpha_upper(chr(i)) is False  # CharUtilsTest:115-121


# ---------------------------------------------------------------------------
# isAsciiAlphanumeric — CharUtilsTest:124-139
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", True),  # CharUtilsTest:125
        ("A", True),  # CharUtilsTest:126
        ("3", True),  # CharUtilsTest:127
        ("-", False),  # CharUtilsTest:128
        ("\n", False),  # CharUtilsTest:129
        ("©", False),  # CharUtilsTest:130
    ],
)
def test_is_ascii_alphanumeric(char_utils, ch, expected):
    assert char_utils.is_ascii_alphanumeric(ch) is expected


@pytest.mark.parametrize(
    "i",
    [
        i
        for i in range(196)
        if ord("A") <= i <= ord("Z") or ord("a") <= i <= ord("z") or ord("0") <= i <= ord("9")
    ],
)
def test_is_ascii_alphanumeric_range_true(char_utils, i):
    assert char_utils.is_ascii_alphanumeric(chr(i)) is True  # CharUtilsTest:132-138


@pytest.mark.parametrize(
    "i",
    [
        i
        for i in range(196)
        if not (ord("A") <= i <= ord("Z") or ord("a") <= i <= ord("z") or ord("0") <= i <= ord("9"))
    ],
)
def test_is_ascii_alphanumeric_range_false(char_utils, i):
    assert char_utils.is_ascii_alphanumeric(chr(i)) is False  # CharUtilsTest:132-138


# ---------------------------------------------------------------------------
# isAsciiControl — CharUtilsTest:141-156
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", False),  # CharUtilsTest:142
        ("A", False),  # CharUtilsTest:143
        ("3", False),  # CharUtilsTest:144
        ("-", False),  # CharUtilsTest:145
        ("\n", True),  # CharUtilsTest:146
        ("©", False),  # CharUtilsTest:147
    ],
)
def test_is_ascii_control(char_utils, ch, expected):
    assert char_utils.is_ascii_control(ch) is expected


@pytest.mark.parametrize("i", [i for i in range(196) if i < 32 or i == 127])
def test_is_ascii_control_range_true(char_utils, i):
    assert char_utils.is_ascii_control(chr(i)) is True  # CharUtilsTest:149-155


@pytest.mark.parametrize("i", [i for i in range(196) if not (i < 32 or i == 127)])
def test_is_ascii_control_range_false(char_utils, i):
    assert char_utils.is_ascii_control(chr(i)) is False  # CharUtilsTest:149-155


# ---------------------------------------------------------------------------
# isAsciiNumeric — CharUtilsTest:174-189
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("3", True),  # CharUtilsTest:181
        ("a", False),  # CharUtilsTest:179
        ("A", False),  # CharUtilsTest:180
        ("-", False),  # CharUtilsTest:182
        ("\n", False),  # CharUtilsTest:183
        ("©", False),  # CharUtilsTest:184
    ],
)
def test_is_ascii_numeric(char_utils, ch, expected):
    assert char_utils.is_ascii_numeric(ch) is expected


@pytest.mark.parametrize("i", [i for i in range(196) if ord("0") <= i <= ord("9")])
def test_is_ascii_numeric_range_true(char_utils, i):
    assert char_utils.is_ascii_numeric(chr(i)) is True  # CharUtilsTest:186-188


@pytest.mark.parametrize("i", [i for i in range(196) if not (ord("0") <= i <= ord("9"))])
def test_is_ascii_numeric_range_false(char_utils, i):
    assert char_utils.is_ascii_numeric(chr(i)) is False  # CharUtilsTest:186-188


# ---------------------------------------------------------------------------
# isAsciiPrintable — CharUtilsTest:158-173
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ch", "expected"),
    [
        ("a", True),  # CharUtilsTest:159
        ("A", True),  # CharUtilsTest:160
        ("3", True),  # CharUtilsTest:161
        ("-", True),  # CharUtilsTest:162
        ("\n", False),  # CharUtilsTest:163
        ("©", False),  # CharUtilsTest:164
    ],
)
def test_is_ascii_printable(char_utils, ch, expected):
    assert char_utils.is_ascii_printable(ch) is expected


@pytest.mark.parametrize("i", [i for i in range(196) if 32 <= i <= 126])
def test_is_ascii_printable_range_true(char_utils, i):
    assert char_utils.is_ascii_printable(chr(i)) is True  # CharUtilsTest:166-172


@pytest.mark.parametrize("i", [i for i in range(196) if not (32 <= i <= 126)])
def test_is_ascii_printable_range_false(char_utils, i):
    assert char_utils.is_ascii_printable(chr(i)) is False  # CharUtilsTest:166-172


# ---------------------------------------------------------------------------
# Structural: ArrayUtils import is fully qualified (regression for #188)
# ---------------------------------------------------------------------------


def test_class_reference_qualified(char_utils_source: str):
    assert "from org.apache.commons.lang3.ArrayUtils import ArrayUtils" in char_utils_source
    assert "ArrayUtils.set_all" in char_utils_source
    assert "array_utils.set_all" not in char_utils_source

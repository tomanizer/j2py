"""Equivalence gate for Commons-Lang ``CharUtils`` (Phase 1 — see docs/EQUIVALENCE_TESTING.md).

Literal-oracle assertions ported from upstream ``CharUtilsTest.java`` (referenced by line)
run against the rule-layer-only translation of ``CharUtils.java``. The asserted values are
the literals the upstream test uses, which are JVM-independent — a failure here is a
transpiler divergence.

Known divergences are tracked as ``xfail(strict)`` against their issues so that fixing the
translation flips the marker and forces its removal. Overloaded methods (``toChar``,
``toIntValue``) are intentionally out of the first surface: they fall back to a by-design
``NotImplementedError`` manual-dispatch stub, not a silent bug.
"""

from __future__ import annotations

import pytest

from tests.equivalence.harness import (
    array_utils_stub,
    load_translated_module,
    translate_rule_layer,
)

pytestmark = pytest.mark.equivalence


@pytest.fixture(scope="module")
def char_utils_source() -> str:
    return translate_rule_layer("CharUtils.java")


@pytest.fixture(scope="module")
def char_utils(char_utils_source: str):
    # ArrayUtils.setAll is referenced but unimported (bug #188); stub it so the class
    # body (a static cache initializer) can run and the methods become callable.
    module = load_translated_module(
        char_utils_source,
        "char_utils_fixture",
        {"array_utils": array_utils_stub()},
    )
    return module.CharUtils


# --- Correctly translated, non-overloaded methods: these must pass. ---------------


def test_compare_equal(char_utils):
    assert char_utils.compare("c", "c") == 0  # CharUtilsTest:45


@pytest.mark.parametrize("ch", ["a", "A", "3", "-", "\n"])  # CharUtilsTest:61-65
def test_is_ascii(char_utils, ch):
    assert char_utils.is_ascii(ch) is True


@pytest.mark.parametrize(
    ("ch", "expected"),
    [("3", True), ("a", False), ("A", False)],  # CharUtilsTest:181-183
)
def test_is_ascii_numeric(char_utils, ch, expected):
    assert char_utils.is_ascii_numeric(ch) is expected


# --- Known divergences, tracked as strict xfails. --------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="#187: sibling static methods called as bare unqualified names -> NameError",
)
@pytest.mark.parametrize(
    ("ch", "expected"),
    [("a", True), ("A", True), ("3", False)],  # CharUtilsTest:75-77
)
def test_is_ascii_alpha(char_utils, ch, expected):
    assert char_utils.is_ascii_alpha(ch) is expected


@pytest.mark.xfail(
    strict=True,
    reason="#188: external class ArrayUtils emitted as bare lowercased identifier, unimported",
)
def test_class_reference_qualified(char_utils_source: str):
    # When #188 is fixed the class name is retained/qualified instead of being
    # snake-cased into a bare module-style reference with no import.
    assert "array_utils.set_all" not in char_utils_source

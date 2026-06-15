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


@pytest.mark.parametrize(
    ("ch", "expected"),
    [("a", True), ("A", True), ("3", False)],  # CharUtilsTest:75-77
)
def test_is_ascii_alpha(char_utils, ch, expected):
    assert char_utils.is_ascii_alpha(ch) is expected


def test_class_reference_qualified(char_utils_source: str):
    assert "from org.apache.commons.lang3.ArrayUtils import ArrayUtils" in char_utils_source
    assert "ArrayUtils.set_all" in char_utils_source
    assert "array_utils.set_all" not in char_utils_source

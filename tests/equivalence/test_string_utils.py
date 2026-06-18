"""Equivalence gate for Commons-Lang ``StringUtils`` focused surface.

Literal-oracle assertions are ported from upstream StringUtils tests and Javadoc
examples for the focused fixture. Expression-oracle assertions are intentionally
omitted so this remains a JVM-independent rule-layer gate.
"""

from __future__ import annotations

import sys

import pytest

from tests.equivalence.harness import (
    char_sequence_utils_stub,
    character_stub,
    install_string_utils_stubs,
    load_translated_module,
    translate_rule_layer,
)

JAVA_CLASS = "StringUtils.java"
surface = pytest.mark.equivalence_surface


@pytest.fixture(scope="module")
def string_utils_source() -> str:
    return translate_rule_layer(JAVA_CLASS)


@pytest.fixture(scope="module", autouse=True)
def _string_utils_stubs():
    """Install StringUtils dependency stubs once for the whole test module."""
    stub_modules = install_string_utils_stubs()
    yield
    for name in reversed(stub_modules):
        sys.modules.pop(name, None)


@pytest.fixture(scope="module")
def string_utils(string_utils_source: str):
    module = load_translated_module(string_utils_source, "string_utils_fixture")
    yield module.StringUtils
    sys.modules.pop("string_utils_fixture", None)


@pytest.mark.equivalence
@surface(JAVA_CLASS, "StringUtils.isEmpty(CharSequence)")
def test_is_empty_equivalence(string_utils) -> None:
    # StringUtilsEmptyBlankTest.java:128-133
    assert string_utils.is_empty(None) is True
    assert string_utils.is_empty("") is True
    assert string_utils.is_empty(" ") is False
    assert string_utils.is_empty("a") is False
    assert string_utils.is_empty("foo") is False
    assert string_utils.is_empty("  foo  ") is False


@pytest.mark.equivalence
@surface(JAVA_CLASS, "StringUtils.isBlank(CharSequence)")
def test_is_blank_equivalence(string_utils) -> None:
    # StringUtilsEmptyBlankTest.java:118-123, plus StringUtils.java Javadoc.
    assert string_utils.is_blank(None) is True
    assert string_utils.is_blank("") is True
    assert string_utils.is_blank(" ") is True
    assert string_utils.is_blank("a") is False
    assert string_utils.is_blank("foo") is False
    assert string_utils.is_blank("  foo  ") is False


@pytest.mark.equivalence
@surface(JAVA_CLASS, "StringUtils.contains(CharSequence,CharSequence)")
def test_contains_char_sequence_equivalence(string_utils) -> None:
    # StringUtilsContainsTest.java:50-60
    assert string_utils.contains(None, None) is False
    assert string_utils.contains(None, "") is False
    assert string_utils.contains(None, "a") is False
    assert string_utils.contains("", None) is False
    assert string_utils.contains("", "") is True
    assert string_utils.contains("", "a") is False
    assert string_utils.contains("abc", "a") is True
    assert string_utils.contains("abc", "b") is True
    assert string_utils.contains("abc", "c") is True
    assert string_utils.contains("abc", "abc") is True
    assert string_utils.contains("abc", "z") is False


@pytest.mark.equivalence
def test_string_utils_dependency_stubs_match_java_edge_cases() -> None:
    char_sequences = char_sequence_utils_stub()
    character = character_stub()

    assert char_sequences.index_of("abc", "a", -5) == 0
    assert char_sequences.region_matches("abc", False, 4, "", 0, 0) is False
    assert char_sequences.region_matches("abc", False, 3, "", 0, 0) is True
    assert character.is_whitespace(32) is True
    assert character.is_whitespace(" ") is True
    assert character.is_whitespace("x") is False


@pytest.mark.equivalence
@surface(JAVA_CLASS, "StringUtils.startsWith(CharSequence,CharSequence)")
def test_starts_with_equivalence(string_utils) -> None:
    # StringUtilsStartsEndsWithTest.java:136-152 and StringUtils.java Javadoc.
    assert string_utils.starts_with(None, None) is True
    assert string_utils.starts_with("FOOBAR", None) is False
    assert string_utils.starts_with(None, "FOO") is False
    assert string_utils.starts_with("FOOBAR", "") is True
    assert string_utils.starts_with("foobar", "foo") is True
    assert string_utils.starts_with("FOOBAR", "FOO") is True
    assert string_utils.starts_with("foobar", "FOO") is False
    assert string_utils.starts_with("FOOBAR", "foo") is False
    assert string_utils.starts_with("foo", "foobar") is False
    assert string_utils.starts_with("bar", "foobar") is False
    assert string_utils.starts_with("foobar", "bar") is False
    assert string_utils.starts_with("FOOBAR", "BAR") is False
    assert string_utils.starts_with("foobar", "BAR") is False
    assert string_utils.starts_with("FOOBAR", "bar") is False


@pytest.mark.equivalence
@surface(JAVA_CLASS, "StringUtils.endsWith(CharSequence,CharSequence)")
def test_ends_with_equivalence(string_utils) -> None:
    # StringUtilsStartsEndsWithTest.java:40-56 and StringUtils.java Javadoc.
    assert string_utils.ends_with(None, None) is True
    assert string_utils.ends_with("FOOBAR", None) is False
    assert string_utils.ends_with(None, "FOO") is False
    assert string_utils.ends_with("FOOBAR", "") is True
    assert string_utils.ends_with("foobar", "foo") is False
    assert string_utils.ends_with("FOOBAR", "FOO") is False
    assert string_utils.ends_with("foobar", "FOO") is False
    assert string_utils.ends_with("FOOBAR", "foo") is False
    assert string_utils.ends_with("foo", "foobar") is False
    assert string_utils.ends_with("bar", "foobar") is False
    assert string_utils.ends_with("foobar", "bar") is True
    assert string_utils.ends_with("FOOBAR", "BAR") is True
    assert string_utils.ends_with("foobar", "BAR") is False
    assert string_utils.ends_with("FOOBAR", "bar") is False


@pytest.mark.equivalence
@surface(JAVA_CLASS, "StringUtils.trim(String)")
def test_trim_equivalence(string_utils) -> None:
    # StringUtilsTrimStripTest literal cases and StringUtils.java Javadoc.
    assert string_utils.trim(None) is None
    assert string_utils.trim("") == ""
    assert string_utils.trim("     ") == ""
    assert string_utils.trim("abc") == "abc"
    assert string_utils.trim("    abc    ") == "abc"


@pytest.mark.equivalence
@surface(JAVA_CLASS, "StringUtils.strip(String)")
def test_strip_equivalence(string_utils) -> None:
    # StringUtilsTrimStripTest.java:34-37
    strip = string_utils.strip
    assert strip(None) is None
    assert strip("") == ""
    assert strip("        ") == ""
    assert strip("  abc  ") == "abc"

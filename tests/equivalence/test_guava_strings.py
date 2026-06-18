"""Equivalence gate for Guava ``Strings`` focused surface."""

from __future__ import annotations

import sys

import pytest

from tests.equivalence.harness import (
    GuavaStringBuilder,
    JavaCharSequence,
    JavaString,
    install_guava_strings_stubs,
    load_translated_module,
    translate_rule_layer,
)

JAVA_CLASS = "Strings.java"
pytestmark = pytest.mark.equivalence
surface = pytest.mark.equivalence_surface


@pytest.fixture(scope="module")
def strings_source() -> str:
    return translate_rule_layer(JAVA_CLASS)


@pytest.fixture(scope="module")
def strings(strings_source: str):
    stub_modules = install_guava_strings_stubs()
    module = load_translated_module(strings_source, "guava_strings_fixture")
    yield module.Strings
    sys.modules.pop("guava_strings_fixture", None)
    for name in reversed(stub_modules):
        sys.modules.pop(name, None)


@surface(JAVA_CLASS, "Strings.nullToEmpty(String)")
def test_null_to_empty(strings) -> None:
    assert strings.null_to_empty(None) == ""
    assert strings.null_to_empty("") == ""
    assert strings.null_to_empty("abc") == "abc"


@surface(JAVA_CLASS, "Strings.emptyToNull(String)")
def test_empty_to_null(strings) -> None:
    assert strings.empty_to_null(None) is None
    assert strings.empty_to_null("") is None
    assert strings.empty_to_null("abc") == "abc"


@surface(JAVA_CLASS, "Strings.isNullOrEmpty(String)")
def test_is_null_or_empty(strings) -> None:
    assert strings.is_null_or_empty(None) is True
    assert strings.is_null_or_empty("") is True
    assert strings.is_null_or_empty(" ") is False
    assert strings.is_null_or_empty("abc") is False


@surface(JAVA_CLASS, "Strings.padStart(String,int,char)")
def test_pad_start(strings) -> None:
    assert strings.pad_start("7", 3, "0") == "007"
    assert strings.pad_start("2010", 3, "0") == "2010"
    assert strings.pad_start("", 2, "x") == "xx"


@surface(JAVA_CLASS, "Strings.padEnd(String,int,char)")
def test_pad_end(strings) -> None:
    assert strings.pad_end("4.", 5, "0") == "4.000"
    assert strings.pad_end("2010", 3, "!") == "2010"
    assert strings.pad_end("", 2, "x") == "xx"


@surface(JAVA_CLASS, "Strings.repeat(String,int)")
def test_repeat(strings) -> None:
    assert strings.repeat("x", 0) == ""
    assert strings.repeat("x", 1) == "x"
    assert strings.repeat(JavaString("ab"), 3) == "ababab"


def test_guava_string_stubs_match_java_edge_cases() -> None:
    assert JavaString("None").__eq__(None) is False
    assert JavaString("x") == JavaString("x")
    assert str(GuavaStringBuilder().append(None)) == "null"
    assert str(GuavaStringBuilder().append(None, 1, 3)) == "ul"


@surface(JAVA_CLASS, "Strings.commonPrefix(CharSequence,CharSequence)")
def test_common_prefix(strings) -> None:
    assert (
        str(strings.common_prefix(JavaCharSequence("foobar"), JavaCharSequence("foobaz")))
        == "fooba"
    )
    assert str(strings.common_prefix(JavaCharSequence("abc"), JavaCharSequence("xyz"))) == ""


@surface(JAVA_CLASS, "Strings.commonSuffix(CharSequence,CharSequence)")
def test_common_suffix(strings) -> None:
    assert (
        str(strings.common_suffix(JavaCharSequence("abcxyz"), JavaCharSequence("123xyz"))) == "xyz"
    )
    assert str(strings.common_suffix(JavaCharSequence("abc"), JavaCharSequence("xyz"))) == ""


@surface(JAVA_CLASS, "Strings.lenientFormat(String,Object...)")
def test_lenient_format_without_args(strings) -> None:
    assert strings.lenient_format("plain template") == "plain template"
    assert strings.lenient_format("%s without args") == "%s without args"


@pytest.mark.xfail(
    strict=True,
    reason="generated varargs code mutates Python's immutable *args tuple",
)
def test_lenient_format_with_args_known_gap(strings) -> None:
    assert strings.lenient_format("%s scored %s", "Ada", 42) == "Ada scored 42"

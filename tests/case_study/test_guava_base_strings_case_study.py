"""Guava ``Strings`` external case study (issue #658).

The assertions below are a focused pytest port of upstream ``StringsTest`` cases from
Guava 33.4.8. They run against the rule-layer translation linked by
``tests/case_study/guava_base_strings_harness.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.case_study.guava_base_strings_harness import (
    _RESIDUAL_GAP_PATCHES,
    link_guava_base_strings_namespace,
)

_NS = link_guava_base_strings_namespace()
Strings = _NS.Strings
JavaCharSequence = _NS.JavaCharSequence
JavaString = _NS.JavaString


def _java_text(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


def _cs(value: str) -> object:
    return JavaCharSequence(_java_text(value))


def test_null_to_empty() -> None:
    assert Strings.null_to_empty(None) == ""
    assert Strings.null_to_empty("") == ""
    assert Strings.null_to_empty("a") == "a"


def test_empty_to_null() -> None:
    assert Strings.empty_to_null(None) is None
    assert Strings.empty_to_null("") is None
    assert Strings.empty_to_null("a") == "a"


def test_is_null_or_empty() -> None:
    assert Strings.is_null_or_empty(None) is True
    assert Strings.is_null_or_empty("") is True
    assert Strings.is_null_or_empty("a") is False


@pytest.mark.parametrize(
    ("value", "minimum", "expected"),
    [
        ("", 0, ""),
        ("x", 0, "x"),
        ("x", 1, "x"),
        ("xx", 0, "xx"),
        ("xx", 2, "xx"),
        ("x", -1, "x"),
        ("", 1, "-"),
        ("", 2, "--"),
        ("x", 2, "-x"),
        ("x", 3, "--x"),
        ("xx", 3, "-xx"),
    ],
)
def test_pad_start(value: str, minimum: int, expected: str) -> None:
    assert Strings.pad_start(value, minimum, "-") == expected


@pytest.mark.parametrize(
    ("value", "minimum", "expected"),
    [
        ("", 0, ""),
        ("x", 0, "x"),
        ("x", 1, "x"),
        ("xx", 0, "xx"),
        ("xx", 2, "xx"),
        ("x", -1, "x"),
        ("", 1, "-"),
        ("", 2, "--"),
        ("x", 2, "x-"),
        ("x", 3, "x--"),
        ("xx", 3, "xx-"),
    ],
)
def test_pad_end(value: str, minimum: int, expected: str) -> None:
    assert Strings.pad_end(value, minimum, "-") == expected


def test_repeat() -> None:
    input_value = JavaString("20")

    assert Strings.repeat(input_value, 0) == ""
    assert str(Strings.repeat(input_value, 1)) == "20"
    assert Strings.repeat(input_value, 2) == "2020"
    assert Strings.repeat(input_value, 3) == "202020"
    assert Strings.repeat(JavaString(""), 4) == ""

    for i in range(0, 100):
        assert len(Strings.repeat(input_value, i)) == 2 * i


def test_repeat_negative_count_raises() -> None:
    with pytest.raises(AssertionError):
        Strings.repeat(JavaString("x"), -1)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("", "", ""),
        ("abc", "", ""),
        ("", "abc", ""),
        ("abcde", "xyz", ""),
        ("xyz", "abcde", ""),
        ("xyz", "abcxyz", ""),
        ("abc", "aaaaa", "a"),
        ("aa", "aaaaa", "aa"),
        ("abcdef", "abcxyz", "abc"),
        ("abc\\ud8ab\\udcabdef", "abc\\ud8ab\\udcabxyz", "abc\\ud8ab\\udcab"),
        ("abc\\ud8ab\\udcabdef", "abc\\ud8ab\\udcacxyz", "abc"),
        ("abc\\ud8ab\\udcabdef", "abc\\ud8ab\\ud8abxyz", "abc"),
        ("abc\\ud8ab\\ud8acdef", "abc\\ud8ab\\ud8acxyz", "abc\\ud8ab\\ud8ac"),
        ("abc\\ud8ab\\ud8abdef", "abc\\ud8ab\\ud8acxyz", "abc\\ud8ab"),
        ("\\ud8ab\\udcab", "\\ud8ab", ""),
        ("\\ud8ab", "\\ud8ab", "\\ud8ab"),
    ],
)
def test_common_prefix(left: str, right: str, expected: str) -> None:
    assert Strings.common_prefix(_cs(left), _cs(right)) == _java_text(expected)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("", "", ""),
        ("abc", "", ""),
        ("", "abc", ""),
        ("abcde", "xyz", ""),
        ("xyz", "abcde", ""),
        ("xyz", "xyzabc", ""),
        ("abc", "ccccc", "c"),
        ("aa", "aaaaa", "aa"),
        ("xyzabc", "xxxabc", "abc"),
        ("abc\\ud8ab\\udcabdef", "xyz\\ud8ab\\udcabdef", "\\ud8ab\\udcabdef"),
        ("abc\\ud8ab\\udcabdef", "abc\\ud8ac\\udcabdef", "def"),
        ("abc\\ud8ab\\udcabdef", "xyz\\udcab\\udcabdef", "def"),
        ("abc\\ud8ab\\ud8abdef", "xyz\\ud8ab\\ud8abdef", "\\ud8ab\\ud8abdef"),
        ("abc\\udcab\\udcabdef", "abc\\udcac\\udcabdef", "\\udcabdef"),
        ("x\\ud8ab\\udcab", "\\udcab", ""),
        ("\\udcab", "\\udcab", "\\udcab"),
    ],
)
def test_common_suffix(left: str, right: str, expected: str) -> None:
    assert Strings.common_suffix(_cs(left), _cs(right)) == _java_text(expected)


@pytest.mark.parametrize(
    ("value", "index", "expected"),
    [
        ("\\ud8ab\\udcab", 0, True),
        ("abc\\ud8ab\\udcab", 3, True),
        ("abc\\ud8ab\\udcabxyz", 3, True),
        ("\\ud8ab\\ud8ab", 0, False),
        ("\\udcab\\udcab", 0, False),
        ("\\ud8ab\\udcab", -1, False),
        ("\\ud8ab\\udcab", 1, False),
        ("\\ud8ab\\udcab", -2, False),
        ("\\ud8ab\\udcab", 2, False),
        ("x\\udcab", 0, False),
        ("\\ud8abx", 0, False),
    ],
)
def test_valid_surrogate_pair_at(value: str, index: int, expected: bool) -> None:
    assert Strings.valid_surrogate_pair_at(_java_text(value), index) is expected


@pytest.mark.parametrize(
    ("template", "args", "expected"),
    [
        ("%s", (), "%s"),
        ("%s", (5,), "5"),
        ("foo", (5,), "foo [5]"),
        ("foo", (5, 6, 7), "foo [5, 6, 7]"),
        ("%s %s %s", ("%s", 1, 2), "%s 1 2"),
        ("", (5, 6), " [5, 6]"),
        ("%s%s%s", (1, 2, 3), "123"),
        ("%s%s%s", (1,), "1%s%s"),
        ("%s + 6 = 11", (5,), "5 + 6 = 11"),
        ("5 + %s = 11", (6,), "5 + 6 = 11"),
        ("5 + 6 = %s", (11,), "5 + 6 = 11"),
        ("%s + %s = %s", (5, 6, 11), "5 + 6 = 11"),
        ("%s", (None, None, None), "null [null, null]"),
        (None, (5, 6), "null [5, 6]"),
        ("%s", (None,), "null"),
    ],
)
def test_lenient_format(template: str | None, args: tuple[object, ...], expected: str) -> None:
    assert Strings.lenient_format(template, *args) == expected


def test_excluded_upstream_helper_surfaces_are_documented() -> None:
    doc = (
        Path(__file__).parent.parent.parent / "docs" / "CASE_STUDY_GUAVA_BASE_STRINGS.md"
    ).read_text(encoding="utf-8")
    for phrase in ("badArgumentToString", "null `Object[]` varargs", "NullPointerTester"):
        assert phrase in doc


def test_translation_metrics_record_rule_only_surface() -> None:
    assert set(_NS.metrics) == {"Strings"}
    metric = _NS.metrics["Strings"]
    assert metric.coverage == 1.0
    assert metric.todos == 0
    assert metric.confidence == 0.99


def test_external_stubs_are_separate_from_residual_patches() -> None:
    assert _NS.external_stubs == ("Character", "Logger", "Platform")


def test_residual_gap_inventory() -> None:
    applied = set(_NS.applied_gaps)
    declared = {gap.gap_id for gap in _RESIDUAL_GAP_PATCHES}
    assert applied == declared == set()

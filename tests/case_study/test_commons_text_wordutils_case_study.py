"""Apache Commons Text WordUtils expansion for issue #657.

The assertions below are a focused pytest port of non-regex upstream ``WordUtilsTest``
cases from Apache Commons Text (commit ``af9cca8``, post-1.15.0). They run against the
rule-layer translation linked by ``tests/case_study/commons_text_caseutils_harness.py``.

Regex-heavy ``containsAllWords`` and ``wrap`` cases are intentionally excluded from this
first expansion; the residual inventory and case-study doc keep those boundaries explicit.
"""

from __future__ import annotations

import pytest

from tests.case_study.commons_text_caseutils_harness import (
    _WORDUTILS_RESIDUAL_GAP_PATCHES,
    link_commons_text_wordutils_namespace,
)

_NS = link_commons_text_wordutils_namespace()
WordUtils = _NS.WordUtils


@pytest.mark.parametrize(
    ("text", "lower", "upper", "append_to_end", "expected"),
    (
        ("012 3456789", 0, 5, None, "012"),
        ("01234 56789", 5, 10, "-", "01234-"),
        ("01 23 45 67 89", 9, -1, "abc", "01 23 45 67abc"),
        ("0123456789", 0, 5, "", "01234"),
        ("0123456789", 15, 20, None, "0123456789"),
    ),
)
def test_abbreviate(
    text: str,
    lower: int,
    upper: int,
    append_to_end: str | None,
    expected: str,
) -> None:
    assert WordUtils.abbreviate(text, lower, upper, append_to_end) == expected


@pytest.mark.parametrize(
    ("text", "capitalize_args", "expected"),
    (
        (None, (), None),
        ("", (), ""),
        ("  ", (), "  "),
        ("i am here 123", (), "I Am Here 123"),
        ("i am HERE 123", (), "I Am HERE 123"),
        ("i-am here+123", (["-", "+", " ", "@"],), "I-Am Here+123"),
        ("i aM.fine", (["."],), "I aM.Fine"),
        ("i am fine now", ([],), "I am fine now"),
    ),
)
def test_capitalize(
    text: str | None,
    capitalize_args: tuple[object, ...],
    expected: str | None,
) -> None:
    assert WordUtils.capitalize(text, *capitalize_args) == expected


@pytest.mark.parametrize(
    ("text", "capitalize_args", "expected"),
    (
        (None, (), None),
        ("", (), ""),
        ("  ", (), "  "),
        ("I AM HERE 123", (), "I Am Here 123"),
        ("HELI WORLD", (), "Heli World"),
        ("a\tb\nc d", (), "A\tB\nC D"),
        ("i-am here+123", (["-", "+", " ", "@"],), "I-Am Here+123"),
        ("i aM.fine", (["."],), "I am.Fine"),
        ("i am fine now", ([],), "I am fine now"),
    ),
)
def test_capitalize_fully(
    text: str | None,
    capitalize_args: tuple[object, ...],
    expected: str | None,
) -> None:
    assert WordUtils.capitalize_fully(text, *capitalize_args) == expected


@pytest.mark.parametrize(
    ("text", "initial_args", "expected"),
    (
        (None, (), None),
        ("", (), ""),
        ("  ", (), ""),
        ("I", (), "I"),
        ("Ben John Lee", (), "BJL"),
        ("   Ben \n   John\tLee\t", (), "BJL"),
        ("Ben J.Lee", (), "BJ"),
        (" Ben   John  . Lee", (), "BJ.L"),
        ("Ben John Lee", ([],), ""),
        ("Ben J.Lee", ([" ", "."],), "BJL"),
        ("Kay O'Murphy", ([" ", ".", "'"],), "KOM"),
    ),
)
def test_initials(
    text: str | None,
    initial_args: tuple[object, ...],
    expected: str | None,
) -> None:
    assert WordUtils.initials(text, *initial_args) == expected


def test_is_delimiter_char_and_code_point() -> None:
    assert not WordUtils.is_delimiter(".", None)
    assert WordUtils.is_delimiter(" ", None)
    assert not WordUtils.is_delimiter(" ", ["."])
    assert WordUtils.is_delimiter(".", ["."])
    assert not WordUtils.is_delimiter(ord(" "), ["."])
    assert WordUtils.is_delimiter(ord("."), [".", "_", "a"])


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (None, None),
        ("", ""),
        ("  ", "  "),
        ("I", "i"),
        ("i", "I"),
        ("i am here 123", "I AM HERE 123"),
        ("I Am Here 123", "i aM hERE 123"),
        ("i am HERE 123", "I AM here 123"),
        ("I AM HERE 123", "i am here 123"),
    ),
)
def test_swap_case(text: str | None, expected: str | None) -> None:
    assert WordUtils.swap_case(text) == expected


@pytest.mark.parametrize(
    ("text", "uncapitalize_args", "expected"),
    (
        (None, (), None),
        ("", (), ""),
        ("  ", (), "  "),
        ("I", (), "i"),
        ("I Am Here 123", (), "i am here 123"),
        ("i am HERE 123", (), "i am hERE 123"),
        ("A\tB\nC D", (), "a\tb\nc d"),
        ("I+Am Here-123", (["-", "+", " ", "@"],), "i+am here-123"),
        ("I AM.FINE", (["."],), "i AM.fINE"),
        ("I am fine now", ([],), "i am fine now"),
    ),
)
def test_uncapitalize(
    text: str | None,
    uncapitalize_args: tuple[object, ...],
    expected: str | None,
) -> None:
    assert WordUtils.uncapitalize(text, *uncapitalize_args) == expected


def test_wordutils_translation_metrics_record_rule_only_surface() -> None:
    assert set(_NS.metrics) == {"WordUtils"}
    metric = _NS.metrics["WordUtils"]
    assert metric.coverage == 1.0
    assert metric.todos == 0


def test_wordutils_external_stubs_are_separate_from_residual_patches() -> None:
    assert _NS.external_stubs == ("ArrayUtils", "Character", "StringUtils", "Strings", "Validate")


def test_wordutils_residual_gap_inventory() -> None:
    applied = set(_NS.applied_gaps)
    declared = {gap.gap_id for gap in _WORDUTILS_RESIDUAL_GAP_PATCHES}
    assert applied == declared
    assert declared == set()

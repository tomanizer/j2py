"""Apache Commons Text CaseUtils external case study (issue #657).

The assertions below are a focused pytest port of upstream ``CaseUtilsTest`` cases from
Apache Commons Text (commit ``af9cca8``, post-1.15.0). They run against the rule-layer
translation linked by ``tests/case_study/commons_text_caseutils_harness.py``.

Mapping notes for the port:

* Java ``char[]`` / varargs delimiters are passed as individual single-character Python
  ``str`` arguments; a Java ``null`` delimiter array (or an omitted varargs argument)
  maps to passing no delimiter arguments at all.
* Java ``char`` literals written as UTF-16 escapes are rewritten as the equivalent Python
  code-point literals (e.g. ``"𐌀"`` becomes ``"\U00010300"``).

One upstream assertion is intentionally excluded; see
``test_excluded_surrogate_delimiter_case_is_documented`` and CT-4 in
``docs/CASE_STUDY_COMMONS_TEXT_CASEUTILS.md``.
"""

from __future__ import annotations

import pytest

from tests.case_study.commons_text_caseutils_harness import (
    _RESIDUAL_GAP_PATCHES,
    link_commons_text_caseutils_namespace,
)

_NS = link_commons_text_caseutils_namespace()
CaseUtils = _NS.CaseUtils

# (str, capitalize_first_letter, delimiters, expected) ported from CaseUtilsTest.
_CASES: tuple[tuple[str | None, bool, tuple[str, ...], str | None], ...] = (
    (None, False, (), None),
    ("", True, (), ""),
    ("  ", False, (), ""),
    ("a  b  c  @def", False, (), "aBC@def"),
    ("a b c @def", True, (), "ABC@def"),
    ("a b c @def", True, ("-",), "ABC@def"),
    ("-+@ ", True, ("-", "+", " ", "@"), ""),
    ("   to-CAMEL-cASE", False, ("-", "+", " ", "@"), "toCamelCase"),
    ("@@@@   to+CAMEL@cASE ", True, ("-", "+", " ", "@"), "ToCamelCase"),
    ("To+CA+ME L@cASE", True, ("-", "+", " ", "@"), "ToCaMeLCase"),
    ("To.Camel.Case", False, (".",), "toCamelCase"),
    ("To.Camel-Case", False, ("-", "."), "toCamelCase"),
    (" to @ Camel case", False, ("-", "@"), "toCamelCase"),
    (" @to @ Camel case", True, ("-", "@"), "ToCamelCase"),
    ("TO CAMEL CASE", True, (), "ToCamelCase"),
    ("TO CAMEL CASE", False, (), "toCamelCase"),
    ("tocamelcase", False, (), "tocamelcase"),
    ("tocamelcase", True, (), "Tocamelcase"),
    ("Tocamelcase", False, (), "tocamelcase"),
    ("tocamelcase", True, (), "Tocamelcase"),
    ("tocamelcase", False, (), "tocamelcase"),
)


@pytest.mark.parametrize(("text", "capitalize_first", "delimiters", "expected"), _CASES)
def test_to_camel_case(
    text: str | None,
    capitalize_first: bool,
    delimiters: tuple[str, ...],
    expected: str | None,
) -> None:
    assert CaseUtils.to_camel_case(text, capitalize_first, *delimiters) == expected


def test_to_camel_case_supplementary_code_points() -> None:
    # Upstream uses UTF-16 surrogate-pair literals; these are the equivalent code points.
    # Default whitespace delimiter, so no surrogate-as-delimiter semantics are involved.
    assert CaseUtils.to_camel_case("\U00010300 \U00010302", True) == "\U00010300\U00010302"


def test_to_camel_case_locale_independent() -> None:
    # Python str.lower() is locale-independent, matching CaseUtils' use of Locale.ROOT:
    # 'I' must not become the Turkish dotless 'i'.
    assert CaseUtils.to_camel_case("TIP.TOP", True, ".") == "TipTop"
    assert CaseUtils.to_camel_case("TO CAMEL CASE", False) == "toCamelCase"


def test_constructor_is_instantiable() -> None:
    # Upstream testConstructor asserts a single public constructor via reflection; the
    # rule-layer port only needs the instance to be constructable.
    assert CaseUtils() is not None


def test_excluded_surrogate_delimiter_case_is_documented() -> None:
    # The upstream assertion
    #   toCamelCase("𐌀𐌁𐌔𐌂𐌃",
    #               true, '\uD800', '\uDF14')
    # passes two *lone surrogate* chars as delimiters. Java combines them in the char[]
    # into the supplementary code point U+10314; Python code-point semantics cannot model
    # a lone-surrogate delimiter array. This case is excluded from the oracle and tracked
    # as CT-4 in the case-study doc. This test asserts that exclusion stays explicit.
    excluded_source = "\\uD800\\uDF14"  # documented, not executed
    assert excluded_source not in {case[0] for case in _CASES}


def test_translation_metrics_record_rule_only_surface() -> None:
    assert set(_NS.metrics) == {"CaseUtils"}
    metric = _NS.metrics["CaseUtils"]
    assert metric.coverage == 1.0
    assert metric.todos == 0


def test_external_stubs_are_separate_from_residual_patches() -> None:
    assert _NS.external_stubs == ("ArrayUtils", "Character", "StringUtils")


def test_residual_gap_inventory() -> None:
    applied = set(_NS.applied_gaps)
    declared = {gap.gap_id for gap in _RESIDUAL_GAP_PATCHES}
    assert applied == declared
    # CT-1 (String(int[], offset, count) lowering) is fixed at the rule layer; CT-2/CT-3
    # remain until their JDK call lowerings land.
    assert declared == {"CT-2", "CT-3"}

"""Equivalence gate for the Guava-style arithmetic precedence regression.

Literal-oracle assertions exercise the Phase-1 exit criterion from
docs/EQUIVALENCE_TESTING.md: the gate must catch a translation that drops grouping from
``(a + b) * c`` to ``a + b * c``. The rule-layer parenthesis fix already landed, so this
test is expected to pass and guards against regression.
"""

from __future__ import annotations

import pytest

from tests.equivalence.harness import load_translated_module, translate_rule_layer

JAVA_CLASS = "GuavaPrecedenceMath.java"
surface = pytest.mark.equivalence_surface

pytestmark = pytest.mark.equivalence


@pytest.fixture(scope="module")
def guava_precedence_source() -> str:
    return translate_rule_layer(JAVA_CLASS)


@pytest.fixture(scope="module")
def guava_precedence_math(guava_precedence_source: str):
    module = load_translated_module(
        guava_precedence_source,
        "_GuavaPrecedenceMath",
    )
    return module.GuavaPrecedenceMath


def test_parenthesized_additive_operand_remains_grouped(
    guava_precedence_source: str,
) -> None:
    """Structural guard for the prior rule-layer fix."""
    assert "return (old_capacity + 1) * 2" in guava_precedence_source
    assert "return (left + right) * scale" in guava_precedence_source


@surface(JAVA_CLASS, "GuavaPrecedenceMath.expandedCapacity(int)")
def test_expanded_capacity_literal_oracles(guava_precedence_math) -> None:
    # A buggy ``old_capacity + 1 * 2`` translation would return 12 for the first case.
    assert guava_precedence_math.expanded_capacity(10) == 22
    assert guava_precedence_math.expanded_capacity(5) == 12


@surface(JAVA_CLASS, "GuavaPrecedenceMath.scaledSum(int,int,int)")
def test_scaled_sum_literal_oracles(guava_precedence_math) -> None:
    # A buggy ``left + right * scale`` translation would return 17 for the first case.
    assert guava_precedence_math.scaled_sum(5, 6, 2) == 22
    assert guava_precedence_math.scaled_sum(-4, 9, 3) == 15

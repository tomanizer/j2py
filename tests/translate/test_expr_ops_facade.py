"""Compatibility coverage for the legacy expr_ops import surface."""

from __future__ import annotations


def test_expr_ops_facade_preserves_direct_import_surface() -> None:
    from j2py.translate import expr_ops
    from j2py.translate.expr_assignments import (
        _desugar_embedded_assign,
        _translate_assignment_expression,
        _translate_update_expression,
    )
    from j2py.translate.expr_binary import _translate_binary_expression
    from j2py.translate.expr_conditionals import _translate_ternary_expression
    from j2py.translate.expr_switch import (
        _switch_condition,
        _switch_label_values,
        _translate_switch_expression,
    )
    from j2py.translate.expr_unary import _translate_unary_expression

    assert expr_ops._desugar_embedded_assign is _desugar_embedded_assign
    assert expr_ops._switch_condition is _switch_condition
    assert expr_ops._switch_label_values is _switch_label_values
    assert expr_ops._translate_assignment_expression is _translate_assignment_expression
    assert expr_ops._translate_binary_expression is _translate_binary_expression
    assert expr_ops._translate_switch_expression is _translate_switch_expression
    assert expr_ops._translate_ternary_expression is _translate_ternary_expression
    assert expr_ops._translate_unary_expression is _translate_unary_expression
    assert expr_ops._translate_update_expression is _translate_update_expression

"""Conditional expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_assignments import _ASSIGN_OR_UPDATE, _desugar_embedded_assign
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import ternary_expression_operands, unwrap_parens


def _translate_ternary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    operands = ternary_expression_operands(node)
    if operands is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed ternary expression")
        return f"__j2py_todo__({node.text!r})"
    condition_node, true_node, false_node = operands
    cond_inner = unwrap_parens(condition_node)
    if cond_inner.type in _ASSIGN_OR_UPDATE:
        condition = _desugar_embedded_assign(cond_inner, ctx)
    else:
        condition = translate_expression(condition_node, ctx)
    true_inner = unwrap_parens(true_node)
    if true_inner.type in _ASSIGN_OR_UPDATE:
        if_true = _desugar_embedded_assign(true_inner, ctx)
    else:
        if_true = translate_expression(true_node, ctx)
    false_inner = unwrap_parens(false_node)
    if false_inner.type in _ASSIGN_OR_UPDATE:
        if_false = _desugar_embedded_assign(false_inner, ctx)
    else:
        if_false = translate_expression(false_node, ctx)
    return f"{if_true} if {condition} else {if_false}"

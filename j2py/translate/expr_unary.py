"""Unary expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_assignments import _ASSIGN_OR_UPDATE, _desugar_embedded_assign
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import unwrap_parens


def _translate_unary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named_children = node.named_children
    if not children or not named_children:
        ctx.diagnostics.record(node, supported=False, reason="malformed unary expression")
        return f"__j2py_todo__({node.text!r})"

    operator = children[0].text
    operand_node = named_children[-1]
    operand = _translate_unary_operand(operand_node, ctx)
    if operator == "!":
        operand_inner = unwrap_parens(operand_node)
        if operand_inner.type in _ASSIGN_OR_UPDATE:
            expr = _desugar_embedded_assign(operand_inner, ctx)
            return f"not ({expr})"
        operand = _translate_unary_operand(operand_node, ctx)
        if operand.startswith("not "):
            return operand.removeprefix("not ")
        return f"not {operand}"
    if operator in {"+", "-", "~"}:
        return f"{operator}{operand}"

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported unary operator {operator}")
    return f"__j2py_todo__({node.text!r})"


def _translate_unary_operand(node: JavaNode, ctx: TranslationContext) -> str:
    operand = translate_expression(node, ctx)
    if _unary_operand_needs_parentheses(node):
        return f"({operand})"
    return operand


def _unary_operand_needs_parentheses(node: JavaNode) -> bool:
    while node.type == "parenthesized_expression" and len(node.named_children) == 1:
        node = node.named_children[0]
    return node.type in {"binary_expression", "switch_expression", "ternary_expression"}

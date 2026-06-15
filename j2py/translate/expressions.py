"""Expression facade and router for the rule-based skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.rules.literals import translate_literal, translate_string_literal
from j2py.translate.rules.naming import translate_class_name
from j2py.translate.rules.types import translate_type

__all__ = ["infer_expression_py_type", "translate_expression"]


def translate_expression(node: JavaNode | None, ctx: TranslationContext) -> str:
    result = _translate_expression(node, ctx)
    if result.startswith("__j2py_todo__("):
        ctx.diagnostics.imports.need_todo_sentinel()
    return result


def infer_expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    from j2py.translate.expr_types import infer_expression_py_type as impl

    return impl(node, ctx)


def _translate_expression(node: JavaNode | None, ctx: TranslationContext) -> str:
    if node is None:
        return "None"

    if node.type in {
        "decimal_integer_literal",
        "hex_integer_literal",
        "binary_integer_literal",
        "octal_integer_literal",
        "decimal_floating_point_literal",
        "true",
        "false",
        "null_literal",
        "character_literal",
    }:
        return translate_literal(node.text, ctx.cfg)

    if node.type == "string_literal":
        return translate_string_literal(node.text)

    if node.type == "identifier":
        from j2py.translate.expr_access import _translate_identifier

        return _translate_identifier(node.text, ctx)

    if node.type in {"type_identifier", "scoped_type_identifier"}:
        return translate_class_name(node.text)

    if node.type in {"boolean_type", "integral_type", "floating_point_type", "void_type"}:
        return translate_type(node.text, ctx.cfg)

    if node.type == "this":
        return "self"

    if node.type == "super":
        ctx.diagnostics.record(node, supported=True, reason="translated super expression")
        return "super()"

    if node.type == "field_access":
        from j2py.translate.expr_access import _translate_field_access

        return _translate_field_access(node, ctx)

    if node.type == "array_access":
        from j2py.translate.expr_access import _translate_array_access

        return _translate_array_access(node, ctx)

    if node.type == "array_initializer":
        from j2py.translate.expr_access import _translate_array_initializer

        return _translate_array_initializer(node, ctx)

    if node.type == "array_creation_expression":
        from j2py.translate.expr_access import _translate_array_creation

        return _translate_array_creation(node, ctx)

    if node.type == "class_literal":
        from j2py.translate.expr_access import _translate_class_literal

        return _translate_class_literal(node, ctx)

    if node.type == "cast_expression":
        from j2py.translate.expr_access import _translate_cast_expression

        return _translate_cast_expression(node, ctx)

    if node.type == "instanceof_expression":
        from j2py.translate.expr_access import _translate_instanceof_expression

        return _translate_instanceof_expression(node, ctx)

    if node.type == "assignment_expression":
        from j2py.translate.expr_ops import _translate_assignment_expression

        return _translate_assignment_expression(node, ctx)

    if node.type == "update_expression":
        from j2py.translate.expr_ops import _translate_update_expression

        return _translate_update_expression(node, ctx)

    if node.type == "method_invocation":
        from j2py.translate.expr_calls import _translate_method_invocation

        return _translate_method_invocation(node, ctx)

    if node.type == "lambda_expression":
        from j2py.translate.expr_lambdas import _translate_lambda_expression

        return _translate_lambda_expression(node, ctx)

    if node.type == "method_reference":
        from j2py.translate.expr_lambdas import _translate_method_reference

        return _translate_method_reference(node, ctx)

    if node.type == "argument_list":
        return ", ".join(
            translate_expression(child, ctx)
            for child in node.named_children
            if not is_comment(child)
        )

    if node.type == "object_creation_expression":
        from j2py.translate.expr_objects import _translate_object_creation

        return _translate_object_creation(node, ctx)

    if node.type == "parenthesized_expression":
        named_children = node.named_children
        if len(named_children) == 1:
            return translate_expression(named_children[0], ctx)

    if node.type == "unary_expression":
        from j2py.translate.expr_ops import _translate_unary_expression

        return _translate_unary_expression(node, ctx)

    if node.type == "ternary_expression":
        from j2py.translate.expr_ops import _translate_ternary_expression

        return _translate_ternary_expression(node, ctx)

    if node.type == "switch_expression":
        from j2py.translate.expr_ops import _translate_switch_expression

        return _translate_switch_expression(node, ctx)

    if node.type == "binary_expression":
        from j2py.translate.expr_ops import _translate_binary_expression

        return _translate_binary_expression(node, ctx)

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported expression {node.type}")
    return f"__j2py_todo__({node.text!r})"

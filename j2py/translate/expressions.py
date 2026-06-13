"""Expression emission for the rule-based skeleton translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import PatternBinding, TranslationContext
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.literals import (
    translate_literal,
    translate_string_literal,
)
from j2py.translate.rules.naming import (
    translate_attribute_method_name,
    translate_class_name,
    translate_field_name,
    translate_method_name,
)
from j2py.translate.rules.types import (
    is_api_get_receiver_type,
    is_map_like_type,
    java_default_value,
    translate_type,
)

if TYPE_CHECKING:
    pass


def translate_expression(node: JavaNode | None, ctx: TranslationContext) -> str:
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
        return _translate_field_access(node, ctx)

    if node.type == "array_access":
        return _translate_array_access(node, ctx)

    if node.type == "array_initializer":
        return _translate_array_initializer(node, ctx)

    if node.type == "array_creation_expression":
        return _translate_array_creation(node, ctx)

    if node.type == "class_literal":
        return _translate_class_literal(node, ctx)

    if node.type == "cast_expression":
        return _translate_cast_expression(node, ctx)

    if node.type == "instanceof_expression":
        return _translate_instanceof_expression(node, ctx)

    if node.type == "assignment_expression":
        children = node.children
        if len(children) >= 3:
            left_node = children[0]
            operator = children[1].text
            right_node = children[-1]
            supported_operators = {
                "=",
                "+=",
                "-=",
                "*=",
                "/=",
                "%=",
                "&=",
                "|=",
                "^=",
                "<<=",
                ">>=",
                ">>>=",
            }
            if operator not in supported_operators:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=f"unsupported assignment operator {operator}",
                )
                return f"__j2py_todo__({node.text!r})"
            if operator == ">>>=":
                left = translate_expression(left_node, ctx)
                shifted = _translate_unsigned_right_shift(node, left_node, right_node, ctx)
                return f"{left} = {shifted}"
            left = translate_expression(left_node, ctx)
            right = translate_expression(right_node, ctx)
            return f"{left} {operator} {right}"

    if node.type == "update_expression":
        return _translate_update_expression(node, ctx)

    if node.type == "method_invocation":
        return _translate_method_invocation(node, ctx)

    if node.type == "lambda_expression":
        return _translate_lambda_expression(node, ctx)

    if node.type == "method_reference":
        return _translate_method_reference(node, ctx)

    if node.type == "argument_list":
        return ", ".join(
            translate_expression(child, ctx)
            for child in node.named_children
            if not is_comment(child)
        )

    if node.type == "object_creation_expression":
        return _translate_object_creation(node, ctx)

    if node.type == "parenthesized_expression":
        named_children = node.named_children
        if len(named_children) == 1:
            return translate_expression(named_children[0], ctx)

    if node.type == "unary_expression":
        return _translate_unary_expression(node, ctx)

    if node.type == "ternary_expression":
        return _translate_ternary_expression(node, ctx)

    if node.type == "switch_expression":
        return _translate_switch_expression(node, ctx)

    if node.type == "binary_expression":
        f_string = _translate_string_concat(node, ctx)
        if f_string is not None:
            return f_string
        children = node.children
        if len(children) >= 3:
            operator_text = children[1].text
            if operator_text == "/":
                return _translate_division(node, children[0], children[2], ctx)
            if operator_text == ">>>":
                return _translate_unsigned_right_shift(node, children[0], children[2], ctx)
            binary_operator: str | None
            binary_operator = _translate_binary_operator(operator_text)
            if binary_operator is None:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=f"unsupported binary operator {children[1].text}",
                )
                return f"__j2py_todo__({node.text!r})"
            null_comparison = _translate_null_comparison(
                children[0],
                children[2],
                binary_operator,
                ctx,
            )
            if null_comparison is not None:
                return null_comparison
            return (
                f"{translate_expression(children[0], ctx)} "
                f"{binary_operator} "
                f"{translate_expression(children[2], ctx)}"
            )

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported expression {node.type}")
    return f"__j2py_todo__({node.text!r})"


def _translate_identifier(raw_name: str, ctx: TranslationContext) -> str:
    if raw_name in ctx.expression_aliases:
        return ctx.expression_aliases[raw_name]
    py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
    if (
        ctx.in_instance_method
        and raw_name in ctx.class_fields
        and raw_name not in ctx.param_names
        and raw_name not in ctx.local_names
    ):
        return f"self.{py_name}"
    return py_name


def _translate_field_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed field access")
        return node.text

    target = translate_expression(children[0], ctx)
    field_name = translate_field_name(
        children[-1].text,
        snake_case=ctx.cfg.snake_case_fields,
    )
    if children[-1].text == "length":
        return f"len({target})"
    return f"{target}.{field_name}"


def _translate_array_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) != 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed array access")
        return f"__j2py_todo__({node.text!r})"
    return f"{translate_expression(children[0], ctx)}[{translate_expression(children[1], ctx)}]"


def _translate_array_initializer(node: JavaNode, ctx: TranslationContext) -> str:
    return f"[{', '.join(translate_expression(child, ctx) for child in node.named_children)}]"


def _translate_array_creation(node: JavaNode, ctx: TranslationContext) -> str:
    initializer = first_child_by_type(node, "array_initializer")
    if initializer is not None:
        return translate_expression(initializer, ctx)
    dimensions = [child for child in node.named_children if child.type == "dimensions_expr"]
    if len(dimensions) == 1 and dimensions[0].named_children:
        type_node = next(
            (child for child in node.named_children if child.type != "dimensions_expr"),
            None,
        )
        default = java_default_value(type_node.text if type_node is not None else "Object")
        size = translate_expression(dimensions[0].named_children[0], ctx)
        return f"[{default}] * {size}"
    if len(dimensions) > 1:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="multidimensional array creation requires nested allocation handling",
        )
        return f"__j2py_todo__({node.text!r})"
    ctx.diagnostics.record(
        node,
        supported=False,
        reason="array creation without initializer requires size handling",
    )
    return f"__j2py_todo__({node.text!r})"


def _translate_class_literal(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if not children:
        ctx.diagnostics.record(node, supported=False, reason="malformed class literal")
        return f"__j2py_todo__({node.text!r})"
    return translate_expression(children[0], ctx)


def _translate_cast_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed cast expression")
        return f"__j2py_todo__({node.text!r})"
    ctx.diagnostics.record(node, supported=True, reason="translated cast expression")
    ctx.diagnostics.warn(node, reason="dropped Java cast; verify runtime type")
    return translate_expression(children[-1], ctx)


def _translate_instanceof_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed instanceof expression")
        return f"__j2py_todo__({node.text!r})"

    expression_node = children[0]
    type_node = children[1]
    expression = translate_expression(expression_node, ctx)
    runtime_type = _runtime_type_expression(type_node, ctx)
    if runtime_type is None:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason=f"unsupported instanceof type {type_node.text}",
        )
        return f"__j2py_todo__({node.text!r})"

    if len(children) >= 3 and children[2].type == "identifier":
        raw_name = children[2].text
        py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
        ctx.pattern_bindings.append(
            PatternBinding(
                raw_name=raw_name,
                py_name=py_name,
                py_type=translate_type(type_node.text, ctx.cfg),
                source=expression,
            ),
        )

    ctx.diagnostics.record(node, supported=True, reason="translated instanceof expression")
    return f"isinstance({expression}, {runtime_type})"


def _runtime_type_expression(type_node: JavaNode, ctx: TranslationContext) -> str | None:
    raw_type = type_node.text.strip()
    raw_type = raw_type.split("<", 1)[0]
    while raw_type.endswith("[]"):
        raw_type = raw_type[:-2]

    mapped = ctx.cfg.collection_map.get(raw_type) or ctx.cfg.type_map.get(raw_type)
    if mapped is not None:
        return mapped.split("[", 1)[0]
    if raw_type in {"byte", "short", "int", "long"}:
        return "int"
    if raw_type in {"float", "double"}:
        return "float"
    if raw_type == "boolean":
        return "bool"
    if not raw_type:
        return None
    return translate_class_name(raw_type)


def _translate_method_invocation(node: JavaNode, ctx: TranslationContext) -> str:
    stream_pipeline = _translate_stream_pipeline(node, ctx)
    if stream_pipeline is not None:
        return stream_pipeline

    args_node = first_child_by_type(node, "argument_list")
    args = translate_expression(args_node, ctx) if args_node is not None else ""

    named = node.named_children
    if args_node is None or len(named) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed method invocation")
        return f"__j2py_todo__({node.text!r})"

    args_index = named.index(args_node)
    method_node = named[args_index - 1]
    method_name = method_node.text
    receiver_nodes = named[: args_index - 1]
    raw_receiver = receiver_nodes[0].text if receiver_nodes else ""
    receiver = translate_expression(receiver_nodes[0], ctx) if receiver_nodes else ""

    if raw_receiver == "System.out" and method_name == "println":
        return f"print({args})"

    if method_name == "add" and receiver:
        return f"{receiver}.append({args})"

    if method_name in {"size", "length"} and receiver and not args:
        return f"len({receiver})"

    if method_name == "isEmpty" and receiver and not args:
        return f"not {receiver}"

    if method_name == "contains" and receiver and args:
        return f"{args} in {receiver}"

    if method_name == "toArray" and receiver:
        return f"list({receiver})"

    if method_name == "get" and receiver and args:
        receiver_type = _expression_py_type(receiver_nodes[0], ctx) if receiver_nodes else None
        if receiver_type is not None and _is_list_type(receiver_type):
            return f"{receiver}[{args}]"
        if receiver_type is not None and is_map_like_type(receiver_type):
            return f"{receiver}.get({args})"
        if receiver_type is not None and is_api_get_receiver_type(receiver_type):
            return f"{receiver}.get({args})"
        if raw_receiver.split(".")[-1][:1].isupper():
            return f"{receiver}.get({args})"
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="ambiguous get invocation requires receiver collection type",
        )
        return f"{receiver}.get({args})"

    if method_name == "equals" and receiver and args:
        arg_nodes = list(args_node.named_children) if args_node is not None else []
        if len(arg_nodes) != 1:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="equals invocation with unexpected argument count",
            )
            return f"__j2py_todo__({node.text!r})"
        if arg_nodes[0].type == "null_literal":
            return f"{receiver} is None"
        return f"{receiver} == {args}"

    if method_name == "equalsIgnoreCase" and receiver and args:
        arg_nodes = list(args_node.named_children) if args_node is not None else []
        if len(arg_nodes) == 1:
            return f"{receiver}.lower() == {args}.lower()"

    if method_name == "toString" and receiver and not args:
        return f"str({receiver})"

    if method_name == "hashCode" and receiver and not args:
        return f"hash({receiver})"

    if method_name == "startsWith" and receiver and args:
        return f"{receiver}.startswith({args})"

    if method_name == "endsWith" and receiver and args:
        return f"{receiver}.endswith({args})"

    if method_name == "trim" and receiver and not args:
        return f"{receiver}.strip()"

    if method_name == "toLowerCase" and receiver and not args:
        return f"{receiver}.lower()"

    if method_name == "toUpperCase" and receiver and not args:
        return f"{receiver}.upper()"

    if method_name == "compareTo" and receiver and args:
        return f"({receiver} > {args}) - ({receiver} < {args})"

    if receiver in {"self", ""}:
        py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
        if not receiver and method_name in ctx.self_dispatch_methods and ctx.in_instance_method:
            return f"self.{py_method}({args})"
    else:
        py_method = translate_attribute_method_name(
            method_name,
            snake_case=ctx.cfg.snake_case_methods,
        )
    if receiver:
        return f"{receiver}.{py_method}({args})"
    if ctx.in_instance_method and py_method in ctx.class_methods:
        return f"self.{py_method}({args})"
    return f"{py_method}({args})"



def _translate_stream_pipeline(node: JavaNode, ctx: TranslationContext) -> str | None:
    from j2py.translate.expr_streams import _translate_stream_pipeline as impl

    return impl(node, ctx)


def _stream_item_name(source: str, ctx: TranslationContext) -> str:
    from j2py.translate.expr_streams import _stream_item_name as impl

    return impl(source, ctx)


def _translate_lambda_expression(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_lambdas import _translate_lambda_expression as impl

    return impl(node, ctx)


def _translate_method_reference(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_lambdas import _translate_method_reference as impl

    return impl(node, ctx)


def _translate_object_creation(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_objects import _translate_object_creation as impl

    return impl(node, ctx)


def _translate_unary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_ops import _translate_unary_expression as impl

    return impl(node, ctx)


def _translate_update_expression(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_ops import _translate_update_expression as impl

    return impl(node, ctx)


def _translate_ternary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_ops import _translate_ternary_expression as impl

    return impl(node, ctx)


def _translate_switch_expression(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_ops import _translate_switch_expression as impl

    return impl(node, ctx)


def _translate_binary_operator(operator: str) -> str | None:
    from j2py.translate.expr_ops import _translate_binary_operator as impl

    return impl(operator)


def _translate_division(
    node: JavaNode,
    left_node: JavaNode,
    right_node: JavaNode,
    ctx: TranslationContext,
) -> str:
    from j2py.translate.expr_ops import _translate_division as impl

    return impl(node, left_node, right_node, ctx)


def _translate_unsigned_right_shift(
    node: JavaNode,
    left_node: JavaNode,
    right_node: JavaNode,
    ctx: TranslationContext,
) -> str:
    from j2py.translate.expr_ops import _translate_unsigned_right_shift as impl

    return impl(node, left_node, right_node, ctx)


def _translate_null_comparison(
    left_node: JavaNode,
    right_node: JavaNode,
    operator: str,
    ctx: TranslationContext,
) -> str | None:
    from j2py.translate.expr_ops import _translate_null_comparison as impl

    return impl(left_node, right_node, operator, ctx)


def _translate_string_concat(node: JavaNode, ctx: TranslationContext) -> str | None:
    from j2py.translate.expr_ops import _translate_string_concat as impl

    return impl(node, ctx)


def _expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    from j2py.translate.expr_types import _expression_py_type as impl

    return impl(node, ctx)


def infer_expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    from j2py.translate.expr_types import infer_expression_py_type as impl

    return impl(node, ctx)


def _is_list_type(py_type: str) -> bool:
    from j2py.translate.expr_types import _is_list_type as impl

    return impl(py_type)

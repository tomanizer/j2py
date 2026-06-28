"""Best-effort Python type inference for expression translation."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.java_types import java_type_of_value, jdk_static_integral_field_type
from j2py.translate.node_utils import first_child_by_type, ternary_expression_operands
from j2py.translate.rules.types import (
    LIST_RETURNING_METHOD_NAMES,
    MAP_RETURNING_METHOD_NAMES,
    NULL_PASS_THROUGH_METHOD_NAMES,
    element_type_from_container,
    element_type_from_java_container,
    is_list_like_java_type,
    is_list_like_type,
    is_map_like_type,
    return_type_from_function,
    static_factory_return_type,
    translate_type,
    type_simple_name,
)


def _expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    return infer_expression_py_type(node, ctx)


def infer_expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    """Best-effort static type for a Java expression node."""
    if node.type == "decimal_integer_literal":
        return "int"
    if node.type in {"decimal_floating_point_literal", "floating_point_type"}:
        return "float"
    if node.type == "integer_type" and node.text in {"int", "long", "byte", "short"}:
        return "int"
    if node.type == "string_literal":
        return "str"
    if node.type == "character_literal":
        return "str"
    if node.type == "true" or node.type == "false":
        return "bool"
    if node.type == "null_literal":
        return "None"
    if node.type == "identifier":
        if node.text in ctx.class_field_types:
            return ctx.class_field_types[node.text]
        if (
            ctx.outer_self_alias
            and node.text in ctx.enclosing_class_field_types
            and node.text not in ctx.class_field_types
        ):
            return ctx.enclosing_class_field_types[node.text]
        return ctx.variable_types.get(node.text) or ctx.class_field_types.get(node.text)
    if node.type == "field_access":
        return _field_access_py_type(node, ctx)
    if node.type == "parenthesized_expression" and len(node.named_children) == 1:
        return infer_expression_py_type(node.named_children[0], ctx)
    if node.type == "cast_expression":
        cast_type_node = node.named_children[0] if node.named_children else None
        if cast_type_node is not None:
            return translate_type(cast_type_node.text, ctx.cfg)
    if node.type == "object_creation_expression":
        type_node = node.child_by_field("type")
        if type_node is not None:
            return translate_type(type_node.text, ctx.cfg)
    if node.type == "method_invocation":
        return _infer_method_invocation_py_type(node, ctx)
    if node.type == "ternary_expression":
        operands = ternary_expression_operands(node)
        if operands is not None:
            _, consequence, alternative = operands
            consequent_type = infer_expression_py_type(consequence, ctx)
            alternate_type = infer_expression_py_type(alternative, ctx)
            if consequent_type == "float" or alternate_type == "float":
                return "float"
            return consequent_type or alternate_type
    if node.type == "binary_expression" and len(node.children) == 3:
        operator = node.children[1].text
        left_type = infer_expression_py_type(node.children[0], ctx)
        right_type = infer_expression_py_type(node.children[2], ctx)
        if operator == "+" and (left_type == "str" or right_type == "str"):
            return "str"
        if operator in _INTEGRAL_BINARY_OPERATORS and left_type == "int" and right_type == "int":
            return "int"
        if operator in _NUMERIC_BINARY_OPERATORS and (
            left_type in {"int", "float"} and right_type in {"int", "float"}
        ):
            return "float" if "float" in {left_type, right_type} else "int"
    return None


_INTEGRAL_BINARY_OPERATORS = {"&", "|", "^", "<<", ">>", ">>>"}
_NUMERIC_BINARY_OPERATORS = {"+", "-", "*", "/", "%"}


def _field_access_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    children = node.named_children
    if len(children) != 2:
        return None
    object_node, field_name_node = children[0], children[1]
    field_name = field_name_node.text

    if field_name == "length":
        return "int"

    if jdk_static_integral_field_type(object_node.text, field_name) is not None:
        return "int"

    if object_node.type == "this":
        return ctx.class_field_types.get(field_name)

    object_type = infer_expression_py_type(object_node, ctx)
    if object_type is None:
        return None

    simple = type_simple_name(object_type)
    type_fields = ctx.declared_type_fields.get(simple)
    if type_fields is None:
        for type_name, fields in ctx.declared_type_fields.items():
            if simple == type_name or object_type.endswith(f".{type_name}"):
                type_fields = fields
                break
    if type_fields is None:
        return None
    return type_fields.get(field_name)


def _is_this_receiver(node: JavaNode) -> bool:
    if node.type == "this":
        return True
    if node.type == "field_access":
        children = node.named_children
        return len(children) == 2 and children[1].type == "this"
    return False


def _infer_method_invocation_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    named = [child for child in node.named_children if not is_comment(child)]
    args_node = first_child_by_type(node, "argument_list")
    if args_node is None or args_node not in named:
        return None
    args_index = named.index(args_node)
    method_name = named[args_index - 1].text
    receiver_nodes = named[: args_index - 1]
    arg_nodes = list(args_node.named_children)

    if not receiver_nodes and method_name in ctx.class_method_return_types:
        return ctx.class_method_return_types[method_name]

    if method_name in NULL_PASS_THROUGH_METHOD_NAMES and arg_nodes:
        return infer_expression_py_type(arg_nodes[0], ctx)

    if method_name in LIST_RETURNING_METHOD_NAMES:
        return "list"

    if method_name in MAP_RETURNING_METHOD_NAMES:
        return "dict"

    if receiver_nodes:
        receiver_type = infer_expression_py_type(receiver_nodes[0], ctx)
        declared_return_type = _declared_type_method_return_type(
            receiver_type,
            method_name,
            ctx,
        )
        if declared_return_type is not None:
            return declared_return_type
        configured_return = _configured_member_return_type(
            receiver_nodes[0].text,
            method_name,
            ctx,
        )
        if configured_return is not None:
            return configured_return
        factory_return = static_factory_return_type(receiver_nodes[0].text, method_name)
        if factory_return is not None:
            return factory_return

    if method_name == "apply" and receiver_nodes:
        receiver_type = infer_expression_py_type(receiver_nodes[0], ctx)
        if receiver_type is not None:
            function_return = return_type_from_function(receiver_type)
            if function_return is not None:
                return function_return

    int_return_methods = {
        "size",
        "length",
        "sum",
        "intValue",
        "longValue",
        "hashCode",
        "ordinal",
        "compare",
        "compareTo",
        "indexOf",
        "lastIndexOf",
    }
    str_return_methods = {
        "trim",
        "strip",
        "toLowerCase",
        "toUpperCase",
        "toString",
        "substring",
        "formatted",
        "charAt",
    }
    if method_name in int_return_methods:
        return "int"
    if method_name in str_return_methods:
        return "str"
    if method_name == "isEmpty":
        return "bool"
    if method_name in {"get", "getOrDefault"} and receiver_nodes:
        receiver_type = infer_expression_py_type(receiver_nodes[0], ctx)
        if receiver_type is not None and is_map_like_type(receiver_type):
            return element_type_from_container(receiver_type) or "object"
        if receiver_type is not None and is_list_like_type(receiver_type):
            return element_type_from_container(receiver_type) or "object"
        java_receiver_type = java_type_of_value(receiver_nodes[0], ctx)
        if java_receiver_type is not None and is_list_like_java_type(java_receiver_type):
            return element_type_from_java_container(java_receiver_type, ctx.cfg) or "object"
    return None


def _configured_member_return_type(
    receiver: str,
    method_name: str,
    ctx: TranslationContext,
) -> str | None:
    from j2py.translate.member_resolution import configured_member_binding_for_receiver

    binding = configured_member_binding_for_receiver(receiver, method_name, ctx)
    if binding is None:
        return None
    if binding.return_type:
        return translate_type(binding.return_type, ctx.cfg)
    if binding.return_shape:
        shape = binding.return_shape
        if ":" in shape:
            _, _, shape = shape.partition(":")
        simple = shape.split("->", 1)[0].split("[", 1)[0]
        return translate_type(simple or shape, ctx.cfg)
    return None


def _declared_type_method_return_type(
    receiver_type: str | None,
    method_name: str,
    ctx: TranslationContext,
) -> str | None:
    if receiver_type is None:
        return None
    candidates = (
        part.strip() for part in receiver_type.split("|") if part.strip() and part.strip() != "None"
    )
    for candidate in candidates:
        simple = type_simple_name(candidate)
        type_methods = ctx.declared_type_method_return_types.get(simple)
        if type_methods is None:
            for type_name, methods in ctx.declared_type_method_return_types.items():
                if simple == type_name or candidate.endswith(f".{type_name}"):
                    type_methods = methods
                    break
        if type_methods is None:
            continue
        return type_methods.get(method_name)
    return None


def _is_list_type(py_type: str) -> bool:
    return is_list_like_type(py_type)

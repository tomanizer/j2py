"""Best-effort Python type inference for expression translation."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.types import (
    LIST_RETURNING_METHOD_NAMES,
    MAP_RETURNING_METHOD_NAMES,
    NULL_PASS_THROUGH_METHOD_NAMES,
    element_type_from_container,
    is_list_like_type,
    is_map_like_type,
    return_type_from_function,
    translate_type,
    type_simple_name,
)


def _expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    return infer_expression_py_type(node, ctx)


def _java_type_of_value(node: JavaNode, ctx: TranslationContext) -> str | None:
    """Return the Java type string for simple identifier/field expressions, or None."""
    if node.type == "identifier":
        return ctx.variable_java_types.get(node.text) or ctx.class_field_java_types.get(node.text)
    if node.type == "field_access" and len(node.named_children) == 2:
        obj, field = node.named_children
        if obj.type == "this":
            return ctx.class_field_java_types.get(field.text)
    return None


def _is_integral_java_type(java_type: str | None) -> bool:
    if java_type is None:
        return False
    simple = java_type.strip()
    if "<" in simple:
        simple = simple.split("<", 1)[0]
    if "." in simple:
        simple = simple.rsplit(".", 1)[-1]
    simple = simple.rstrip("[]")
    return simple in {
        "Byte",
        "Character",
        "Integer",
        "Long",
        "Short",
        "byte",
        "char",
        "int",
        "long",
        "short",
    }


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
        children = node.named_children
        if len(children) >= 3:
            consequent_type = infer_expression_py_type(children[1], ctx)
            alternate_type = infer_expression_py_type(children[2], ctx)
            if consequent_type == "float" or alternate_type == "float":
                return "float"
            return consequent_type or alternate_type
    if node.type == "binary_expression" and len(node.children) == 3:
        operator = node.children[1].text
        if operator == "+":
            left_type = infer_expression_py_type(node.children[0], ctx)
            right_type = infer_expression_py_type(node.children[2], ctx)
            if left_type == "str" or right_type == "str":
                return "str"
    return None


def _field_access_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    children = node.named_children
    if len(children) != 2:
        return None
    object_node, field_name_node = children[0], children[1]
    field_name = field_name_node.text

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
    return None


def _is_list_type(py_type: str) -> bool:
    return is_list_like_type(py_type)

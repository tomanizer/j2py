"""Shared Java type lookup helpers used by expression lowering."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext

INTEGRAL_JAVA_TYPES: frozenset[str] = frozenset(
    {
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
    },
)


def java_type_of_value(node: JavaNode, ctx: TranslationContext) -> str | None:
    """Return the Java type string for simple identifier/this-field expressions."""
    if node.type == "identifier":
        if node.text in ctx.variable_java_types:
            return ctx.variable_java_types[node.text]
        if node.text in ctx.class_field_java_types:
            return ctx.class_field_java_types[node.text]
        if (
            ctx.outer_self_alias
            and node.text in ctx.enclosing_class_field_java_types
            and node.text not in ctx.class_field_java_types
        ):
            return ctx.enclosing_class_field_java_types[node.text]
        return None
    if node.type == "field_access" and len(node.named_children) == 2:
        obj, field = node.named_children
        if obj.type == "this":
            return ctx.class_field_java_types.get(field.text)
    return None


def is_integral_java_type(java_type: str | None) -> bool:
    if java_type is None:
        return False
    return java_type_simple_name(java_type) in INTEGRAL_JAVA_TYPES


def java_integral_width(node: JavaNode, ctx: TranslationContext) -> int | None:
    java_type = java_expression_type(node, ctx)
    if java_type is None:
        return None
    return java_type_width(java_type)


def java_expression_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    if node.type in {
        "decimal_integer_literal",
        "hex_integer_literal",
        "octal_integer_literal",
        "binary_integer_literal",
    }:
        return "long" if node.text.lower().endswith("l") else "int"
    if node.type == "decimal_floating_point_literal":
        return "float" if node.text.lower().endswith("f") else "double"
    if node.type == "string_literal":
        return "String"
    if node.type == "character_literal":
        return "char"
    if node.type in {"true", "false"}:
        return "boolean"
    if node.type == "identifier":
        if node.text in ctx.variable_java_types:
            return ctx.variable_java_types[node.text]
        if node.text in ctx.class_field_java_types:
            return ctx.class_field_java_types[node.text]
        if (
            ctx.outer_self_alias
            and node.text in ctx.enclosing_class_field_java_types
            and node.text not in ctx.class_field_java_types
        ):
            return ctx.enclosing_class_field_java_types[node.text]
        return None
    if node.type == "field_access":
        return field_access_java_type(node, ctx)
    if node.type == "array_access" and node.named_children:
        array_java_type = java_expression_type(node.named_children[0], ctx)
        if array_java_type is None:
            return None
        return java_type_strip_one_array_dimension(array_java_type)
    if node.type == "parenthesized_expression" and len(node.named_children) == 1:
        return java_expression_type(node.named_children[0], ctx)
    if node.type == "cast_expression" and node.named_children:
        return node.named_children[0].text
    if node.type == "object_creation_expression":
        type_node = node.child_by_field("type")
        if type_node is not None:
            return type_node.text
    if node.type == "method_invocation":
        char_at_type = method_invocation_java_type(node)
        if char_at_type is not None:
            return char_at_type
        return _method_invocation_java_return_type(node, ctx)
    return None


def _method_invocation_java_return_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    from j2py.translate.node_utils import first_child_by_type
    from j2py.translate.rules.types import (
        is_list_like_java_type,
        java_element_type_from_java_container,
    )

    args_node = first_child_by_type(node, "argument_list")
    named = node.named_children
    if args_node is None or args_node not in named:
        return None
    args_index = named.index(args_node)
    method_name = named[args_index - 1].text
    receiver_nodes = named[: args_index - 1]
    if method_name != "get" or not receiver_nodes:
        return None
    java_receiver_type = java_expression_type(receiver_nodes[0], ctx)
    if java_receiver_type is None:
        return None
    if is_list_like_java_type(java_receiver_type):
        return java_element_type_from_java_container(java_receiver_type) or java_receiver_type
    return None


def method_invocation_java_type(node: JavaNode) -> str | None:
    """Java return type for the JDK call patterns the rule layer lowers structurally.

    ``String``/``CharSequence#charAt(int)`` returns a Java ``char``; the rule layer
    lowers single-argument ``charAt`` to Python indexing (a 1-char ``str``), so the
    char model must agree here or a ``char == 'x'`` comparison wraps only the literal
    in ``ord()`` and silently compares ``str`` to ``int``.
    """
    name_node = node.child_by_field("name")
    if name_node is None or name_node.text != "charAt":
        return None
    arguments = node.child_by_field("arguments")
    if arguments is None:
        return None
    args = [c for c in arguments.named_children if c.type not in ("line_comment", "block_comment")]
    if len(args) != 1:
        return None
    return "char"


def java_type_strip_one_array_dimension(java_type: str) -> str | None:
    stripped = java_type.strip()
    if stripped.endswith("[]"):
        return stripped[:-2].strip()
    return None


def field_access_java_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    children = node.named_children
    if len(children) != 2:
        return None
    target_node, field_name_node = children
    field_name = field_name_node.text
    if target_node.type == "this":
        return ctx.class_field_java_types.get(field_name)

    object_java_type = java_expression_type(target_node, ctx)
    if object_java_type is None:
        return None

    simple = java_type_simple_name(object_java_type)
    type_fields = ctx.declared_type_java_fields.get(simple)
    if type_fields is None:
        for type_name, fields in ctx.declared_type_java_fields.items():
            if simple == type_name or object_java_type.endswith(f".{type_name}"):
                type_fields = fields
                break
    if type_fields is None:
        return None
    return type_fields.get(field_name)


def java_type_simple_name(java_type: str) -> str:
    """Return the unqualified base name from a Java type string."""
    simple = java_type.strip()
    if "<" in simple:
        simple = simple.split("<", 1)[0]
    if "." in simple:
        simple = simple.rsplit(".", 1)[-1]
    return simple.rstrip("[]")


def java_type_width(java_type: str) -> int | None:
    simple = java_type_simple_name(java_type)
    if simple in {"long", "Long"}:
        return 64
    if simple in {"byte", "short", "int", "char", "Byte", "Short", "Integer", "Character"}:
        return 32
    return None


def jdk_static_integral_field_type(raw_receiver: str, field_name: str) -> str | None:
    receiver = java_type_simple_name(raw_receiver)
    if receiver not in {
        "Byte",
        "Short",
        "Integer",
        "Long",
        "Character",
    }:
        return None
    if field_name in {"SIZE", "BYTES", "MIN_VALUE", "MAX_VALUE"}:
        return "int"
    return None

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
        return ctx.variable_java_types.get(node.text) or ctx.class_field_java_types.get(node.text)
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
    if node.type == "identifier":
        return ctx.variable_java_types.get(node.text) or ctx.class_field_java_types.get(node.text)
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
    if node.type == "method_invocation":
        return method_invocation_java_type(node)
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

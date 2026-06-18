"""Identifier, access, array, class-literal, cast, and instanceof helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import PatternBinding, TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.java_types import (
    java_expression_type,
    java_type_of_value,
    java_type_simple_name,
)
from j2py.translate.member_resolution import (
    static_import_field_fallback,
    wildcard_static_import_binding,
)
from j2py.translate.name_resolution import NameScope, scope_from_context
from j2py.translate.node_utils import first_child_by_type, unwrap_parens
from j2py.translate.rules.naming import (
    _receiver_simple_name,
    translate_class_name,
    translate_field_name,
)
from j2py.translate.rules.types import java_default_value, translate_type

_JDK_INTEGRAL_STATIC_FIELD_VALUES = {
    "Byte": {"SIZE": "8", "BYTES": "1", "MIN_VALUE": "-128", "MAX_VALUE": "127"},
    "Short": {"SIZE": "16", "BYTES": "2", "MIN_VALUE": "-2**15", "MAX_VALUE": "2**15 - 1"},
    "Integer": {"SIZE": "32", "BYTES": "4", "MIN_VALUE": "-2**31", "MAX_VALUE": "2**31 - 1"},
    "Long": {"SIZE": "64", "BYTES": "8", "MIN_VALUE": "-2**63", "MAX_VALUE": "2**63 - 1"},
    "Character": {"SIZE": "16", "BYTES": "2", "MIN_VALUE": "0", "MAX_VALUE": "0xFFFF"},
}


def _translate_identifier(raw_name: str, ctx: TranslationContext) -> str:
    resolved = ctx.name_resolver.resolve_identifier(raw_name, scope_from_context(ctx))
    if resolved.import_line:
        request_type_import(resolved.import_line, resolved.kind, ctx)
    if resolved.kind == "unknown" and ctx.wildcard_static_imports:
        for owner in ctx.wildcard_static_imports.values():
            binding = wildcard_static_import_binding(owner, raw_name, ctx, kind="field")
            if binding is not None:
                return static_import_field_fallback(binding, ctx.cfg)
    return resolved.python_name


def request_type_import(import_line: str, kind: str, ctx: TranslationContext) -> None:
    """Route a type import to module-level or body-local depending on context.

    Same-package sibling type references (kind ``"package_type"``) inside method
    bodies are emitted as function-local imports to break base↔derived circular
    import cycles (issue #325). All other imports remain at module level.
    """
    if ctx.in_method_body and kind == "package_type":
        ctx.body_local_imports.add(import_line)
    else:
        ctx.diagnostics.imports.need_line(import_line)


def _translate_field_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed field access")
        return node.text

    if _is_qualified_this_access(node):
        if ctx.outer_self_alias is not None:
            return ctx.outer_self_alias
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="qualified outer this requires captured outer self",
        )
        return f"__j2py_todo__({node.text!r})"

    static_field = _translate_static_field_access(node, ctx)
    if static_field is not None:
        return static_field

    target = translate_expression(children[0], ctx)
    field_name = translate_field_name(
        children[-1].text,
        snake_case=ctx.cfg.snake_case_fields,
    )
    if children[-1].text == "length":
        return f"len({target})"
    return f"{target}.{field_name}"


def _is_qualified_this_access(node: JavaNode) -> bool:
    children = node.named_children
    return (
        node.type == "field_access"
        and len(children) == 2
        and children[0].type
        in {"identifier", "type_identifier", "scoped_identifier", "scoped_type_identifier"}
        and children[1].type == "this"
    )


def _translate_array_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) != 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed array access")
        return f"__j2py_todo__({node.text!r})"
    array_expr = translate_expression(children[0], ctx)
    index_inner = unwrap_parens(children[1])
    if index_inner.type in {"assignment_expression", "update_expression"}:
        from j2py.translate.expr_ops import _desugar_embedded_assign

        index_expr = _desugar_embedded_assign(index_inner, ctx)
    else:
        index_expr = translate_expression(children[1], ctx)
    index_type = java_expression_type(index_inner, ctx)
    if (
        index_type is not None
        and java_type_simple_name(index_type) in {"char", "Character"}
        and not index_expr.startswith("ord(")
    ):
        index_expr = f"ord({index_expr})"
    return f"{array_expr}[{index_expr}]"


def _translate_array_initializer(node: JavaNode, ctx: TranslationContext) -> str:
    values = [
        translate_expression(child, ctx) for child in node.named_children if not is_comment(child)
    ]
    return f"[{', '.join(values)}]"


def _translate_array_creation(node: JavaNode, ctx: TranslationContext) -> str:
    initializer = first_child_by_type(node, "array_initializer")
    if initializer is not None:
        return translate_expression(initializer, ctx)
    dimension_nodes = [
        child for child in node.named_children if child.type in {"dimensions", "dimensions_expr"}
    ]
    sized_dimensions: list[JavaNode] = []
    has_unsized_dimension = False
    for dimension in dimension_nodes:
        if dimension.type == "dimensions_expr":
            if has_unsized_dimension:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=(
                        "array creation with interleaved unsized dimensions requires "
                        "allocation handling"
                    ),
                )
                return f"__j2py_todo__({node.text!r})"
            sized_dimensions.append(dimension)
        else:
            has_unsized_dimension = True
    if has_unsized_dimension and not sized_dimensions:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="array creation with unsized dimensions requires allocation handling",
        )
        return f"__j2py_todo__({node.text!r})"
    if sized_dimensions and all(dimension.named_children for dimension in sized_dimensions):
        type_node = _array_creation_type_node(node)
        default = (
            "None"
            if has_unsized_dimension
            else java_default_value(type_node.text if type_node is not None else "Object")
        )
        sizes = [
            translate_expression(dimension.named_children[0], ctx) for dimension in sized_dimensions
        ]
        return _sized_array_allocation(default, sizes)
    ctx.diagnostics.record(
        node,
        supported=False,
        reason="array creation without initializer requires size handling",
    )
    return f"__j2py_todo__({node.text!r})"


def _array_creation_type_node(node: JavaNode) -> JavaNode | None:
    return next(
        (
            child
            for child in node.named_children
            if child.type not in {"array_initializer", "dimensions", "dimensions_expr"}
        ),
        None,
    )


def _sized_array_allocation(default: str, sizes: list[str]) -> str:
    allocation = f"[{default}] * {sizes[-1]}"
    for size in reversed(sizes[:-1]):
        allocation = f"[{allocation} for _ in range({size})]"
    return allocation


def _translate_class_literal(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if not children:
        ctx.diagnostics.record(node, supported=False, reason="malformed class literal")
        return f"__j2py_todo__({node.text!r})"
    return translate_expression(children[0], ctx)


def _translate_static_field_access(node: JavaNode, ctx: TranslationContext) -> str | None:
    children = node.named_children
    if len(children) < 2:
        return None
    receiver = _receiver_simple_name(children[0].text)
    field = children[-1].text
    jdk_integral_constant = _jdk_integral_static_field_value(receiver, field)
    if jdk_integral_constant is not None:
        return jdk_integral_constant
    if receiver == "Math" and field == "PI":
        ctx.diagnostics.imports.need_math()
        return "math.pi"
    if receiver == "Math" and field == "E":
        ctx.diagnostics.imports.need_math()
        return "math.e"
    return None


def _jdk_integral_static_field_value(receiver: str, field: str) -> str | None:
    values = _JDK_INTEGRAL_STATIC_FIELD_VALUES.get(receiver)
    return values.get(field) if values is not None else None


def _remember_cast_comment(type_node: JavaNode, ctx: TranslationContext) -> None:
    if not ctx.cfg.emit_line_comments:
        return
    comment = f"cast: ({type_node.text})"
    if _is_numeric_narrowing_cast(type_node):
        comment = f"{comment} - numeric narrowing"
    ctx.pending_expression_comments.append(comment)


def _is_numeric_narrowing_cast(type_node: JavaNode) -> bool:
    return type_node.type in {"integral_type", "floating_point_type"} and type_node.text in {
        "byte",
        "short",
        "int",
        "float",
        "char",
    }


def _translate_cast_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed cast expression")
        return f"__j2py_todo__({node.text!r})"

    type_node = children[0]
    value_node = children[-1]
    value_expr = translate_expression(value_node, ctx)
    _remember_cast_comment(type_node, ctx)

    if type_node.type == "floating_point_type":
        ctx.diagnostics.record(node, supported=True, reason="translated numeric cast")
        src = java_type_of_value(value_node, ctx)
        if src in {"char", "Character"}:
            return f"float(ord({value_expr}))"
        return f"float({value_expr})"

    if type_node.type == "integral_type":
        ctx.diagnostics.record(node, supported=True, reason="translated numeric cast")
        type_text = type_node.text
        src = java_type_of_value(value_node, ctx)
        is_char_src = src in {"char", "Character"}
        base = f"ord({value_expr})" if is_char_src else f"int({value_expr})"
        if type_text == "char":
            return value_expr if is_char_src else f"chr({base} & 0xFFFF)"
        if type_text == "byte":
            return f"(({base} & 0xFF) ^ 0x80) - 0x80"
        if type_text == "short":
            return f"(({base} & 0xFFFF) ^ 0x8000) - 0x8000"
        return base

    py_type = translate_type(type_node.text, ctx.cfg)
    cast_target = _runtime_safe_cast_target(type_node, py_type, ctx)
    ctx.diagnostics.imports.need_typing("cast")
    ctx.diagnostics.imports.need_type_annotation(py_type)
    ctx.diagnostics.record(node, supported=True, reason="translated reference cast to typing.cast")
    ctx.diagnostics.warn(
        node,
        reason="Java reference cast translated to typing.cast; verify runtime type",
    )
    return f"cast({cast_target}, {value_expr})"


def _runtime_safe_cast_target(type_node: JavaNode, py_type: str, ctx: TranslationContext) -> str:
    if "[" not in py_type:
        return py_type
    scope = NameScope(
        containing_class_name=ctx.containing_class_name,
        nested_class_names=ctx.nested_class_names,
        snake_case_fields=ctx.cfg.snake_case_fields,
    )
    translated_type_kinds = {
        "containing_type",
        "nested_type",
        "package_type",
        "compilation_unit_type",
    }
    for candidate in type_node.walk():
        if candidate.type not in {"type_identifier", "scoped_type_identifier"}:
            continue
        raw_name = candidate.text.rsplit(".", 1)[-1]
        py_name = translate_class_name(raw_name)
        if py_name not in py_type:
            continue
        resolved = ctx.name_resolver.resolve_identifier(raw_name, scope)
        if resolved.kind in translated_type_kinds:
            return repr(py_type)
    return py_type


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

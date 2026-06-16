"""Identifier, access, array, class-literal, cast, and instanceof helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import PatternBinding, TranslationContext
from j2py.translate.expr_types import _java_type_of_value
from j2py.translate.expressions import translate_expression
from j2py.translate.name_resolution import scope_from_context
from j2py.translate.node_utils import first_child_by_type, unwrap_parens
from j2py.translate.rules.naming import translate_class_name, translate_field_name
from j2py.translate.rules.types import java_default_value, translate_type


def _translate_identifier(raw_name: str, ctx: TranslationContext) -> str:
    resolved = ctx.name_resolver.resolve_identifier(raw_name, scope_from_context(ctx))
    if resolved.import_line:
        ctx.diagnostics.imports.need_line(resolved.import_line)
    return resolved.python_name


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
    dimensions = [child for child in node.named_children if child.type == "dimensions_expr"]
    if any(child.type == "dimensions" for child in node.named_children):
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="array creation with unsized dimensions requires allocation handling",
        )
        return f"__j2py_todo__({node.text!r})"
    if dimensions and all(dimension.named_children for dimension in dimensions):
        type_node = _array_creation_type_node(node)
        default = java_default_value(type_node.text if type_node is not None else "Object")
        sizes = [translate_expression(dimension.named_children[0], ctx) for dimension in dimensions]
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
    if receiver == "Math" and field == "PI":
        ctx.diagnostics.imports.need_math()
        return "math.pi"
    if receiver == "Math" and field == "E":
        ctx.diagnostics.imports.need_math()
        return "math.e"
    if receiver == "Integer" and field == "MAX_VALUE":
        return "2**31 - 1"
    return None


def _receiver_simple_name(raw_receiver: str) -> str:
    return raw_receiver.rsplit(".", 1)[-1]


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
        src = _java_type_of_value(value_node, ctx)
        if src in {"char", "Character"}:
            return f"float(ord({value_expr}))"
        return f"float({value_expr})"

    if type_node.type == "integral_type":
        ctx.diagnostics.record(node, supported=True, reason="translated numeric cast")
        type_text = type_node.text
        src = _java_type_of_value(value_node, ctx)
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
    ctx.diagnostics.imports.need_typing("cast")
    ctx.diagnostics.imports.need_type_annotation(py_type)
    ctx.diagnostics.record(node, supported=True, reason="translated reference cast to typing.cast")
    ctx.diagnostics.warn(
        node,
        reason="Java reference cast translated to typing.cast; verify runtime type",
    )
    return f"cast({py_type}, {value_expr})"


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

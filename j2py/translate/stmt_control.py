"""Control-flow statement helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import infer_expression_py_type, translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import element_type_from_container, is_var_type
from j2py.translate.statements import _translate_local_variable_declaration, translate_body


def _translate_enhanced_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated enhanced for statement")
    type_node = node.child_by_field("type")
    name_node = node.child_by_field("name")
    value_node = node.child_by_field("value")
    body_node = node.child_by_field("body")
    if name_node is None or value_node is None or body_node is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed enhanced for statement")
        return [f"{indent}# TODO(j2py): malformed enhanced for statement", f"{indent}pass"]

    raw_name = name_node.text
    py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
    iterable = translate_expression(value_node, ctx)

    previous_locals = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    ctx.local_names.add(raw_name)
    if type_node is not None and is_var_type(type_node.text):
        container_type = infer_expression_py_type(value_node, ctx)
        element_type = (
            element_type_from_container(container_type) if container_type is not None else None
        )
        if element_type is not None:
            ctx.variable_types[raw_name] = element_type
    try:
        lines = [f"{indent}for {py_name} in {iterable}:"]
        lines.extend(translate_body(body_node, ctx, indent=f"{indent}    "))
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
    return lines


def _translate_if(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
    keyword: str = "if",
) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated if statement")
    condition = node.child_by_field("condition")
    consequence = node.child_by_field("consequence")
    alternative = node.child_by_field("alternative")

    previous_bindings = ctx.pattern_bindings
    ctx.pattern_bindings = []
    try:
        condition_text = translate_expression(condition, ctx)
        pattern_bindings = ctx.pattern_bindings
    finally:
        ctx.pattern_bindings = previous_bindings

    lines = [f"{indent}{keyword} {condition_text}:"]
    if consequence is None:
        ctx.diagnostics.record(node, supported=False, reason="if statement without a body")
        lines.append(f"{indent}    pass")
    else:
        previous_locals = set(ctx.local_names)
        previous_types = dict(ctx.variable_types)
        for binding in pattern_bindings:
            ctx.local_names.add(binding.raw_name)
            ctx.variable_types[binding.raw_name] = binding.py_type
            lines.append(f"{indent}    {binding.py_name} = {binding.source}")
        try:
            lines.extend(translate_body(consequence, ctx, indent=f"{indent}    "))
        finally:
            ctx.local_names = previous_locals
            ctx.variable_types = previous_types

    if alternative is None:
        return lines

    if alternative.type == "if_statement":
        lines.extend(_translate_if(alternative, ctx, indent=indent, keyword="elif"))
        return lines

    lines.append(f"{indent}else:")
    lines.extend(translate_body(alternative, ctx, indent=f"{indent}    "))
    return lines


def _translate_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated for statement")
    parts = _traditional_for_parts(node)
    if parts is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed for statement")
        return [f"{indent}# TODO(j2py): malformed for statement", f"{indent}pass"]

    initializer, condition, update, body = parts
    if initializer is not None and condition is not None and update is not None:
        range_loop = _range_loop_parts(initializer, condition, update, ctx)
        if range_loop is not None:
            raw_name, py_name, start, stop = range_loop
            previous_locals = set(ctx.local_names)
            ctx.local_names.add(raw_name)
            lines = [f"{indent}for {py_name} in range({start}, {stop}):"]
            lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
            ctx.local_names = previous_locals
            return lines

    out: list[str] = []
    if initializer is not None:
        out.extend(_translate_for_initializer(initializer, ctx, indent=indent))

    if condition is not None:
        while_expr = translate_expression(condition, ctx)
    else:
        ctx.diagnostics.warn(
            node,
            reason="for loop without condition lowered to while True; verify loop exit path",
        )
        while_expr = "True"

    out.append(f"{indent}while {while_expr}:")
    out.extend(translate_body(body, ctx, indent=f"{indent}    "))
    if update is not None:
        out.append(f"{indent}    {translate_expression(update, ctx)}")
    return out


_FOR_INITIALIZER_TYPES = frozenset({"local_variable_declaration", "assignment_expression"})
_FOR_UPDATE_TYPES = frozenset({"update_expression", "assignment_expression"})


def _is_for_initializer(node: JavaNode) -> bool:
    return node.type in _FOR_INITIALIZER_TYPES


def _is_for_update_clause(node: JavaNode) -> bool:
    return node.type in _FOR_UPDATE_TYPES


def _traditional_for_parts(
    node: JavaNode,
) -> tuple[JavaNode | None, JavaNode | None, JavaNode | None, JavaNode] | None:
    """Parse a traditional for_statement by clause role, not fixed child count."""
    children = node.named_children
    if not children:
        return None

    body = children[-1]
    if body.type != "block":
        return None

    rest = children[:-1]
    if not rest:
        return None, None, None, body

    if len(rest) == 1:
        clause = rest[0]
        if _is_for_update_clause(clause):
            return None
        return None, clause, None, body

    if len(rest) == 2:
        first, second = rest
        if _is_for_update_clause(second):
            if _is_for_initializer(first):
                return first, None, second, body
            return None, first, second, body
        if _is_for_initializer(first):
            return first, second, None, body
        return None, first, None, body

    if len(rest) == 3:
        initializer, condition, update = rest
        if not _is_for_update_clause(update):
            return None
        if not _is_for_initializer(initializer):
            return None
        return initializer, condition, update, body

    return None


def _translate_for_initializer(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    if node.type == "local_variable_declaration":
        return _translate_local_variable_declaration(node, ctx, indent=indent)
    if node.type == "assignment_expression":
        return [f"{indent}{translate_expression(node, ctx)}"]
    return [f"{indent}{translate_expression(node, ctx)}"]


def _range_loop_parts(
    initializer: JavaNode,
    condition: JavaNode,
    update: JavaNode,
    ctx: TranslationContext,
) -> tuple[str, str, str, str] | None:
    declarator = first_child_by_type(initializer, "variable_declarator")
    if declarator is None:
        return None
    name_node = declarator.child_by_field("name")
    value_node = declarator.child_by_field("value")
    condition_children = condition.children
    update_children = update.children
    if (
        name_node is None
        or value_node is None
        or len(condition_children) < 3
        or len(update_children) < 2
        or update_children[-1].text != "++"
        or condition_children[0].text != name_node.text
        or condition_children[1].text != "<"
        or update.named_children[0].text != name_node.text
    ):
        return None
    return (
        name_node.text,
        translate_field_name(name_node.text, snake_case=ctx.cfg.snake_case_fields),
        translate_expression(value_node, ctx),
        translate_expression(condition_children[2], ctx),
    )


def _translate_while(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated while statement")
    condition = node.child_by_field("condition") or node.named_children[0]
    body = node.child_by_field("body") or node.named_children[-1]
    lines = [f"{indent}while {translate_expression(condition, ctx)}:"]
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    return lines


def _translate_do_while(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated do while statement")
    body = first_child_by_type(node, "block")
    condition = first_child_by_type(node, "parenthesized_expression")
    lines = [f"{indent}while True:"]
    if body is None:
        lines.append(f"{indent}    pass")
    else:
        lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    lines.append(f"{indent}    if not ({translate_expression(condition, ctx)}):")
    lines.append(f"{indent}        break")
    return lines


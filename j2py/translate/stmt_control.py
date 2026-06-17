"""Control-flow statement helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import infer_expression_py_type, translate_expression
from j2py.translate.node_utils import direct_children_by_type, first_child_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import element_type_from_container, is_var_type
from j2py.translate.statements import (
    _flush_hoisted_pre_stmts,
    _translate_local_variable_declaration,
    _with_expression_comments,
    translate_body,
)


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
    previous_java_types = dict(ctx.variable_java_types)
    ctx.local_names.add(raw_name)
    if type_node is not None and not is_var_type(type_node.text):
        ctx.variable_java_types[raw_name] = type_node.text
    if type_node is not None and is_var_type(type_node.text):
        container_type = infer_expression_py_type(value_node, ctx)
        element_type = (
            element_type_from_container(container_type) if container_type is not None else None
        )
        if element_type is not None:
            ctx.variable_types[raw_name] = element_type
    try:
        lines = [_with_expression_comments(f"{indent}for {py_name} in {iterable}:", ctx)]
        lines.extend(translate_body(body_node, ctx, indent=f"{indent}    "))
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
        ctx.variable_java_types = previous_java_types
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

    # Compound assigns in conditions (rare) are hoisted before the if/elif.
    pre = _flush_hoisted_pre_stmts(ctx, indent)
    lines = pre + [_with_expression_comments(f"{indent}{keyword} {condition_text}:", ctx)]
    if consequence is None:
        ctx.diagnostics.record(node, supported=False, reason="if statement without a body")
        lines.append(f"{indent}    pass")
    else:
        previous_locals = set(ctx.local_names)
        previous_types = dict(ctx.variable_types)
        previous_java_types = dict(ctx.variable_java_types)
        for binding in pattern_bindings:
            ctx.local_names.add(binding.raw_name)
            ctx.variable_types[binding.raw_name] = binding.py_type
            lines.append(f"{indent}    {binding.py_name} = {binding.source}")
        try:
            lines.extend(_translate_statement_or_body(consequence, ctx, indent=f"{indent}    "))
        finally:
            ctx.local_names = previous_locals
            ctx.variable_types = previous_types
            ctx.variable_java_types = previous_java_types

    if alternative is None:
        return lines

    if alternative.type == "if_statement":
        lines.extend(_translate_if(alternative, ctx, indent=indent, keyword="elif"))
        return lines

    lines.append(f"{indent}else:")
    lines.extend(_translate_statement_or_body(alternative, ctx, indent=f"{indent}    "))
    return lines


def _translate_statement_or_body(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    if node.type == "block":
        return translate_body(node, ctx, indent=indent)
    from j2py.translate.statements import translate_statement

    return translate_statement(node, ctx, indent=indent)


def _translate_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated for statement")
    parts = _traditional_for_parts(node)
    if parts is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed for statement")
        return [f"{indent}# TODO(j2py): malformed for statement", f"{indent}pass"]

    initializers, condition, updates, body = parts
    if (
        len(initializers) == 1
        and condition is not None
        and len(updates) == 1
        and _initializer_supports_range_loop(initializers[0])
    ):
        range_loop = _range_loop_parts(initializers[0], condition, updates[0], ctx)
        if range_loop is not None:
            raw_name, py_name, start, stop = range_loop
            previous_locals = set(ctx.local_names)
            ctx.local_names.add(raw_name)
            lines = [
                _with_expression_comments(
                    f"{indent}for {py_name} in range({start}, {stop}):",
                    ctx,
                )
            ]
            lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
            ctx.local_names = previous_locals
            return lines

    out: list[str] = []
    for initializer in initializers:
        out.extend(_translate_for_initializer(initializer, ctx, indent=indent))

    if condition is not None:
        while_expr = translate_expression(condition, ctx)
        out.extend(_flush_hoisted_pre_stmts(ctx, indent))
    else:
        ctx.diagnostics.warn(
            node,
            reason="for loop without condition lowered to while True; verify loop exit path",
        )
        while_expr = "True"

    out.append(_with_expression_comments(f"{indent}while {while_expr}:", ctx))
    out.extend(translate_body(body, ctx, indent=f"{indent}    "))
    for update in updates:
        out.append(
            _with_expression_comments(
                f"{indent}    {translate_expression(update, ctx)}",
                ctx,
            )
        )
    return out


_FOR_INITIALIZER_TYPES = frozenset({"local_variable_declaration", "assignment_expression"})
_FOR_UPDATE_TYPES = frozenset({"update_expression", "assignment_expression"})
_FOR_EXPRESSION_CLAUSE_TYPES = frozenset(
    {
        "method_invocation",
        "object_creation_expression",
        "array_creation_expression",
        "field_access",
        "identifier",
    },
)


def _peel_for_initializers(rest: list[JavaNode]) -> list[JavaNode]:
    initializers: list[JavaNode] = []
    while rest:
        if rest[0].type in _FOR_INITIALIZER_TYPES or rest[0].type == "expression_statement":
            initializers.append(rest.pop(0))
            continue
        if len(rest) >= 2 and rest[0].type in _FOR_EXPRESSION_CLAUSE_TYPES:
            initializers.append(rest.pop(0))
            continue
        break
    return initializers


def _initializer_supports_range_loop(initializer: JavaNode) -> bool:
    """Range lowering only applies to a single declarator in one local declaration."""
    if initializer.type != "local_variable_declaration":
        return False
    return len(direct_children_by_type(initializer, "variable_declarator")) == 1


def _traditional_for_parts(
    node: JavaNode,
) -> tuple[list[JavaNode], JavaNode | None, list[JavaNode], JavaNode] | None:
    """Parse a traditional for_statement by clause role, not fixed child count."""
    children = node.named_children
    if not children:
        return None

    body = children[-1]
    if body.type != "block":
        return None

    rest = list(children[:-1])
    initializers = _peel_for_initializers(rest)

    if not rest:
        return initializers, None, [], body

    if len(rest) == 1:
        clause = rest[0]
        if _is_strict_for_update(clause):
            return initializers, None, [clause], body
        return initializers, clause, [], body

    condition = rest[0]
    updates = rest[1:]
    if not all(_is_for_update_like(node) for node in updates):
        return None
    return initializers, condition, updates, body


def _is_strict_for_update(node: JavaNode) -> bool:
    """Updates that can appear as the sole remaining clause (no condition)."""
    return node.type in _FOR_UPDATE_TYPES


def _is_for_update_like(node: JavaNode) -> bool:
    """Expressions allowed in the update clause list after the condition."""
    return node.type in _FOR_UPDATE_TYPES or node.type in _FOR_EXPRESSION_CLAUSE_TYPES


def _translate_for_initializer(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    if node.type == "local_variable_declaration":
        return _translate_local_variable_declaration(node, ctx, indent=indent)
    if node.type == "expression_statement":
        from j2py.translate.statements import translate_statement

        return translate_statement(node, ctx, indent=indent)
    if node.type in _FOR_EXPRESSION_CLAUSE_TYPES:
        return [_with_expression_comments(f"{indent}{translate_expression(node, ctx)}", ctx)]
    if node.type == "assignment_expression":
        return [_with_expression_comments(f"{indent}{translate_expression(node, ctx)}", ctx)]
    return [_with_expression_comments(f"{indent}{translate_expression(node, ctx)}", ctx)]


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
        or condition_children[1].text not in {"<", "<="}
        or update.named_children[0].text != name_node.text
    ):
        return None
    stop = translate_expression(condition_children[2], ctx)
    if condition_children[1].text == "<=":
        stop = f"({stop}) + 1"
    return (
        name_node.text,
        translate_field_name(name_node.text, snake_case=ctx.cfg.snake_case_fields),
        translate_expression(value_node, ctx),
        stop,
    )


def _translate_while(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated while statement")
    condition = node.child_by_field("condition") or node.named_children[0]
    body = node.child_by_field("body") or node.named_children[-1]
    while_expr = translate_expression(condition, ctx)
    # Compound assigns in conditions (rare) are hoisted before the while.
    pre = _flush_hoisted_pre_stmts(ctx, indent)
    lines = pre + [_with_expression_comments(f"{indent}while {while_expr}:", ctx)]
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
    lines.append(
        _with_expression_comments(
            f"{indent}    if not ({translate_expression(condition, ctx)}):",
            ctx,
        )
    )
    lines.append(f"{indent}        break")
    return lines

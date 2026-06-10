"""Statement emission for the rule-based skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import direct_children_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import translate_type


def translate_body(body: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    lines: list[str] = []
    for statement in body.named_children:
        lines.extend(translate_statement(statement, ctx, indent=indent))
    if not lines:
        lines.append(f"{indent}pass")
    return lines


def translate_statement(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    if node.type == "expression_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated expression statement")
        expr = node.named_children[0] if node.named_children else node
        return [f"{indent}{translate_expression(expr, ctx)}"]

    if node.type == "return_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated return statement")
        if not node.named_children:
            return [f"{indent}return"]
        return [f"{indent}return {translate_expression(node.named_children[0], ctx)}"]

    if node.type == "local_variable_declaration":
        return _translate_local_variable_declaration(node, ctx, indent=indent)

    if node.type == "enhanced_for_statement":
        return _translate_enhanced_for(node, ctx, indent=indent)

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported statement {node.type}")
    return [f"{indent}# TODO(j2py): unsupported {node.type}", f"{indent}pass"]


def _translate_local_variable_declaration(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    ctx.diagnostics.record(
        node,
        supported=True,
        reason="translated local variable declaration",
    )
    type_node = node.child_by_field("type")
    py_type = translate_type(type_node.text if type_node is not None else "Object", ctx.cfg)

    lines: list[str] = []
    for declarator in direct_children_by_type(node, "variable_declarator"):
        name_node = declarator.child_by_field("name")
        if name_node is None:
            continue
        raw_name = name_node.text
        py_name = translate_field_name(raw_name)
        ctx.local_names.add(raw_name)
        value_node = declarator.child_by_field("value")
        value = translate_expression(value_node, ctx) if value_node else "None"
        if value in {"[]", "{}", "set()"}:
            lines.append(f"{indent}{py_name}: {py_type} = {value}")
        else:
            lines.append(f"{indent}{py_name} = {value}")
    return lines


def _translate_enhanced_for(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated enhanced for statement")
    children = node.named_children
    if len(children) < 4:
        ctx.diagnostics.record(node, supported=False, reason="malformed enhanced for statement")
        return [f"{indent}# TODO(j2py): malformed enhanced for statement", f"{indent}pass"]

    raw_name = children[1].text
    py_name = translate_field_name(raw_name)
    iterable = translate_expression(children[2], ctx)
    body = children[3]

    previous_locals = set(ctx.local_names)
    ctx.local_names.add(raw_name)
    lines = [f"{indent}for {py_name} in {iterable}:"]
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    ctx.local_names = previous_locals
    return lines

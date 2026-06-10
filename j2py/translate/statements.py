"""Statement emission for the rule-based skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import direct_children_by_type, first_child_by_type
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
    if is_comment(node):
        ctx.diagnostics.warn(node, reason="preserved comment")
        return translate_comment(node, indent=indent)

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

    if node.type == "if_statement":
        return _translate_if(node, ctx, indent=indent)

    if node.type == "for_statement":
        return _translate_for(node, ctx, indent=indent)

    if node.type == "while_statement":
        return _translate_while(node, ctx, indent=indent)

    if node.type == "do_statement":
        return _translate_do_while(node, ctx, indent=indent)

    if node.type == "try_statement":
        return _translate_try(node, ctx, indent=indent)

    if node.type == "explicit_constructor_invocation":
        return _translate_explicit_constructor_invocation(node, ctx, indent=indent)

    if node.type == "throw_statement":
        return _translate_throw(node, ctx, indent=indent)

    if node.type == "break_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated break statement")
        return [f"{indent}break"]

    if node.type == "continue_statement":
        ctx.diagnostics.record(node, supported=True, reason="translated continue statement")
        return [f"{indent}continue"]

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

    lines = [f"{indent}{keyword} {translate_expression(condition, ctx)}:"]
    if consequence is None:
        ctx.diagnostics.record(node, supported=False, reason="if statement without a body")
        lines.append(f"{indent}    pass")
    else:
        lines.extend(translate_body(consequence, ctx, indent=f"{indent}    "))

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
    children = node.named_children
    if len(children) < 4:
        ctx.diagnostics.record(node, supported=False, reason="malformed for statement")
        return [f"{indent}# TODO(j2py): malformed for statement", f"{indent}pass"]

    initializer, condition, update, body = children[0], children[1], children[2], children[3]
    range_loop = _range_loop_parts(initializer, condition, update, ctx)
    if range_loop is not None:
        raw_name, py_name, start, stop = range_loop
        previous_locals = set(ctx.local_names)
        ctx.local_names.add(raw_name)
        lines = [f"{indent}for {py_name} in range({start}, {stop}):"]
        lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
        ctx.local_names = previous_locals
        return lines

    lines = translate_statement(initializer, ctx, indent=indent)
    lines.append(f"{indent}while {translate_expression(condition, ctx)}:")
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    lines.append(f"{indent}    {translate_expression(update, ctx)}")
    return lines


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
        translate_field_name(name_node.text),
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


def _translate_try(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated try statement")
    try_body = first_child_by_type(node, "block")
    lines = [f"{indent}try:"]
    lines.extend(
        translate_body(try_body, ctx, indent=f"{indent}    ")
        if try_body is not None
        else [f"{indent}    pass"],
    )

    for catch_clause in direct_children_by_type(node, "catch_clause"):
        lines.extend(_translate_catch(catch_clause, ctx, indent=indent))

    finally_clause = first_child_by_type(node, "finally_clause")
    if finally_clause is not None:
        finally_body = first_child_by_type(finally_clause, "block")
        lines.append(f"{indent}finally:")
        lines.extend(
            translate_body(finally_body, ctx, indent=f"{indent}    ")
            if finally_body is not None
            else [f"{indent}    pass"],
        )

    return lines


def _translate_explicit_constructor_invocation(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    args_node = first_child_by_type(node, "argument_list")
    args = translate_expression(args_node, ctx) if args_node is not None else ""
    target = node.named_children[0] if node.named_children else None

    if target is not None and target.type == "super":
        ctx.diagnostics.record(node, supported=True, reason="translated super constructor call")
        return [f"{indent}super().__init__({args})"]

    ctx.diagnostics.record(
        node,
        supported=False,
        reason="constructor delegation requires overload merge",
    )
    return [
        f"{indent}# TODO(j2py): unsupported constructor delegation {node.text!r}",
        f"{indent}pass",
    ]


def _translate_catch(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated catch clause")
    parameter = first_child_by_type(node, "catch_formal_parameter")
    body = first_child_by_type(node, "block")
    exception_type = "Exception"
    exception_name = "exc"
    if parameter is not None:
        exception_type = _catch_type(parameter, ctx)
        name_node = parameter.child_by_field("name") or first_child_by_type(parameter, "identifier")
        if name_node is not None:
            exception_name = translate_field_name(name_node.text)
    lines = [f"{indent}except {exception_type} as {exception_name}:"]
    lines.extend(
        translate_body(body, ctx, indent=f"{indent}    ")
        if body is not None
        else [f"{indent}    pass"],
    )
    return lines


def _catch_type(parameter: JavaNode, ctx: TranslationContext) -> str:
    catch_type = first_child_by_type(parameter, "catch_type")
    if catch_type is None:
        return "Exception"
    types = [child.text for child in catch_type.named_children if child.type == "type_identifier"]
    mapped = [ctx.cfg.exception_map.get(java_type, java_type) for java_type in types]
    if not mapped:
        return ctx.cfg.exception_map.get(catch_type.text, catch_type.text)
    if len(mapped) == 1:
        return mapped[0]
    return f"({', '.join(mapped)})"


def _translate_throw(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated throw statement")
    expression = node.named_children[0] if node.named_children else None
    if expression is None:
        ctx.diagnostics.record(node, supported=False, reason="throw statement without expression")
        return [f"{indent}raise RuntimeError()"]
    if expression.type == "object_creation_expression":
        return [f"{indent}raise {_translate_exception_creation(expression, ctx)}"]
    return [f"{indent}raise {translate_expression(expression, ctx)}"]


def _translate_exception_creation(node: JavaNode, ctx: TranslationContext) -> str:
    type_node = node.child_by_field("type")
    args_node = first_child_by_type(node, "argument_list")
    raw_type = type_node.text if type_node is not None else "Exception"
    py_type = ctx.cfg.exception_map.get(raw_type, raw_type)
    args = list(args_node.named_children) if args_node is not None else []
    if len(args) >= 2 and args[1].type == "identifier":
        message = translate_expression(args[0], ctx)
        cause = translate_expression(args[1], ctx)
        return f"{py_type}({message}) from {cause}"
    rendered_args = ", ".join(translate_expression(arg, ctx) for arg in args)
    return f"{py_type}({rendered_args})"

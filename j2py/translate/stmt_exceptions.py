"""Exception-related statement helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.java_types import java_expression_type, java_type_simple_name
from j2py.translate.node_utils import direct_children_by_type, first_child_by_type, unwrap_parens
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import translate_type
from j2py.translate.statements import translate_body


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


def _translate_try_with_resources(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    resources = first_child_by_type(node, "resource_specification")
    body = first_child_by_type(node, "block")
    if resources is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed try-with-resources")
        return [f"{indent}# TODO(j2py): malformed try-with-resources", f"{indent}pass"]

    resource_parts: list[str] = []
    resource_bindings: list[tuple[str, str, str]] = []
    for resource in direct_children_by_type(resources, "resource"):
        named = resource.named_children
        if len(named) == 1:
            resource_parts.append(translate_expression(named[0], ctx))
            continue
        if len(named) < 3:
            ctx.diagnostics.record(
                resource,
                supported=False,
                reason="malformed try-with-resources resource",
            )
            return [
                f"{indent}# TODO(j2py): malformed try-with-resources resource",
                f"{indent}pass",
            ]
        type_node, name_node, value_node = named[0], named[1], named[-1]
        raw_name = name_node.text
        py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
        java_type = type_node.text
        py_type = translate_type(java_type, ctx.cfg)
        resource_parts.append(f"{translate_expression(value_node, ctx)} as {py_name}")
        resource_bindings.append((raw_name, py_type, java_type))

    if not resource_parts:
        ctx.diagnostics.record(node, supported=False, reason="try-with-resources without resources")
        return [f"{indent}# TODO(j2py): try-with-resources without resources", f"{indent}pass"]

    ctx.diagnostics.record(node, supported=True, reason="translated try-with-resources statement")
    previous_locals = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    previous_java_types = dict(ctx.variable_java_types)
    for raw_name, py_type, java_type in resource_bindings:
        ctx.local_names.add(raw_name)
        ctx.variable_types[raw_name] = py_type
        ctx.variable_java_types[raw_name] = java_type
    try:
        lines = [f"{indent}with {', '.join(resource_parts)}:"]
        lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
        ctx.variable_java_types = previous_java_types
    return lines


def _translate_catch(node: JavaNode, ctx: TranslationContext, *, indent: str) -> list[str]:
    ctx.diagnostics.record(node, supported=True, reason="translated catch clause")
    parameter = first_child_by_type(node, "catch_formal_parameter")
    body = first_child_by_type(node, "block")
    exception_type = "Exception"
    exception_name = "exc"
    exception_java_types: list[str] = []
    raw_exception_name = "exc"
    if parameter is not None:
        exception_type = _catch_type(parameter, ctx)
        exception_java_types = _catch_java_types(parameter)
        name_node = parameter.child_by_field("name") or first_child_by_type(parameter, "identifier")
        if name_node is not None:
            raw_exception_name = name_node.text
            exception_name = translate_field_name(
                name_node.text,
                snake_case=ctx.cfg.snake_case_fields,
            )
    lines = [f"{indent}except {exception_type} as {exception_name}:"]
    previous_locals = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    previous_java_types = dict(ctx.variable_java_types)
    ctx.local_names.add(raw_exception_name)
    ctx.variable_types[raw_exception_name] = exception_type
    if exception_java_types:
        ctx.variable_java_types[raw_exception_name] = " | ".join(exception_java_types)
    try:
        lines.extend(
            translate_body(body, ctx, indent=f"{indent}    ")
            if body is not None
            else [f"{indent}    pass"],
        )
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
        ctx.variable_java_types = previous_java_types
    return lines


def _catch_type(parameter: JavaNode, ctx: TranslationContext) -> str:
    types = _catch_java_types(parameter)
    if not types:
        return "Exception"
    mapped = [ctx.cfg.exception_map.get(java_type, java_type) for java_type in types]
    if len(mapped) == 1:
        return mapped[0]
    return f"({', '.join(mapped)})"


def _catch_java_types(parameter: JavaNode) -> list[str]:
    catch_type = first_child_by_type(parameter, "catch_type")
    if catch_type is None:
        return []
    types = [child.text for child in catch_type.named_children if child.type == "type_identifier"]
    return types or [catch_type.text]


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
    if len(args) == 2 and _is_exception_cause_argument(args[1], ctx):
        message = translate_expression(args[0], ctx)
        cause = translate_expression(args[1], ctx)
        return f"{py_type}({message}) from {cause}"
    rendered_args = ", ".join(
        _translate_exception_constructor_arg(arg, ctx, is_last=index == len(args) - 1)
        for index, arg in enumerate(args)
    )
    return f"{py_type}({rendered_args})"


def _translate_exception_constructor_arg(
    arg: JavaNode,
    ctx: TranslationContext,
    *,
    is_last: bool,
) -> str:
    rendered = translate_expression(arg, ctx)
    unwrapped = unwrap_parens(arg)
    if is_last and unwrapped.type == "identifier" and unwrapped.text in ctx.spread_param_names:
        return f"*{translate_expression(unwrapped, ctx)}"
    return rendered


def _is_exception_cause_argument(arg: JavaNode, ctx: TranslationContext) -> bool:
    java_type = java_expression_type(arg, ctx)
    if java_type is None:
        return False
    for candidate in java_type.split("|"):
        simple = java_type_simple_name(candidate.strip())
        if simple == "Throwable":
            return True
        if simple in ctx.cfg.exception_map:
            return True
        if simple.endswith(("Exception", "Error")):
            return True
    return False

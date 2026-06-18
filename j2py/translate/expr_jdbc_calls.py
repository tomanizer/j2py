"""Spring JDBC call lowering to SQLAlchemy Core scaffolding."""

from __future__ import annotations

import ast

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.java_types import java_expression_type, java_type_simple_name
from j2py.translate.rules.naming import translate_field_name

_JDBC_TEMPLATE_TYPES = frozenset({"JdbcTemplate", "NamedParameterJdbcTemplate"})
_ROW_MAPPER_TODO = "TODO(j2py): JdbcTemplate RowMapper/callback requires project row mapping"


def translate_jdbc_template_method_invocation(
    node: JavaNode,
    *,
    method_name: str,
    receiver: str,
    receiver_nodes: list[JavaNode],
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    ctx: TranslationContext,
) -> str | None:
    """Lower safe Spring JdbcTemplate calls to SQLAlchemy Core scaffolding."""

    if not receiver_nodes or not receiver:
        return None
    receiver_type = java_expression_type(receiver_nodes[0], ctx)
    if receiver_type is None:
        return None
    template_type = java_type_simple_name(receiver_type)
    if template_type not in _JDBC_TEMPLATE_TYPES:
        return None

    if method_name == "update":
        return _translate_update(
            node,
            template_type=template_type,
            receiver=receiver,
            arg_nodes=arg_nodes,
            arg_expressions=arg_expressions,
            ctx=ctx,
        )
    if method_name == "queryForObject":
        return _translate_query_for_object(
            node,
            template_type=template_type,
            receiver=receiver,
            arg_nodes=arg_nodes,
            arg_expressions=arg_expressions,
            ctx=ctx,
        )
    if method_name == "query" and _has_row_mapper_or_callback(arg_nodes[1:]):
        return _unsupported_row_mapper(node, ctx)
    return None


def _translate_update(
    node: JavaNode,
    *,
    template_type: str,
    receiver: str,
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    ctx: TranslationContext,
) -> str:
    if not arg_nodes:
        return _unsupported(node, ctx, reason="JdbcTemplate.update without SQL argument")
    if _has_row_mapper_or_callback(arg_nodes[1:]):
        return _unsupported_row_mapper(node, ctx)

    sql_node = arg_nodes[0]
    if template_type == "NamedParameterJdbcTemplate":
        params = arg_expressions[1] if len(arg_expressions) >= 2 else None
        positional_count = 0
    else:
        params = _positional_param_dict(arg_expressions[1:])
        positional_count = len(arg_expressions) - 1

    ctx.diagnostics.record(
        node,
        supported=True,
        reason="lowered JdbcTemplate.update to SQLAlchemy Core scaffold",
        category="spring-jdbc-sqlalchemy",
        facts={"template_type": template_type, "method": "update"},
    )
    execute = _execute_expression(
        receiver,
        sql_node,
        params=params,
        positional_count=positional_count,
        ctx=ctx,
    )
    return f"{execute}.rowcount"


def _translate_query_for_object(
    node: JavaNode,
    *,
    template_type: str,
    receiver: str,
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    ctx: TranslationContext,
) -> str:
    if not arg_nodes:
        return _unsupported(node, ctx, reason="JdbcTemplate.queryForObject without SQL argument")
    if _has_row_mapper_or_callback(arg_nodes[1:]):
        return _unsupported_row_mapper(node, ctx)

    sql_node = arg_nodes[0]
    params: str | None = None
    positional_count = 0
    if template_type == "NamedParameterJdbcTemplate":
        if len(arg_nodes) >= 3 and _is_class_literal(arg_nodes[2]):
            params = arg_expressions[1]
        elif len(arg_nodes) >= 2 and _is_class_literal(arg_nodes[1]):
            params = None
    elif len(arg_nodes) >= 2 and _is_class_literal(arg_nodes[1]):
        params = _positional_param_dict(arg_expressions[2:])
        positional_count = len(arg_expressions) - 2
    elif len(arg_nodes) >= 3 and _is_class_literal(arg_nodes[-1]):
        params = arg_expressions[1]

    ctx.diagnostics.record(
        node,
        supported=True,
        reason="lowered JdbcTemplate.queryForObject to SQLAlchemy Core scaffold",
        category="spring-jdbc-sqlalchemy",
        facts={"template_type": template_type, "method": "queryForObject"},
    )
    execute = _execute_expression(
        receiver,
        sql_node,
        params=params,
        positional_count=positional_count,
        ctx=ctx,
    )
    return f"{execute}.scalar_one()"


def _execute_expression(
    receiver: str,
    sql_node: JavaNode,
    *,
    params: str | None,
    positional_count: int,
    ctx: TranslationContext,
) -> str:
    ctx.diagnostics.imports.need_line("from sqlalchemy import text")
    connection = _connection_placeholder(receiver)
    text_call = _text_call(sql_node, positional_count, ctx)
    if params:
        return f"{connection}.execute({text_call}, {params})"
    return f"{connection}.execute({text_call})"


def _text_call(sql_node: JavaNode, positional_count: int, ctx: TranslationContext) -> str:
    from j2py.translate.expressions import translate_expression

    sql_expr = translate_expression(sql_node, ctx)
    literal = _literal_string(sql_expr)
    if literal is not None:
        if positional_count:
            literal = _rewrite_positional_placeholders(literal, positional_count)
        return f"text({literal!r})"
    return f"text({sql_expr})"


def _literal_string(sql_expr: str) -> str | None:
    try:
        value = ast.literal_eval(sql_expr)
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _rewrite_positional_placeholders(sql: str, count: int) -> str:
    rewritten = sql
    for index in range(1, count + 1):
        rewritten = rewritten.replace("?", f":p{index}", 1)
    return rewritten


def _positional_param_dict(args: list[str]) -> str | None:
    if not args:
        return None
    entries = [f"{f'p{index}'!r}: {arg}" for index, arg in enumerate(args, start=1)]
    return "{" + ", ".join(entries) + "}"


def _connection_placeholder(receiver: str) -> str:
    if receiver.startswith("self."):
        return f"self.{receiver.removeprefix('self.')}_connection"
    if receiver.isidentifier():
        return f"{receiver}_connection"
    name = translate_field_name(receiver.replace(".", "_"), snake_case=True)
    return f"{name}_connection"


def _has_row_mapper_or_callback(nodes: list[JavaNode]) -> bool:
    return any(
        child.type
        in {
            "lambda_expression",
            "method_reference",
            "object_creation_expression",
            "class_instance_creation_expression",
        }
        or "RowMapper" in child.text
        for node in nodes
        for child in node.walk()
    )


def _is_class_literal(node: JavaNode) -> bool:
    return node.type == "class_literal" or node.text.endswith(".class")


def _unsupported_row_mapper(node: JavaNode, ctx: TranslationContext) -> str:
    return _unsupported(
        node,
        ctx,
        reason="JdbcTemplate RowMapper/callback requires project row mapping",
    )


def _unsupported(node: JavaNode, ctx: TranslationContext, *, reason: str) -> str:
    ctx.diagnostics.record(
        node,
        supported=False,
        reason=reason,
        category="spring-jdbc-sqlalchemy-todo",
    )
    return f"__j2py_todo__({_ROW_MAPPER_TODO!r})"

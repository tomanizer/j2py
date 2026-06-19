"""Spring JDBC call lowering to SQLAlchemy Core scaffolding."""

from __future__ import annotations

import ast

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.java_types import java_expression_type, java_type_simple_name
from j2py.translate.jdbc_row_mapper import is_row_mapper_shape, lower_row_mapper
from j2py.translate.rules.naming import translate_field_name

_JDBC_TEMPLATE_TYPES = frozenset({"JdbcTemplate", "NamedParameterJdbcTemplate"})
_ROW_MAPPER_TODO = (
    "TODO(j2py): JdbcTemplate RowMapper/callback requires manual mapper port; "
    "lower to SQLAlchemy row mapping or a project DB facade"
)


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
    if method_name == "query":
        return _translate_query(
            node,
            template_type=template_type,
            receiver=receiver,
            arg_nodes=arg_nodes,
            arg_expressions=arg_expressions,
            ctx=ctx,
        )
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
    mapper_call = _translate_query_with_row_mapper(
        node,
        template_type=template_type,
        receiver=receiver,
        arg_nodes=arg_nodes,
        arg_expressions=arg_expressions,
        ctx=ctx,
        single=True,
    )
    if mapper_call is not None:
        return mapper_call
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


def _translate_query(
    node: JavaNode,
    *,
    template_type: str,
    receiver: str,
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    ctx: TranslationContext,
) -> str | None:
    if not arg_nodes:
        return _unsupported(node, ctx, reason="JdbcTemplate.query without SQL argument")
    mapper_call = _translate_query_with_row_mapper(
        node,
        template_type=template_type,
        receiver=receiver,
        arg_nodes=arg_nodes,
        arg_expressions=arg_expressions,
        ctx=ctx,
        single=False,
    )
    if mapper_call is not None:
        return mapper_call
    if _has_row_mapper_or_callback(arg_nodes[1:]):
        return _unsupported_row_mapper(node, ctx)
    return None


def _translate_query_with_row_mapper(
    node: JavaNode,
    *,
    template_type: str,
    receiver: str,
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    ctx: TranslationContext,
    single: bool,
) -> str | None:
    mapper_index = _row_mapper_arg_index(template_type, arg_nodes)
    if mapper_index is None:
        return None
    mapper = lower_row_mapper(arg_nodes[mapper_index], ctx)
    if mapper is None:
        return None
    _discard_lowered_anonymous_mapper_helper(
        arg_nodes[mapper_index],
        arg_expressions[mapper_index],
        ctx,
    )

    params, positional_count = _query_mapper_params(
        template_type,
        mapper_index,
        arg_expressions,
    )
    ctx.diagnostics.record(
        node,
        supported=True,
        reason=(
            "lowered JdbcTemplate RowMapper queryForObject to SQLAlchemy row mapping"
            if single
            else "lowered JdbcTemplate RowMapper query to SQLAlchemy row mapping"
        ),
        category="spring-jdbc-row-mapper",
        facts={
            "template_type": template_type,
            "mapper_kind": mapper.kind,
            **({"target_type": mapper.target_type} if mapper.target_type else {}),
        },
    )
    execute = _execute_expression(
        receiver,
        arg_nodes[0],
        params=params,
        positional_count=positional_count,
        ctx=ctx,
    )
    mappings = f"{execute}.mappings()"
    if single:
        return f"(lambda row: {mapper.expression})({mappings}.one())"
    return f"[{mapper.expression} for row in {mappings}]"


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


def _row_mapper_arg_index(template_type: str, arg_nodes: list[JavaNode]) -> int | None:
    if template_type == "NamedParameterJdbcTemplate":
        for index in (2, 1):
            if len(arg_nodes) > index and is_row_mapper_shape(arg_nodes[index]):
                return index
        return None
    for index, arg in enumerate(arg_nodes[1:], start=1):
        if is_row_mapper_shape(arg):
            return index
    return None


def _query_mapper_params(
    template_type: str,
    mapper_index: int,
    arg_expressions: list[str],
) -> tuple[str | None, int]:
    if template_type == "NamedParameterJdbcTemplate":
        if mapper_index == 2 and len(arg_expressions) >= 2:
            return arg_expressions[1], 0
        return None, 0
    params = _positional_param_dict(arg_expressions[mapper_index + 1 :])
    return params, len(arg_expressions) - mapper_index - 1


def _discard_lowered_anonymous_mapper_helper(
    mapper_node: JavaNode,
    mapper_expression: str,
    ctx: TranslationContext,
) -> None:
    if mapper_node.type != "object_creation_expression" or "class_body" not in {
        child.type for child in mapper_node.named_children
    }:
        return
    helper_name = mapper_expression.split("(", 1)[0]
    if not helper_name.startswith("_J2pyAnonymous"):
        return
    for index in range(len(ctx.pending_local_helpers) - 1, -1, -1):
        helper = ctx.pending_local_helpers[index]
        if any(f"class {helper_name}" in line for line in helper):
            del ctx.pending_local_helpers[index]
            return


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
        is_row_mapper_shape(child)
        or child.type == "class_instance_creation_expression"
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
        reason=(
            "JdbcTemplate RowMapper/callback requires manual mapper port; "
            "lower to SQLAlchemy row mapping or a project DB facade"
        ),
    )


def _unsupported(node: JavaNode, ctx: TranslationContext, *, reason: str) -> str:
    ctx.diagnostics.record(
        node,
        supported=False,
        reason=reason,
        category="spring-jdbc-sqlalchemy-todo",
    )
    todo = _ROW_MAPPER_TODO if "RowMapper/callback" in reason else f"TODO(j2py): {reason}"
    return f"__j2py_todo__({todo!r})"

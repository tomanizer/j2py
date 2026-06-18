"""RowMapper lowering helpers for Spring JDBC SQLAlchemy scaffolding."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.node_utils import first_child_by_type, unwrap_parens
from j2py.translate.rules.naming import translate_class_name

_RESULT_SET_GETTERS = frozenset(
    {
        "getString",
        "getInt",
        "getLong",
        "getBoolean",
        "getBigDecimal",
        "getDate",
        "getTimestamp",
    },
)


@dataclass(frozen=True)
class RowMapperLowering:
    """A RowMapper body rendered as a Python expression over ``row``."""

    expression: str
    kind: str
    target_type: str | None = None


def lower_row_mapper(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    row_name: str = "row",
) -> RowMapperLowering | None:
    """Return a deterministic RowMapper lowering when the mapper shape is supported."""

    inner = unwrap_parens(node)
    if inner.type == "lambda_expression":
        return _lower_lambda_mapper(inner, ctx, row_name=row_name)
    if inner.type == "object_creation_expression":
        bean_mapper = _lower_bean_property_constructor(inner, row_name=row_name)
        if bean_mapper is not None:
            return bean_mapper
        return _lower_anonymous_row_mapper(inner, ctx, row_name=row_name)
    if inner.type == "method_invocation":
        return _lower_bean_property_factory(inner, row_name=row_name)
    return None


def is_row_mapper_shape(node: JavaNode) -> bool:
    """Return whether ``node`` is some RowMapper-like argument, supported or not."""

    inner = unwrap_parens(node)
    if inner.type in {"lambda_expression", "method_reference"}:
        return True
    if inner.type == "object_creation_expression":
        type_node = inner.child_by_field("type")
        return type_node is not None and (
            "RowMapper" in type_node.text or "BeanPropertyRowMapper" in type_node.text
        )
    if inner.type == "method_invocation":
        receiver = inner.child_by_field("object")
        return receiver is not None and receiver.text == "BeanPropertyRowMapper"
    return False


def _lower_lambda_mapper(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    row_name: str,
) -> RowMapperLowering | None:
    params_node = node.child_by_field("parameters")
    body_node = node.child_by_field("body")
    if params_node is None or body_node is None or body_node.type == "block":
        return None

    params = _identifier_texts(params_node)
    if not params:
        return None
    expression = _lower_mapper_expression(
        body_node,
        ctx,
        row_name=row_name,
        result_set_names={params[0]},
    )
    if expression is None:
        return None
    return RowMapperLowering(expression=expression, kind="lambda")


def _lower_anonymous_row_mapper(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    row_name: str,
) -> RowMapperLowering | None:
    type_node = node.child_by_field("type")
    if type_node is None or "RowMapper" not in type_node.text:
        return None
    body_node = first_child_by_type(node, "class_body")
    if body_node is None:
        return None

    for method in body_node.named_children:
        if method.type != "method_declaration":
            continue
        name_node = method.child_by_field("name")
        if name_node is None or name_node.text != "mapRow":
            continue
        result_set_name = _result_set_parameter_name(method)
        if result_set_name is None:
            return None
        return_expr = _single_return_expression(method)
        if return_expr is None:
            return None
        expression = _lower_mapper_expression(
            return_expr,
            ctx,
            row_name=row_name,
            result_set_names={result_set_name},
        )
        if expression is None:
            return None
        return RowMapperLowering(
            expression=expression,
            kind="anonymous",
            target_type=_row_mapper_target(type_node.text),
        )
    return None


def _lower_bean_property_factory(
    node: JavaNode,
    *,
    row_name: str,
) -> RowMapperLowering | None:
    receiver = node.child_by_field("object")
    name_node = node.child_by_field("name")
    if receiver is None or receiver.text != "BeanPropertyRowMapper":
        return None
    if name_node is None or name_node.text != "newInstance":
        return None
    args = _argument_nodes(node)
    if len(args) != 1:
        return None
    target = _class_literal_name(args[0])
    if target is None:
        return None
    return RowMapperLowering(
        expression=f"{target}(**dict({row_name}))",
        kind="bean_property",
        target_type=target,
    )


def _lower_bean_property_constructor(
    node: JavaNode,
    *,
    row_name: str,
) -> RowMapperLowering | None:
    type_node = node.child_by_field("type")
    if type_node is None or "BeanPropertyRowMapper" not in type_node.text:
        return None
    args = _argument_nodes(node)
    if len(args) != 1:
        return None
    target = _class_literal_name(args[0])
    if target is None:
        return None
    return RowMapperLowering(
        expression=f"{target}(**dict({row_name}))",
        kind="bean_property",
        target_type=target,
    )


def _lower_mapper_expression(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    row_name: str,
    result_set_names: set[str],
) -> str | None:
    inner = unwrap_parens(node)
    getter = _result_set_getter_access(
        inner,
        row_name=row_name,
        result_set_names=result_set_names,
    )
    if getter is not None:
        return getter

    if inner.type == "object_creation_expression":
        type_node = inner.child_by_field("type")
        if type_node is None:
            return None
        args = []
        for arg in _argument_nodes(inner):
            lowered = _lower_mapper_expression(
                arg,
                ctx,
                row_name=row_name,
                result_set_names=result_set_names,
            )
            if lowered is None:
                return None
            args.append(lowered)
        return f"{translate_class_name(type_node.text.split('<', 1)[0])}({', '.join(args)})"

    if inner.type in {
        "decimal_integer_literal",
        "string_literal",
        "character_literal",
        "true",
        "false",
        "null_literal",
        "identifier",
        "field_access",
    }:
        from j2py.translate.expressions import translate_expression

        return translate_expression(inner, ctx)

    return None


def _result_set_getter_access(
    node: JavaNode,
    *,
    row_name: str,
    result_set_names: set[str],
) -> str | None:
    if node.type != "method_invocation":
        return None
    receiver = node.child_by_field("object")
    name_node = node.child_by_field("name")
    if receiver is None or name_node is None:
        return None
    if receiver.text not in result_set_names or name_node.text not in _RESULT_SET_GETTERS:
        return None
    args = _argument_nodes(node)
    if len(args) != 1:
        return None
    column = _string_literal_value(args[0])
    if column is None:
        return None
    return f"{row_name}[{column!r}]"


def _result_set_parameter_name(method: JavaNode) -> str | None:
    params = method.child_by_field("parameters")
    if params is None:
        return None
    for param in params.named_children:
        type_node = param.child_by_field("type")
        name_node = param.child_by_field("name")
        if type_node is None or name_node is None:
            continue
        if type_node.text.endswith("ResultSet"):
            return name_node.text
    return None


def _single_return_expression(method: JavaNode) -> JavaNode | None:
    body = method.child_by_field("body")
    if body is None:
        body = first_child_by_type(method, "block")
    if body is None:
        return None
    statements = [child for child in body.named_children if not is_comment(child)]
    if len(statements) != 1 or statements[0].type != "return_statement":
        return None
    return statements[0].named_children[0] if statements[0].named_children else None


def _argument_nodes(node: JavaNode) -> list[JavaNode]:
    args_node = first_child_by_type(node, "argument_list")
    if args_node is None:
        return []
    return [child for child in args_node.named_children if not is_comment(child)]


def _class_literal_name(node: JavaNode) -> str | None:
    if node.type != "class_literal":
        return None
    for child in node.named_children:
        if child.type in {"type_identifier", "scoped_type_identifier", "identifier"}:
            return translate_class_name(child.text)
    return None


def _string_literal_value(node: JavaNode) -> str | None:
    if node.type != "string_literal":
        return None
    try:
        value = ast.literal_eval(node.text)
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _identifier_texts(node: JavaNode) -> list[str]:
    return [child.text for child in node.walk() if child.type == "identifier"]


def _row_mapper_target(type_text: str) -> str | None:
    if "<" not in type_text or ">" not in type_text:
        return None
    inner = type_text.split("<", 1)[1].rsplit(">", 1)[0].strip()
    return translate_class_name(inner) if inner else None

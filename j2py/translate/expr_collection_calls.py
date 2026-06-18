"""Collection-like Java method call lowering helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.java_types import java_type_of_value
from j2py.translate.rules.types import (
    is_api_get_receiver_type,
    is_indexed_predicate_get_receiver_java_type,
    is_indexed_predicate_get_receiver_type,
    is_map_like_type,
)


def translate_collection_method_invocation(
    node: JavaNode,
    *,
    method_name: str,
    receiver: str,
    receiver_nodes: list[JavaNode],
    raw_receiver: str,
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    if method_name == "add" and receiver:
        from j2py.translate.expr_types import _expression_py_type, _is_list_type

        receiver_type = _expression_py_type(receiver_nodes[0], ctx) if receiver_nodes else None
        if receiver_type is not None and _is_list_type(receiver_type):
            return f"{receiver}.append({args})"

    if method_name == "get" and receiver and args:
        return _translate_get_invocation(
            node,
            receiver=receiver,
            receiver_nodes=receiver_nodes,
            raw_receiver=raw_receiver,
            arg_nodes=arg_nodes,
            arg_expressions=arg_expressions,
            args=args,
            ctx=ctx,
        )

    return None


def _translate_get_invocation(
    node: JavaNode,
    *,
    receiver: str,
    receiver_nodes: list[JavaNode],
    raw_receiver: str,
    arg_nodes: list[JavaNode],
    arg_expressions: list[str],
    args: str,
    ctx: TranslationContext,
) -> str:
    if len(arg_expressions) != 1:
        return f"{receiver}.get({args})"

    if receiver_nodes and receiver_nodes[0].type == "super":
        return f"{receiver}.get({args})"

    if receiver_nodes and _receiver_get_method_would_collide(receiver_nodes[0], ctx):
        return f"{receiver}.get({args})"

    typed_result = _translate_typed_get_invocation(receiver, receiver_nodes, args, ctx)
    if typed_result is not None:
        return typed_result

    if raw_receiver.split(".")[-1][:1].isupper():
        return f"{receiver}.get({args})"
    ctx.diagnostics.record(
        node,
        supported=False,
        reason="ambiguous get invocation requires receiver collection type",
    )
    return f"{receiver}.get({args})"


def _receiver_get_method_would_collide(
    receiver_node: JavaNode,
    ctx: TranslationContext,
) -> bool:
    from j2py.translate.expr_types import _is_this_receiver

    return (
        receiver_node.type in {"this", "field_access"}
        and "get" in ctx.class_method_return_types
        and _is_this_receiver(receiver_node)
    )


def _translate_typed_get_invocation(
    receiver: str,
    receiver_nodes: list[JavaNode],
    args: str,
    ctx: TranslationContext,
) -> str | None:
    from j2py.translate.expr_types import _expression_py_type, _is_list_type

    receiver_type = _expression_py_type(receiver_nodes[0], ctx) if receiver_nodes else None
    if receiver_type is not None and _is_list_type(receiver_type):
        return f"{receiver}[{args}]"
    if receiver_type is not None and is_map_like_type(receiver_type):
        return f"{receiver}.get({args})"
    if receiver_type is not None and is_api_get_receiver_type(receiver_type):
        return f"{receiver}.get({args})"
    if receiver_type is not None and is_indexed_predicate_get_receiver_type(receiver_type):
        return f"{receiver}.get({args})"
    if receiver_nodes:
        java_receiver_type = java_type_of_value(receiver_nodes[0], ctx)
        if java_receiver_type is not None and is_indexed_predicate_get_receiver_java_type(
            java_receiver_type,
        ):
            return f"{receiver}.get({args})"
    return None

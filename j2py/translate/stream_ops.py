"""Stream intermediate-operation lowering helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeAlias

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_lambdas import _lambda_body_expression, _method_reference_target
from j2py.translate.rules.naming import translate_field_name, translate_method_name

IntermediateHandler: TypeAlias = Callable[
    [JavaNode, JavaNode | None, "StreamPipelineState", TranslationContext],
    "StreamPipelineState | None",
]


@dataclass(frozen=True)
class StreamPipelineState:
    item_name: str
    current_expr: str
    loop_clauses: list[tuple[str, str]]
    filters: list[str]
    post_ops: list[tuple[str, str | None]]


def initial_stream_state(source: str, item_name: str) -> StreamPipelineState:
    return StreamPipelineState(
        item_name=item_name,
        current_expr=item_name,
        loop_clauses=[(item_name, source)],
        filters=[],
        post_ops=[],
    )


def translate_stream_intermediates(
    node: JavaNode,
    operations: list[tuple[str, JavaNode | None]],
    state: StreamPipelineState,
    ctx: TranslationContext,
) -> StreamPipelineState | None:
    current_state = state
    for operation, arg in operations:
        handler = _INTERMEDIATE_HANDLERS.get(operation)
        if handler is None:
            _record_unsupported_intermediate(node, operation, ctx)
            return None
        next_state = handler(node, arg, current_state, ctx)
        if next_state is None:
            return None
        current_state = next_state

    return current_state


def _translate_map_intermediate(
    node: JavaNode,
    arg: JavaNode | None,
    state: StreamPipelineState,
    ctx: TranslationContext,
) -> StreamPipelineState | None:
    if arg is None:
        _record_unsupported_intermediate(node, "map", ctx)
        return None
    if _reject_after_post_ops(node, "map", state.post_ops, ctx):
        return None
    mapped = _stream_map_expression(arg, state.item_name, ctx)
    if mapped is None:
        return None
    return replace(state, current_expr=mapped)


def _translate_filter_intermediate(
    node: JavaNode,
    arg: JavaNode | None,
    state: StreamPipelineState,
    ctx: TranslationContext,
) -> StreamPipelineState | None:
    if arg is None:
        _record_unsupported_intermediate(node, "filter", ctx)
        return None
    if _reject_after_post_ops(node, "filter", state.post_ops, ctx):
        return None
    predicate = _stream_filter_expression(arg, state.current_expr, state.item_name, ctx)
    if predicate is None:
        return None
    return replace(state, filters=[*state.filters, predicate])


def _translate_flatmap_intermediate(
    node: JavaNode,
    arg: JavaNode | None,
    state: StreamPipelineState,
    ctx: TranslationContext,
) -> StreamPipelineState | None:
    if arg is None:
        _record_unsupported_intermediate(node, "flatMap", ctx)
        return None
    if _reject_after_post_ops(node, "flatMap", state.post_ops, ctx):
        return None
    binding = _stream_flatmap_binding(arg, state.item_name, state.current_expr, ctx)
    if binding is None:
        _record_unsupported_intermediate(node, "flatMap", ctx)
        return None
    inner_name, inner_iterable = binding
    return replace(
        state,
        item_name=inner_name,
        current_expr=inner_name,
        loop_clauses=[*state.loop_clauses, (inner_name, inner_iterable)],
    )


def _translate_distinct_intermediate(
    node: JavaNode,
    arg: JavaNode | None,
    state: StreamPipelineState,
    ctx: TranslationContext,
) -> StreamPipelineState | None:
    return replace(state, post_ops=[*state.post_ops, ("distinct", None)])


def _translate_sorted_intermediate(
    node: JavaNode,
    arg: JavaNode | None,
    state: StreamPipelineState,
    ctx: TranslationContext,
) -> StreamPipelineState | None:
    if arg is not None and state.current_expr != state.item_name:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="sorted comparator after map requires mapped-value translation",
        )
        return None
    sorted_key = _stream_map_expression(arg, state.item_name, ctx) if arg is not None else None
    return replace(state, post_ops=[*state.post_ops, ("sorted", sorted_key)])


def _record_unsupported_intermediate(
    node: JavaNode,
    operation: str,
    ctx: TranslationContext,
) -> None:
    ctx.diagnostics.record(
        node,
        supported=False,
        reason=f"unsupported stream intermediate: {operation}",
    )


def _reject_after_post_ops(
    node: JavaNode,
    operation: str,
    post_ops: list[tuple[str, str | None]],
    ctx: TranslationContext,
) -> bool:
    if not post_ops:
        return False
    ctx.diagnostics.record(
        node,
        supported=False,
        reason=(f"stream {operation} after sorted/distinct requires order-preserving translation"),
    )
    return True


def _stream_comprehension_suffix(
    loop_clauses: list[tuple[str, str]],
    filters: list[str],
) -> str:
    loops = " ".join(f"for {var} in {iterable}" for var, iterable in loop_clauses)
    if filters:
        return f"{loops} if {' and '.join(filters)}"
    return loops


def _stream_flatmap_inner_item_name(outer_item_name: str, ctx: TranslationContext) -> str:
    for stem in (f"{outer_item_name}_item", f"{outer_item_name}_element", "item"):
        name = translate_field_name(stem, snake_case=ctx.cfg.snake_case_fields)
        if name != outer_item_name and name.isidentifier():
            return name
    return "item"


def _stream_flatmap_binding(
    arg: JavaNode,
    outer_item_name: str,
    current_expr: str,
    ctx: TranslationContext,
) -> tuple[str, str] | None:
    """Return (inner_loop_var, inner_iterable) for a supported flatMap mapper.

    Supports ``Type::stream`` instance-method references on stream elements
    (e.g. ``List::stream``), plus simple one-argument lambdas whose body
    returns a stream or iterable-like value. Bound references such as
    ``myList::stream`` are rejected so we fall back to the general translated
    chain.
    """
    if arg.type == "lambda_expression":
        inner_name = _stream_flatmap_inner_item_name(outer_item_name, ctx)
        inner_iterable = _lambda_body_expression(arg, ctx, default_alias=current_expr)
        if inner_iterable is None:
            return None
        inner_iterable = _strip_terminal_stream_call(inner_iterable)
        return inner_name, inner_iterable

    if arg.type == "method_reference":
        named = arg.named_children
        if len(named) >= 2 and named[-1].text == "stream" and named[0].text[:1].isupper():
            inner_name = _stream_flatmap_inner_item_name(outer_item_name, ctx)
            inner_iterable = current_expr
            return inner_name, inner_iterable
    return None


def _strip_terminal_stream_call(expression: str) -> str:
    suffix = ".stream()"
    if expression.endswith(suffix):
        return expression[: -len(suffix)]
    return expression


def _apply_stream_post_ops(
    base: str,
    post_ops: list[tuple[str, str | None]],
    item_name: str,
) -> str:
    for operation, key in post_ops:
        if operation == "sorted":
            base = f"sorted({base}, key=lambda {item_name}: {key})" if key else f"sorted({base})"
        elif operation == "distinct":
            base = f"list(dict.fromkeys({base}))"
    return base


def _stream_map_expression(arg: JavaNode, item_name: str, ctx: TranslationContext) -> str | None:
    if arg.type == "lambda_expression":
        return _lambda_body_expression(arg, ctx, default_alias=item_name)
    if arg.type == "method_reference":
        named = arg.named_children
        if len(named) == 1 and arg.children[-1].text == "new":
            return f"{_method_reference_target(named[0], ctx)}({item_name})"
        if len(named) >= 2 and named[0].text[:1].isupper():
            method_name = translate_method_name(
                named[-1].text,
                snake_case=ctx.cfg.snake_case_methods,
            )
            return f"{item_name}.{method_name}()"
        if len(named) >= 2:
            target = _method_reference_target(named[0], ctx)
            method_name = translate_method_name(
                named[-1].text,
                snake_case=ctx.cfg.snake_case_methods,
            )
            return f"{target}.{method_name}({item_name})"
    return None


def _stream_filter_expression(
    arg: JavaNode,
    current_expr: str,
    item_name: str,
    ctx: TranslationContext,
) -> str | None:
    if arg.type == "lambda_expression":
        return _lambda_body_expression(arg, ctx, default_alias=current_expr)
    if arg.type == "method_reference":
        mapped = _stream_map_expression(arg, item_name, ctx)
        return mapped
    return None


_INTERMEDIATE_HANDLERS: dict[str, IntermediateHandler] = {
    "distinct": _translate_distinct_intermediate,
    "filter": _translate_filter_intermediate,
    "flatMap": _translate_flatmap_intermediate,
    "map": _translate_map_intermediate,
    "sorted": _translate_sorted_intermediate,
}

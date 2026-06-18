"""Stream terminal collector lowering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_lambdas import _lambda_body_expression
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.stream_ops import (
    StreamPipelineState,
    _apply_stream_post_ops,
    _stream_comprehension_suffix,
    _stream_map_expression,
)

StreamCollectorKind = Literal["to_list", "to_set", "joining", "grouping", "to_map"]


@dataclass(frozen=True)
class StreamCollector:
    kind: StreamCollectorKind
    arg_count: int | None


def stream_collector_from_terminal(
    node: JavaNode,
    terminal_name: str,
    terminal_arg: JavaNode | None,
    ctx: TranslationContext,
) -> StreamCollector | None:
    kind = _stream_collector_kind(terminal_name, terminal_arg)
    if kind is None:
        return None

    arg_count = _method_invocation_arg_count(terminal_arg)
    if not _collector_arity_is_supported(node, kind, arg_count, ctx):
        return None
    return StreamCollector(kind=kind, arg_count=arg_count)


def translate_stream_terminal(
    node: JavaNode,
    *,
    source: str,
    state: StreamPipelineState,
    collector: StreamCollector,
    terminal_arg: JavaNode | None,
    ctx: TranslationContext,
) -> str | None:
    if collector.kind in {"grouping", "to_map"} and state.post_ops:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="collector helper with sorted/distinct requires order-preserving translation",
        )
        return None

    if collector.kind == "grouping":
        return _translate_grouping_collector(node, source, state, terminal_arg, collector, ctx)

    if collector.kind == "to_map":
        return _translate_to_map_collector(node, source, state, terminal_arg, ctx)

    comp_suffix = _stream_comprehension_suffix(state.loop_clauses, state.filters)
    if collector.kind == "to_set":
        if any(operation == "sorted" for operation, _key in state.post_ops):
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="sorted before Collectors.toSet requires order-discarding review",
            )
            return None
        base = f"{{{state.current_expr} {comp_suffix}}}"
    elif collector.kind == "joining":
        delim = '""'
        joining_args = _collector_invocation_arguments(terminal_arg)
        if joining_args:
            # First arg is usually the delimiter string literal or expr.
            delim = translate_expression(joining_args[0], ctx)
        base = f"({state.current_expr} {comp_suffix})"
        base = _apply_stream_post_ops(base, state.post_ops, state.item_name)
        return f"{delim}.join({base})"
    else:
        base = f"[{state.current_expr} {comp_suffix}]"

    return _apply_stream_post_ops(base, state.post_ops, state.item_name)


def _stream_collector_kind(
    terminal_name: str,
    terminal_arg: JavaNode | None,
) -> StreamCollectorKind | None:
    if terminal_name == "toList" or (
        terminal_name == "collect" and _is_collectors_to_list(terminal_arg)
    ):
        return "to_list"
    if terminal_name == "collect" and _is_collectors_to_set(terminal_arg):
        return "to_set"
    if terminal_name == "collect" and _is_collectors_joining(terminal_arg):
        return "joining"
    if terminal_name == "collect" and _is_collectors_grouping_by(terminal_arg):
        return "grouping"
    if terminal_name == "collect" and _is_collectors_to_map(terminal_arg):
        return "to_map"
    return None


def _collector_arity_is_supported(
    node: JavaNode,
    kind: StreamCollectorKind,
    arg_count: int | None,
    ctx: TranslationContext,
) -> bool:
    if kind in {"to_list", "to_set"} and arg_count not in {None, 0}:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="collector without arguments received unexpected arguments",
        )
        return False
    if kind == "joining" and arg_count not in {0, 1}:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.joining with prefix/suffix requires manual translation",
        )
        return False
    if kind == "grouping" and arg_count not in {1, 2}:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.groupingBy with downstream collector requires manual translation",
        )
        return False
    if kind == "to_map" and arg_count != 2:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.toMap with merge/supplier arguments requires manual translation",
        )
        return False
    return True


def _translate_grouping_collector(
    node: JavaNode,
    source: str,
    state: StreamPipelineState,
    terminal_arg: JavaNode | None,
    collector: StreamCollector,
    ctx: TranslationContext,
) -> str | None:
    if not ctx.allow_local_helpers:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.groupingBy requires local helper scope",
        )
        return None
    if state.current_expr != state.item_name:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.groupingBy after map requires mapped-value helper",
        )
        return None

    grouping_args = _collector_invocation_arguments(terminal_arg)
    if collector.arg_count == 2:
        downstream = grouping_args[1]
        if not _is_collectors_mapping_to_list_identity(downstream, state.item_name, ctx):
            ctx.diagnostics.record(
                node,
                supported=False,
                reason=(
                    "Collectors.groupingBy with downstream collector requires manual translation"
                ),
            )
            return None
    key_mapper = state.item_name
    if grouping_args:
        key_arg = grouping_args[0]
        k = _stream_map_expression(key_arg, state.item_name, ctx)
        if k:
            key_mapper = k
    filter_conds = " and ".join(state.filters) if state.filters else None
    helper_id = len(ctx.pending_local_helpers) + 1
    helper_name = f"_j2py_groupby_{helper_id}"
    helper_lines = [
        f"        def {helper_name}(source):",
        "            from collections import defaultdict",
        "            groups = defaultdict(list)",
        f"            for {state.item_name} in source:",
    ]
    if filter_conds:
        helper_lines.append(f"                if not ({filter_conds}): continue")
    if state.current_expr != state.item_name:
        helper_lines.append(f"                mapped = {state.current_expr}")
        val = "mapped"
    else:
        val = state.item_name
    helper_lines.append(f"                key = {key_mapper}")
    helper_lines.append(f"                groups[key].append({val})")
    helper_lines.append("            return dict(groups)")
    ctx.pending_local_helpers.append(helper_lines)
    return f"{helper_name}({source})"


def _translate_to_map_collector(
    node: JavaNode,
    source: str,
    state: StreamPipelineState,
    terminal_arg: JavaNode | None,
    ctx: TranslationContext,
) -> str | None:
    if not ctx.allow_local_helpers:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.toMap requires local helper scope",
        )
        return None
    if state.current_expr != state.item_name:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.toMap after map requires mapped-value helper",
        )
        return None

    key_mapper = state.item_name
    value_mapper = state.current_expr
    if terminal_arg is not None and len(terminal_arg.named_children) >= 2:
        key_arg = terminal_arg.named_children[0]
        val_arg = terminal_arg.named_children[1]
        k = _stream_map_expression(key_arg, state.item_name, ctx)
        if k:
            key_mapper = k
        v = _stream_map_expression(val_arg, state.item_name, ctx)
        if v:
            value_mapper = v
    filter_conds = " and ".join(state.filters) if state.filters else None
    helper_id = len(ctx.pending_local_helpers) + 1
    helper_name = f"_j2py_to_map_{helper_id}"
    helper_lines = [
        f"        def {helper_name}(source):",
        "            result = {}",
        f"            for {state.item_name} in source:",
    ]
    if filter_conds:
        helper_lines.append(f"                if not ({filter_conds}): continue")
    if state.current_expr != state.item_name:
        helper_lines.append(f"                mapped = {state.current_expr}")
        # value_mapper may reference the original item_name; use translated expression.
    helper_lines.append(f"                key = {key_mapper}")
    helper_lines.append(f"                result[key] = {value_mapper}")
    helper_lines.append("            return result")
    ctx.pending_local_helpers.append(helper_lines)
    return f"{helper_name}({source})"


def _is_collectors_to_list(node: JavaNode | None) -> bool:
    return _is_collectors_call(node, "toList")


def _is_collectors_to_set(node: JavaNode | None) -> bool:
    return _is_collectors_call(node, "toSet")


def _is_collectors_joining(node: JavaNode | None) -> bool:
    return _is_collectors_call(node, "joining")


def _is_collectors_grouping_by(node: JavaNode | None) -> bool:
    return _is_collectors_call(node, "groupingBy")


def _is_collectors_mapping(node: JavaNode | None) -> bool:
    return _is_collectors_call(node, "mapping")


def _is_collectors_to_map(node: JavaNode | None) -> bool:
    return _is_collectors_call(node, "toMap")


def _is_collectors_call(node: JavaNode | None, method_name: str) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == method_name
    )


def _is_stream_identity_mapper(
    arg: JavaNode,
    item_name: str,
    ctx: TranslationContext,
) -> bool:
    if arg.type == "lambda_expression":
        mapped = _lambda_body_expression(arg, ctx, default_alias=item_name)
        return mapped == item_name
    return _is_function_identity(arg)


def _is_function_identity(arg: JavaNode) -> bool:
    if arg.type == "method_invocation":
        receiver = arg.child_by_field("object")
        name = arg.child_by_field("name")
        return (
            receiver is not None
            and receiver.text == "Function"
            and name is not None
            and name.text == "identity"
            and _method_invocation_arg_count(arg) == 0
        )
    if arg.type == "method_reference":
        named = arg.named_children
        return len(named) >= 2 and named[0].text == "Function" and named[-1].text == "identity"
    return False


def _is_collectors_mapping_to_list_identity(
    node: JavaNode,
    item_name: str,
    ctx: TranslationContext,
) -> bool:
    """True for Collectors.mapping(identity, Collectors.toList())."""
    if not _is_collectors_mapping(node):
        return False
    mapping_args = _collector_invocation_arguments(node)
    if len(mapping_args) != 2:
        return False
    mapper, downstream = mapping_args
    if not _is_collectors_to_list(downstream):
        return False
    return _is_stream_identity_mapper(mapper, item_name, ctx)


def _method_invocation_arg_count(node: JavaNode | None) -> int | None:
    if node is None or node.type != "method_invocation":
        return None
    args_node = node.child_by_field("arguments") or first_child_by_type(node, "argument_list")
    if args_node is None:
        return 0
    return len(_argument_list_nodes(args_node))


def _collector_invocation_arguments(node: JavaNode | None) -> list[JavaNode]:
    if node is None or node.type != "method_invocation":
        return []
    args_node = node.child_by_field("arguments") or first_child_by_type(node, "argument_list")
    if args_node is None:
        return []
    return _argument_list_nodes(args_node)


def _argument_list_nodes(args_node: JavaNode) -> list[JavaNode]:
    return [child for child in args_node.named_children if not is_comment(child)]

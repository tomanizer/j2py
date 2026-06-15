"""Stream pipeline expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_lambdas import _lambda_body_expression, _method_reference_target
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_field_name, translate_method_name


def _translate_stream_pipeline(node: JavaNode, ctx: TranslationContext) -> str | None:
    """Translate simple-to-medium stream pipelines to Python comps or small helpers.

    Hybrid policy (addressing plan open question): rewrite to clean, reviewable
    Python (list/set comps, .join, or small accumulation helpers) for common
    cases where the mapping is direct and doesn't obscure the original logic.
    For complex/unsupported intermediates (custom flatMap mappers, custom
    collectors, reduce, etc.) we fall back to the general translated chain so
    the intentional "streamy" structure remains visible to reviewers. This keeps
    line-level correspondence and avoids over-Pythonification.
    """
    chain = _stream_chain(node)
    if chain is None:
        return None

    source_node, operations = chain
    if not operations or operations[-1][0] not in {"collect", "toList"}:
        return None

    terminal_name, terminal_arg = operations[-1]
    is_to_list = terminal_name == "toList" or (
        terminal_name == "collect" and _is_collectors_to_list(terminal_arg)
    )
    is_to_set = terminal_name == "collect" and _is_collectors_to_set(terminal_arg)
    is_joining = terminal_name == "collect" and _is_collectors_joining(terminal_arg)
    is_grouping = terminal_name == "collect" and _is_collectors_grouping_by(terminal_arg)
    is_to_map = terminal_name == "collect" and _is_collectors_to_map(terminal_arg)
    if not (is_to_list or is_to_set or is_joining or is_grouping or is_to_map):
        return None

    collector_arg_count = _method_invocation_arg_count(terminal_arg)
    if (is_to_list or is_to_set) and collector_arg_count not in {None, 0}:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="collector without arguments received unexpected arguments",
        )
        return None
    if is_joining and collector_arg_count not in {0, 1}:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.joining with prefix/suffix requires manual translation",
        )
        return None
    if is_grouping and collector_arg_count not in {1, 2}:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.groupingBy with downstream collector requires manual translation",
        )
        return None
    if is_to_map and collector_arg_count != 2:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="Collectors.toMap with merge/supplier arguments requires manual translation",
        )
        return None

    source = translate_expression(source_node, ctx)
    item_name = _stream_item_name(source, ctx)
    loop_clauses: list[tuple[str, str]] = [(item_name, source)]
    current_expr = item_name
    filters: list[str] = []
    post_ops: list[tuple[str, str | None]] = []
    for operation, arg in operations[:-1]:
        if operation == "map" and arg is not None:
            if post_ops:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=(
                        f"stream {operation} after sorted/distinct requires "
                        "order-preserving translation"
                    ),
                )
                return None
            mapped = _stream_map_expression(arg, item_name, ctx)
            if mapped is None:
                return None
            current_expr = mapped
            continue
        if operation == "filter" and arg is not None:
            if post_ops:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=(
                        f"stream {operation} after sorted/distinct requires "
                        "order-preserving translation"
                    ),
                )
                return None
            predicate = _stream_filter_expression(arg, current_expr, item_name, ctx)
            if predicate is None:
                return None
            filters.append(predicate)
            continue
        if operation == "flatMap" and arg is not None:
            if post_ops:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=(
                        f"stream {operation} after sorted/distinct requires "
                        "order-preserving translation"
                    ),
                )
                return None
            binding = _stream_flatmap_binding(arg, item_name, current_expr, ctx)
            if binding is None:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason="unsupported stream intermediate: flatMap",
                )
                return None
            inner_name, inner_iterable = binding
            loop_clauses.append((inner_name, inner_iterable))
            item_name = inner_name
            current_expr = inner_name
            continue
        if operation == "distinct":
            post_ops.append(("distinct", None))
            continue
        if operation == "sorted":
            sorted_key = None
            if arg is not None:
                if current_expr != item_name:
                    ctx.diagnostics.record(
                        node,
                        supported=False,
                        reason="sorted comparator after map requires mapped-value translation",
                    )
                    return None
                k = _stream_map_expression(arg, item_name, ctx)
                if k:
                    sorted_key = k
            post_ops.append(("sorted", sorted_key))
            continue
        ctx.diagnostics.record(
            node,
            supported=False,
            reason=f"unsupported stream intermediate: {operation}",
        )
        return None

    if (is_grouping or is_to_map) and post_ops:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="collector helper with sorted/distinct requires order-preserving translation",
        )
        return None

    if is_grouping:
        if not ctx.allow_local_helpers:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="Collectors.groupingBy requires local helper scope",
            )
            return None
        if current_expr != item_name:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="Collectors.groupingBy after map requires mapped-value helper",
            )
            return None
        # Phase 3 basic support for groupingBy using helper + defaultdict (per plan)
        # key mapper from first arg to groupingBy; value is the post-map item
        grouping_args = _collector_invocation_arguments(terminal_arg)
        if collector_arg_count == 2:
            downstream = grouping_args[1]
            if not _is_collectors_mapping_to_list_identity(downstream, item_name, ctx):
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=(
                        "Collectors.groupingBy with downstream collector "
                        "requires manual translation"
                    ),
                )
                return None
        key_mapper = item_name
        if grouping_args:
            key_arg = grouping_args[0]
            k = _stream_map_expression(key_arg, item_name, ctx)
            if k:
                key_mapper = k
        filter_conds = " and ".join(filters) if filters else None
        helper_id = len(ctx.pending_local_helpers) + 1
        helper_name = f"_j2py_groupby_{helper_id}"
        helper_lines = [
            f"        def {helper_name}(source):",
            "            from collections import defaultdict",
            "            groups = defaultdict(list)",
            f"            for {item_name} in source:",
        ]
        if filter_conds:
            helper_lines.append(f"                if not ({filter_conds}): continue")
        if current_expr != item_name:
            helper_lines.append(f"                mapped = {current_expr}")
            val = "mapped"
        else:
            val = item_name
        helper_lines.append(f"                key = {key_mapper}")
        helper_lines.append(f"                groups[key].append({val})")
        helper_lines.append("            return dict(groups)")
        ctx.pending_local_helpers.append(helper_lines)
        return f"{helper_name}({source})"

    if is_to_map:
        if not ctx.allow_local_helpers:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="Collectors.toMap requires local helper scope",
            )
            return None
        if current_expr != item_name:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="Collectors.toMap after map requires mapped-value helper",
            )
            return None
        # Phase 3 simple toMap support (dict via helper, like groupingBy).
        # (dict-comp for very simple cases could be added later)
        key_mapper = item_name
        value_mapper = current_expr
        if terminal_arg is not None and len(terminal_arg.named_children) >= 2:
            key_arg = terminal_arg.named_children[0]
            val_arg = terminal_arg.named_children[1]
            k = _stream_map_expression(key_arg, item_name, ctx)
            if k:
                key_mapper = k
            v = _stream_map_expression(val_arg, item_name, ctx)
            if v:
                value_mapper = v
        filter_conds = " and ".join(filters) if filters else None
        helper_id = len(ctx.pending_local_helpers) + 1
        helper_name = f"_j2py_to_map_{helper_id}"
        helper_lines = [
            f"        def {helper_name}(source):",
            "            result = {}",
            f"            for {item_name} in source:",
        ]
        if filter_conds:
            helper_lines.append(f"                if not ({filter_conds}): continue")
        if current_expr != item_name:
            helper_lines.append(f"                mapped = {current_expr}")
            # value_mapper may reference the original item_name; use translated
        helper_lines.append(f"                key = {key_mapper}")
        helper_lines.append(f"                result[key] = {value_mapper}")
        helper_lines.append("            return result")
        ctx.pending_local_helpers.append(helper_lines)
        return f"{helper_name}({source})"

    comp_suffix = _stream_comprehension_suffix(loop_clauses, filters)
    if is_to_set:
        if any(operation == "sorted" for operation, _key in post_ops):
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="sorted before Collectors.toSet requires order-discarding review",
            )
            return None
        base = f"{{{current_expr} {comp_suffix}}}"
    elif is_joining:
        # Basic joining support (delimiter only for phase 1; prefix/suffix fall to general)
        delim = '""'
        joining_args = _collector_invocation_arguments(terminal_arg)
        if joining_args:
            # First arg is usually the delimiter string literal or expr
            delim = translate_expression(joining_args[0], ctx)
        base = f"({current_expr} {comp_suffix})"
        base = _apply_stream_post_ops(base, post_ops, item_name)
        return f"{delim}.join({base})"
    else:
        base = f"[{current_expr} {comp_suffix}]"

    return _apply_stream_post_ops(base, post_ops, item_name)


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
    (e.g. ``List::stream``). Bound references such as ``myList::stream`` are
    rejected so we fall back to the general translated chain.
    """
    if arg.type != "method_reference":
        return None
    named = arg.named_children
    if len(named) >= 2 and named[-1].text == "stream" and named[0].text[:1].isupper():
        inner_name = _stream_flatmap_inner_item_name(outer_item_name, ctx)
        inner_iterable = current_expr if current_expr != outer_item_name else outer_item_name
        return inner_name, inner_iterable
    return None


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


def _stream_chain(node: JavaNode) -> tuple[JavaNode, list[tuple[str, JavaNode | None]]] | None:
    if node.type != "method_invocation":
        return None
    receiver = node.child_by_field("object")
    name_node = node.child_by_field("name")
    args_node = node.child_by_field("arguments") or first_child_by_type(node, "argument_list")
    if receiver is None or name_node is None:
        return None

    method_name = name_node.text
    arg = (
        args_node.named_children[0] if args_node is not None and args_node.named_children else None
    )
    if method_name == "stream":
        return receiver, []

    previous = _stream_chain(receiver)
    if previous is None:
        return None
    source, operations = previous
    return source, [*operations, (method_name, arg)]


def _is_collectors_to_list(node: JavaNode | None) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == "toList"
    )


def _is_collectors_to_set(node: JavaNode | None) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == "toSet"
    )


def _is_collectors_joining(node: JavaNode | None) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == "joining"
    )


def _is_collectors_grouping_by(node: JavaNode | None) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == "groupingBy"
    )


def _is_collectors_mapping(node: JavaNode | None) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == "mapping"
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


def _is_collectors_to_map(node: JavaNode | None) -> bool:
    if node is None or node.type != "method_invocation":
        return False
    receiver = node.child_by_field("object")
    name = node.child_by_field("name")
    return (
        receiver is not None
        and receiver.text == "Collectors"
        and name is not None
        and name.text == "toMap"
    )


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


def _stream_item_name(source: str, ctx: TranslationContext) -> str:
    base = _stream_source_base_name(source)

    # Common collection variable names that are plurals (or singular-looking but used
    # for lists). The previous heuristic turned "status"->"statu", "address"->"addres",
    # "statuses"->"statuse", "classes"->"classe" etc. Use explicit map + safer stripping.
    _PLURAL_FIXES = {
        "statuses": "status",
        "status": "status",
        "addresses": "address",
        "address": "address",
        "classes": "class",
        "class": "class",  # e.g. List<Class<?>>
        "entries": "entry",
        "interfaces": "interface",
        "boxes": "box",
        "types": "type",
        "cases": "case",
        "values": "value",
    }
    if base in _PLURAL_FIXES:
        base = _PLURAL_FIXES[base]
    elif base.endswith("ies") and len(base) > 3:
        base = f"{base[:-3]}y"
    elif base.endswith("es") and len(base) > 2:
        base = base[:-2]
    elif base.endswith("s") and len(base) > 1:
        base = base[:-1]

    if not base or len(base) < 2:
        base = "item"
    name = translate_field_name(base, snake_case=ctx.cfg.snake_case_fields)
    if not name.isidentifier():
        return "item"
    return name


def _stream_source_base_name(source: str) -> str:
    base = source.rsplit(".", 1)[-1].strip()
    while base.endswith("()"):
        base = base[:-2]
    if base.startswith("get_"):
        base = base[4:]
        if "_" in base:
            base = base.rsplit("_", 1)[-1]
    base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)
    return base.strip("_")


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

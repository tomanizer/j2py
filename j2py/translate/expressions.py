"""Expression emission for the rule-based skeleton translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import PatternBinding, TranslationContext
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.literals import (
    java_string_literal_value,
    translate_literal,
    translate_string_literal,
)
from j2py.translate.rules.naming import (
    translate_attribute_method_name,
    translate_class_name,
    translate_field_name,
    translate_method_name,
)
from j2py.translate.rules.types import (
    element_type_from_container,
    java_default_value,
    translate_type,
)

if TYPE_CHECKING:
    from j2py.translate.classes import FieldInfo


def translate_expression(node: JavaNode | None, ctx: TranslationContext) -> str:
    if node is None:
        return "None"

    if node.type in {
        "decimal_integer_literal",
        "hex_integer_literal",
        "binary_integer_literal",
        "octal_integer_literal",
        "decimal_floating_point_literal",
        "true",
        "false",
        "null_literal",
        "character_literal",
    }:
        return translate_literal(node.text, ctx.cfg)

    if node.type == "string_literal":
        return translate_string_literal(node.text)

    if node.type == "identifier":
        return _translate_identifier(node.text, ctx)

    if node.type in {"type_identifier", "scoped_type_identifier"}:
        return translate_class_name(node.text)

    if node.type in {"boolean_type", "integral_type", "floating_point_type", "void_type"}:
        return translate_type(node.text, ctx.cfg)

    if node.type == "this":
        return "self"

    if node.type == "super":
        ctx.diagnostics.record(node, supported=True, reason="translated super expression")
        return "super()"

    if node.type == "field_access":
        return _translate_field_access(node, ctx)

    if node.type == "array_access":
        return _translate_array_access(node, ctx)

    if node.type == "array_initializer":
        return _translate_array_initializer(node, ctx)

    if node.type == "array_creation_expression":
        return _translate_array_creation(node, ctx)

    if node.type == "class_literal":
        return _translate_class_literal(node, ctx)

    if node.type == "cast_expression":
        return _translate_cast_expression(node, ctx)

    if node.type == "instanceof_expression":
        return _translate_instanceof_expression(node, ctx)

    if node.type == "assignment_expression":
        children = node.children
        if len(children) >= 3:
            left_node = children[0]
            operator = children[1].text
            right_node = children[-1]
            supported_operators = {
                "=",
                "+=",
                "-=",
                "*=",
                "/=",
                "%=",
                "&=",
                "|=",
                "^=",
                "<<=",
                ">>=",
                ">>>=",
            }
            if operator not in supported_operators:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=f"unsupported assignment operator {operator}",
                )
                return f"__j2py_todo__({node.text!r})"
            if operator == ">>>=":
                ctx.diagnostics.warn(
                    node,
                    reason=(
                        "unsigned right shift assignment translated as >>=; "
                        "verify negative values"
                    ),
                )
                operator = ">>="
            left = translate_expression(left_node, ctx)
            right = translate_expression(right_node, ctx)
            return f"{left} {operator} {right}"

    if node.type == "update_expression":
        return _translate_update_expression(node, ctx)

    if node.type == "method_invocation":
        return _translate_method_invocation(node, ctx)

    if node.type == "lambda_expression":
        return _translate_lambda_expression(node, ctx)

    if node.type == "method_reference":
        return _translate_method_reference(node, ctx)

    if node.type == "argument_list":
        return ", ".join(
            translate_expression(child, ctx)
            for child in node.named_children
            if not is_comment(child)
        )

    if node.type == "object_creation_expression":
        return _translate_object_creation(node, ctx)

    if node.type == "parenthesized_expression":
        named_children = node.named_children
        if len(named_children) == 1:
            return translate_expression(named_children[0], ctx)

    if node.type == "unary_expression":
        return _translate_unary_expression(node, ctx)

    if node.type == "ternary_expression":
        return _translate_ternary_expression(node, ctx)

    if node.type == "switch_expression":
        return _translate_switch_expression(node, ctx)

    if node.type == "binary_expression":
        f_string = _translate_string_concat(node, ctx)
        if f_string is not None:
            return f_string
        children = node.children
        if len(children) >= 3:
            operator_text = children[1].text
            if operator_text == "/":
                return _translate_division(node, children[0], children[2], ctx)
            binary_operator: str | None
            if operator_text == ">>>":
                ctx.diagnostics.warn(
                    node,
                    reason="unsigned right shift translated as >>; verify negative values",
                )
                binary_operator = ">>"
            else:
                binary_operator = _translate_binary_operator(operator_text)
            if binary_operator is None:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason=f"unsupported binary operator {children[1].text}",
                )
                return f"__j2py_todo__({node.text!r})"
            null_comparison = _translate_null_comparison(
                children[0],
                children[2],
                binary_operator,
                ctx,
            )
            if null_comparison is not None:
                return null_comparison
            return (
                f"{translate_expression(children[0], ctx)} "
                f"{binary_operator} "
                f"{translate_expression(children[2], ctx)}"
            )

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported expression {node.type}")
    return f"__j2py_todo__({node.text!r})"


def _translate_identifier(raw_name: str, ctx: TranslationContext) -> str:
    if raw_name in ctx.expression_aliases:
        return ctx.expression_aliases[raw_name]
    py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
    if (
        ctx.in_instance_method
        and raw_name in ctx.class_fields
        and raw_name not in ctx.param_names
        and raw_name not in ctx.local_names
    ):
        return f"self.{py_name}"
    return py_name


def _translate_field_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed field access")
        return node.text

    target = translate_expression(children[0], ctx)
    field_name = translate_field_name(
        children[-1].text,
        snake_case=ctx.cfg.snake_case_fields,
    )
    if children[-1].text == "length":
        return f"len({target})"
    return f"{target}.{field_name}"


def _translate_array_access(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) != 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed array access")
        return f"__j2py_todo__({node.text!r})"
    return f"{translate_expression(children[0], ctx)}[{translate_expression(children[1], ctx)}]"


def _translate_array_initializer(node: JavaNode, ctx: TranslationContext) -> str:
    return f"[{', '.join(translate_expression(child, ctx) for child in node.named_children)}]"


def _translate_array_creation(node: JavaNode, ctx: TranslationContext) -> str:
    initializer = first_child_by_type(node, "array_initializer")
    if initializer is not None:
        return translate_expression(initializer, ctx)
    dimensions = [child for child in node.named_children if child.type == "dimensions_expr"]
    if len(dimensions) == 1 and dimensions[0].named_children:
        type_node = next(
            (child for child in node.named_children if child.type != "dimensions_expr"),
            None,
        )
        default = java_default_value(type_node.text if type_node is not None else "Object")
        size = translate_expression(dimensions[0].named_children[0], ctx)
        return f"[{default}] * {size}"
    if len(dimensions) > 1:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="multidimensional array creation requires nested allocation handling",
        )
        return f"__j2py_todo__({node.text!r})"
    ctx.diagnostics.record(
        node,
        supported=False,
        reason="array creation without initializer requires size handling",
    )
    return f"__j2py_todo__({node.text!r})"


def _translate_class_literal(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if not children:
        ctx.diagnostics.record(node, supported=False, reason="malformed class literal")
        return f"__j2py_todo__({node.text!r})"
    return translate_expression(children[0], ctx)


def _translate_cast_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed cast expression")
        return f"__j2py_todo__({node.text!r})"
    ctx.diagnostics.record(node, supported=True, reason="translated cast expression")
    ctx.diagnostics.warn(node, reason="dropped Java cast; verify runtime type")
    return translate_expression(children[-1], ctx)


def _translate_instanceof_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed instanceof expression")
        return f"__j2py_todo__({node.text!r})"

    expression_node = children[0]
    type_node = children[1]
    expression = translate_expression(expression_node, ctx)
    runtime_type = _runtime_type_expression(type_node, ctx)
    if runtime_type is None:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason=f"unsupported instanceof type {type_node.text}",
        )
        return f"__j2py_todo__({node.text!r})"

    if len(children) >= 3 and children[2].type == "identifier":
        raw_name = children[2].text
        py_name = translate_field_name(raw_name, snake_case=ctx.cfg.snake_case_fields)
        ctx.pattern_bindings.append(
            PatternBinding(
                raw_name=raw_name,
                py_name=py_name,
                py_type=translate_type(type_node.text, ctx.cfg),
                source=expression,
            ),
        )

    ctx.diagnostics.record(node, supported=True, reason="translated instanceof expression")
    return f"isinstance({expression}, {runtime_type})"


def _runtime_type_expression(type_node: JavaNode, ctx: TranslationContext) -> str | None:
    raw_type = type_node.text.strip()
    raw_type = raw_type.split("<", 1)[0]
    while raw_type.endswith("[]"):
        raw_type = raw_type[:-2]

    mapped = ctx.cfg.collection_map.get(raw_type) or ctx.cfg.type_map.get(raw_type)
    if mapped is not None:
        return mapped.split("[", 1)[0]
    if raw_type in {"byte", "short", "int", "long"}:
        return "int"
    if raw_type in {"float", "double"}:
        return "float"
    if raw_type == "boolean":
        return "bool"
    if not raw_type:
        return None
    return translate_class_name(raw_type)


def _translate_method_invocation(node: JavaNode, ctx: TranslationContext) -> str:
    stream_pipeline = _translate_stream_pipeline(node, ctx)
    if stream_pipeline is not None:
        return stream_pipeline

    args_node = first_child_by_type(node, "argument_list")
    args = translate_expression(args_node, ctx) if args_node is not None else ""

    named = node.named_children
    if args_node is None or len(named) < 2:
        ctx.diagnostics.record(node, supported=False, reason="malformed method invocation")
        return f"__j2py_todo__({node.text!r})"

    args_index = named.index(args_node)
    method_node = named[args_index - 1]
    method_name = method_node.text
    receiver_nodes = named[: args_index - 1]
    raw_receiver = receiver_nodes[0].text if receiver_nodes else ""
    receiver = translate_expression(receiver_nodes[0], ctx) if receiver_nodes else ""

    if raw_receiver == "System.out" and method_name == "println":
        return f"print({args})"

    if method_name == "add" and receiver:
        return f"{receiver}.append({args})"

    if method_name in {"size", "length"} and receiver and not args:
        return f"len({receiver})"

    if method_name == "isEmpty" and receiver and not args:
        return f"not {receiver}"

    if method_name == "contains" and receiver and args:
        return f"{args} in {receiver}"

    if method_name == "toArray" and receiver:
        return f"list({receiver})"

    if method_name == "get" and receiver and args:
        receiver_type = _expression_py_type(receiver_nodes[0], ctx) if receiver_nodes else None
        if receiver_type is not None and _is_list_type(receiver_type):
            return f"{receiver}[{args}]"
        if receiver_type is not None and _is_dict_type(receiver_type):
            return f"{receiver}.get({args})"
        if raw_receiver.split(".")[-1][:1].isupper():
            return f"{receiver}.get({args})"
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="ambiguous get invocation requires receiver collection type",
        )
        return f"{receiver}.get({args})"

    if method_name == "equals" and receiver and args:
        arg_nodes = list(args_node.named_children) if args_node is not None else []
        if len(arg_nodes) != 1:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="equals invocation with unexpected argument count",
            )
            return f"__j2py_todo__({node.text!r})"
        if arg_nodes[0].type == "null_literal":
            return f"{receiver} is None"
        return f"{receiver} == {args}"

    if method_name == "equalsIgnoreCase" and receiver and args:
        arg_nodes = list(args_node.named_children) if args_node is not None else []
        if len(arg_nodes) == 1:
            return f"{receiver}.lower() == {args}.lower()"

    if method_name == "toString" and receiver and not args:
        return f"str({receiver})"

    if method_name == "hashCode" and receiver and not args:
        return f"hash({receiver})"

    if method_name == "startsWith" and receiver and args:
        return f"{receiver}.startswith({args})"

    if method_name == "endsWith" and receiver and args:
        return f"{receiver}.endswith({args})"

    if method_name == "trim" and receiver and not args:
        return f"{receiver}.strip()"

    if method_name == "toLowerCase" and receiver and not args:
        return f"{receiver}.lower()"

    if method_name == "toUpperCase" and receiver and not args:
        return f"{receiver}.upper()"

    if method_name == "compareTo" and receiver and args:
        return f"({receiver} > {args}) - ({receiver} < {args})"

    if receiver in {"self", ""}:
        py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
        if not receiver and method_name in ctx.self_dispatch_methods and ctx.in_instance_method:
            return f"self.{py_method}({args})"
    else:
        py_method = translate_attribute_method_name(
            method_name,
            snake_case=ctx.cfg.snake_case_methods,
        )
    if receiver:
        return f"{receiver}.{py_method}({args})"
    if ctx.in_instance_method and py_method in ctx.class_methods:
        return f"self.{py_method}({args})"
    return f"{py_method}({args})"


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
    if is_grouping and collector_arg_count != 1:
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
            binding = _stream_flatmap_binding(arg, item_name, ctx)
            if binding is None:
                ctx.diagnostics.record(
                    node,
                    supported=False,
                    reason="unsupported stream intermediate: flatMap",
                )
                return None
            inner_name, inner_iterable = binding
            if current_expr != item_name:
                inner_iterable = current_expr
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
        key_mapper = item_name
        if terminal_arg is not None and terminal_arg.named_children:
            key_arg = terminal_arg.named_children[0]
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
        if terminal_arg is not None and terminal_arg.named_children:
            # First arg is usually the delimiter string literal or expr
            delim = translate_expression(terminal_arg.named_children[0], ctx)
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
    ctx: TranslationContext,
) -> tuple[str, str] | None:
    """Return (inner_loop_var, inner_iterable) for a supported flatMap mapper."""
    if arg.type != "method_reference":
        return None
    named = arg.named_children
    if len(named) >= 2 and named[-1].text == "stream":
        inner_name = _stream_flatmap_inner_item_name(outer_item_name, ctx)
        return inner_name, outer_item_name
    return None


def _apply_stream_post_ops(
    base: str,
    post_ops: list[tuple[str, str | None]],
    item_name: str,
) -> str:
    for operation, key in post_ops:
        if operation == "sorted":
            base = (
                f"sorted({base}, key=lambda {item_name}: {key})" if key else f"sorted({base})"
            )
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
    return len(args_node.named_children)


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


def _lambda_body_expression(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    default_alias: str,
) -> str | None:
    params_node = node.child_by_field("parameters")
    body_node = node.child_by_field("body")
    if params_node is None or body_node is None or body_node.type == "block":
        return None
    params = _lambda_parameters(params_node, ctx)
    if len(params) != 1:
        return None

    raw_name = params[0][0]
    previous_aliases = dict(ctx.expression_aliases)
    ctx.expression_aliases[raw_name] = default_alias
    try:
        body = translate_expression(body_node, ctx)
    finally:
        ctx.expression_aliases = previous_aliases
    return body


def _translate_block_lambda(node: JavaNode, ctx: TranslationContext) -> str:
    """Translate a Java block lambda by emitting a local helper function.

    The helper def is appended to ctx.pending_local_helpers (later flushed near
    the top of the enclosing method). Only the helper name is returned so it can
    be used in any expression position while preserving reviewability.
    """
    if not ctx.allow_local_helpers:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="block lambda requires local helper scope",
        )
        return f"__j2py_todo__({node.text!r})"

    params_node = node.child_by_field("parameters")
    body_node = node.child_by_field("body")
    if params_node is None or body_node is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed lambda expression")
        return f"__j2py_todo__({node.text!r})"

    params = _lambda_parameters(params_node, ctx)

    # Stable, unique-within-method name. Sequential id keeps names short and
    # deterministic per method.
    helper_id = len(ctx.pending_local_helpers) + 1
    helper_name = f"_j2py_lambda_{helper_id}"

    # Snapshot scope so lambda params/locals don't leak, but outer captures
    # (including self via in_instance_method + class_fields) remain visible.
    previous_locals = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    previous_aliases = dict(ctx.expression_aliases)

    for raw_name, _py_name, py_type in params:
        ctx.local_names.add(raw_name)
        if py_type is not None:
            ctx.variable_types[raw_name] = py_type

    try:
        # Local import to avoid circular dependency with statements.py
        # (statements imports translate_expression; we only need translate_body
        # for the block-lambda helper path).
        from j2py.translate.statements import translate_body

        # Body of the helper is indented one level deeper than a normal method body.
        body_lines = translate_body(body_node, ctx, indent="            ")
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
        ctx.expression_aliases = previous_aliases

    # Build signature. Follow the style of expression lambdas (types only when known).
    if params:
        sig_parts: list[str] = []
        for _raw, py_name, py_type in params:
            if ctx.cfg.emit_type_hints and py_type:
                sig_parts.append(f"{py_name}: {py_type}")
            else:
                sig_parts.append(py_name)
        sig = f"{helper_name}({', '.join(sig_parts)})"
    else:
        sig = f"{helper_name}()"

    helper_lines: list[str] = [
        f"        def {sig}:",
        *body_lines,
    ]

    ctx.pending_local_helpers.append(helper_lines)
    ctx.diagnostics.record(
        node,
        supported=True,
        reason="translated block lambda as local helper function",
    )
    return helper_name


def _translate_lambda_expression(node: JavaNode, ctx: TranslationContext) -> str:
    params_node = node.child_by_field("parameters")
    body_node = node.child_by_field("body")
    if params_node is None or body_node is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed lambda expression")
        return f"__j2py_todo__({node.text!r})"

    if body_node.type == "block":
        return _translate_block_lambda(node, ctx)

    params = _lambda_parameters(params_node, ctx)
    previous_locals = set(ctx.local_names)
    previous_types = dict(ctx.variable_types)
    previous_aliases = dict(ctx.expression_aliases)
    for raw_name, _py_name, py_type in params:
        ctx.local_names.add(raw_name)
        if py_type is not None:
            ctx.variable_types[raw_name] = py_type
    try:
        body = translate_expression(body_node, ctx)
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
        ctx.expression_aliases = previous_aliases

    rendered_params = ", ".join(py_name for _raw_name, py_name, _py_type in params)
    if rendered_params:
        return f"lambda {rendered_params}: {body}"
    return f"lambda: {body}"


def _lambda_parameters(
    node: JavaNode,
    ctx: TranslationContext,
) -> list[tuple[str, str, str | None]]:
    if node.type == "identifier":
        return [
            (
                node.text,
                translate_field_name(node.text, snake_case=ctx.cfg.snake_case_fields),
                None,
            ),
        ]

    params: list[tuple[str, str, str | None]] = []
    for child in node.named_children:
        if child.type == "formal_parameter":
            name_node = child.child_by_field("name")
            if name_node is None:
                continue
            type_node = child.child_by_field("type")
            params.append(
                (
                    name_node.text,
                    translate_field_name(name_node.text, snake_case=ctx.cfg.snake_case_fields),
                    translate_type(type_node.text, ctx.cfg) if type_node is not None else None,
                ),
            )
        elif child.type == "identifier":
            params.append(
                (
                    child.text,
                    translate_field_name(child.text, snake_case=ctx.cfg.snake_case_fields),
                    None,
                ),
            )
    return params


def _translate_method_reference(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named = node.named_children
    if len(children) < 3 or not named:
        ctx.diagnostics.record(node, supported=False, reason="malformed method reference")
        return f"__j2py_todo__({node.text!r})"

    target = _method_reference_target(named[0], ctx)
    if children[-1].text == "new":
        if named[0].type == "array_type":
            ctx.diagnostics.warn(
                node,
                reason="array constructor method reference translated as list factory",
            )
            return "list"
        return target

    method_node = named[-1]
    if method_node == named[0]:
        ctx.diagnostics.record(node, supported=False, reason="malformed method reference")
        return f"__j2py_todo__({node.text!r})"
    method_name = translate_method_name(method_node.text, snake_case=ctx.cfg.snake_case_methods)
    return f"{target}.{method_name}"


def _method_reference_target(node: JavaNode, ctx: TranslationContext) -> str:
    if node.text[:1].isupper():
        return translate_class_name(node.text)
    return translate_expression(node, ctx)


def _translate_object_creation(node: JavaNode, ctx: TranslationContext) -> str:
    type_node = node.child_by_field("type")
    args_node = first_child_by_type(node, "argument_list")
    body_node = first_child_by_type(node, "class_body")
    args = translate_expression(args_node, ctx) if args_node is not None else ""
    raw_type = type_node.text if type_node is not None else "object"
    base_type = raw_type.split("<", 1)[0]

    if body_node is not None:
        return _translate_anonymous_class(node, body_node, base_type, args, ctx)

    collection_literals = {
        "ArrayList": "[]",
        "LinkedList": "[]",
        "Vector": "[]",
        "HashMap": "{}",
        "LinkedHashMap": "{}",
        "TreeMap": "{}",
        "Hashtable": "{}",
        "HashSet": "set()",
        "LinkedHashSet": "set()",
        "TreeSet": "set()",
    }
    collection_copy_constructors = {
        "ArrayList": "list",
        "LinkedList": "list",
        "Vector": "list",
        "HashMap": "dict",
        "LinkedHashMap": "dict",
        "TreeMap": "dict",
        "Hashtable": "dict",
        "HashSet": "set",
        "LinkedHashSet": "set",
        "TreeSet": "set",
    }
    if base_type in collection_literals:
        if not args:
            return collection_literals[base_type]
        arg_nodes = [
            child for child in args_node.named_children if not is_comment(child)
        ] if args_node is not None else []
        if len(arg_nodes) == 1:
            copied = translate_expression(arg_nodes[0], ctx)
            return f"{collection_copy_constructors[base_type]}({copied})"
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="non-empty collection constructor requires LLM completion",
        )
        return f"__j2py_todo__({node.text!r})"

    return f"{translate_class_name(base_type)}({args})"


def _translate_anonymous_class(
    node: JavaNode,
    body_node: JavaNode,
    base_type: str,
    args: str,
    ctx: TranslationContext,
) -> str:
    from j2py.translate.classes import (
        _instance_field_names,
        _instance_field_types,
        field_infos_from_declaration,
    )

    if not ctx.allow_local_helpers:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="anonymous class requires local helper scope",
        )
        return f"__j2py_todo__({node.text!r})"

    helper_id = len(ctx.pending_local_helpers) + 1
    helper_name = f"_J2pyAnonymous{helper_id}"
    base_name = translate_class_name(base_type)
    helper_lines = [f"        class {helper_name}({base_name}):"]

    instance_fields: list[FieldInfo] = []
    methods: list[JavaNode] = []
    for member in body_node.named_children:
        if is_comment(member):
            ctx.diagnostics.warn(member, reason="preserved comment")
            if ctx.cfg.emit_line_comments:
                helper_lines.extend(translate_comment(member, indent="            "))
            continue
        if member.type == "field_declaration":
            for field in field_infos_from_declaration(member, ctx.cfg):
                if field.is_static:
                    ctx.diagnostics.record(
                        member,
                        supported=False,
                        reason="unsupported anonymous class static field_declaration",
                    )
                    helper_lines.append(
                        "            # TODO(j2py): unsupported anonymous class static field",
                    )
                    continue
                ctx.diagnostics.record(
                    member,
                    supported=True,
                    reason="translated anonymous class instance field",
                )
                instance_fields.append(field)
            continue
        if member.type == "method_declaration":
            methods.append(member)
            continue
        ctx.diagnostics.record(
            member,
            supported=False,
            reason=f"unsupported anonymous class member {member.type}",
        )
        helper_lines.append(
            f"            # TODO(j2py): unsupported anonymous class member {member.type}",
        )

    instance_field_names = _instance_field_names(instance_fields)
    instance_field_types = _instance_field_types(instance_fields)
    wrote_member = False
    if instance_fields:
        helper_lines.extend(
            _anonymous_helper_init_lines(instance_fields, ctx),
        )
        wrote_member = True

    for method in methods:
        if wrote_member:
            helper_lines.append("")
        helper_lines.extend(
            _anonymous_method_lines(
                method,
                ctx,
                instance_field_names=instance_field_names,
                instance_field_types=instance_field_types,
            ),
        )
        wrote_member = True

    if not wrote_member:
        helper_lines.append("            pass")

    ctx.pending_local_helpers.append(helper_lines)
    ctx.diagnostics.record(
        node,
        supported=True,
        reason="translated anonymous class as local helper class",
    )
    ctx.diagnostics.warn(
        node,
        reason="anonymous class translated as local helper; verify captured outer this references",
    )
    return f"{helper_name}({args})"


def _anonymous_helper_init_lines(
    fields: list[FieldInfo],
    ctx: TranslationContext,
) -> list[str]:
    from j2py.translate.classes import (
        _field_assignment,
        _instance_field_names,
        _instance_field_types,
    )

    lines = ["            def __init__(self):"]
    field_ctx = TranslationContext(
        cfg=ctx.cfg,
        diagnostics=ctx.diagnostics,
        class_fields=_instance_field_names(fields),
        class_field_types=_instance_field_types(fields),
        in_instance_method=True,
    )
    for field in fields:
        if field.initializer is not None:
            assignment = (
                f"{_field_assignment(f'self.{field.py_name}', field.py_type, ctx.cfg)} = "
                f"{translate_expression(field.initializer, field_ctx)}"
            )
        else:
            default_value = java_default_value(field.java_type)
            annotation = field.py_type if default_value != "None" else f"{field.py_type} | None"
            assignment = (
                f"{_field_assignment(f'self.{field.py_name}', annotation, ctx.cfg)} = "
                f"{default_value}"
            )
        lines.append(f"                {assignment}")
    return lines


def _anonymous_method_lines(
    method: JavaNode,
    ctx: TranslationContext,
    *,
    instance_field_names: set[str],
    instance_field_types: dict[str, str],
) -> list[str]:
    from j2py.translate.classes import (
        _method_body,
        _modifiers,
        _parameter_infos,
        _record_annotation_diagnostics,
        _return_type,
    )
    from j2py.translate.statements import translate_body

    _record_annotation_diagnostics(method, ctx.cfg, ctx.diagnostics)
    ctx.diagnostics.record(
        method,
        supported=True,
        reason="translated anonymous class method",
    )

    name_node = method.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = translate_method_name(raw_name, snake_case=ctx.cfg.snake_case_methods)
    is_static = "static" in _modifiers(method)
    params = _parameter_infos(method, ctx.cfg)
    rendered_params = [
        f"{param.py_name}: {param.py_type}" if ctx.cfg.emit_type_hints else param.py_name
        for param in params
    ]
    if not is_static:
        rendered_params.insert(0, "self")
    returns = f" -> {_return_type(method, ctx.cfg)}" if ctx.cfg.emit_type_hints else ""
    lines: list[str] = []
    if is_static:
        lines.append("            @staticmethod")
    lines.append(f"            def {py_name}({', '.join(rendered_params)}){returns}:")

    previous_param_names = set(ctx.param_names)
    previous_types = dict(ctx.variable_types)
    previous_class_fields = set(ctx.class_fields)
    previous_class_field_types = dict(ctx.class_field_types)
    previous_in_instance_method = ctx.in_instance_method
    previous_allow_helpers = ctx.allow_local_helpers
    for param in params:
        ctx.param_names.add(param.raw_name)
        ctx.variable_types[param.raw_name] = param.py_type
    ctx.class_fields = instance_field_names
    ctx.class_field_types = instance_field_types
    ctx.in_instance_method = not is_static
    ctx.allow_local_helpers = True
    start_index = len(ctx.pending_local_helpers)
    try:
        body = _method_body(method)
        body_lines = (
            translate_body(body, ctx, indent="                ")
            if body
            else ["                pass"]
        )
        nested_helpers = ctx.pending_local_helpers[start_index:]
        del ctx.pending_local_helpers[start_index:]
        for helper in nested_helpers:
            lines.append("")
            lines.extend(f"        {line}" if line else line for line in helper)
        lines.extend(body_lines)
    finally:
        ctx.param_names = previous_param_names
        ctx.variable_types = previous_types
        ctx.class_fields = previous_class_fields
        ctx.class_field_types = previous_class_field_types
        ctx.in_instance_method = previous_in_instance_method
        ctx.allow_local_helpers = previous_allow_helpers

    return lines


def _translate_unary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named_children = node.named_children
    if not children or not named_children:
        ctx.diagnostics.record(node, supported=False, reason="malformed unary expression")
        return f"__j2py_todo__({node.text!r})"

    operator = children[0].text
    operand = translate_expression(named_children[-1], ctx)
    if operator == "!":
        if operand.startswith("not "):
            return operand.removeprefix("not ")
        return f"not {operand}"
    if operator in {"+", "-"}:
        return f"{operator}{operand}"

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported unary operator {operator}")
    return f"__j2py_todo__({node.text!r})"


def _translate_update_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.children
    named_children = node.named_children
    if len(children) < 2 or not named_children:
        ctx.diagnostics.record(node, supported=False, reason="malformed update expression")
        return f"__j2py_todo__({node.text!r})"

    operator = next(
        (child.text for child in children if child.text in {"++", "--"}),
        children[-1].text,
    )
    target = translate_expression(named_children[0], ctx)
    if operator == "++":
        return f"{target} += 1"
    if operator == "--":
        return f"{target} -= 1"

    ctx.diagnostics.record(node, supported=False, reason=f"unsupported update operator {operator}")
    return f"__j2py_todo__({node.text!r})"


def _translate_ternary_expression(node: JavaNode, ctx: TranslationContext) -> str:
    children = node.named_children
    if len(children) != 3:
        ctx.diagnostics.record(node, supported=False, reason="malformed ternary expression")
        return f"__j2py_todo__({node.text!r})"
    condition = translate_expression(children[0], ctx)
    if_true = translate_expression(children[1], ctx)
    if_false = translate_expression(children[2], ctx)
    return f"{if_true} if {condition} else {if_false}"


def _translate_switch_expression(node: JavaNode, ctx: TranslationContext) -> str:
    condition = node.child_by_field("condition")
    body = node.child_by_field("body")
    if condition is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed switch expression")
        return f"__j2py_todo__({node.text!r})"

    subject = translate_expression(condition, ctx)
    cases: list[tuple[list[str], str]] = []
    default: str | None = None
    for rule in body.named_children:
        if rule.type != "switch_rule":
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="colon switch expression requires statement translation",
            )
            return f"__j2py_todo__({node.text!r})"
        label = first_child_by_type(rule, "switch_label")
        value_node = _switch_rule_value_node(rule)
        if label is None or value_node is None:
            ctx.diagnostics.record(node, supported=False, reason="malformed switch rule")
            return f"__j2py_todo__({node.text!r})"
        value = _switch_rule_value(value_node, ctx)
        if value is None:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="switch rule block requires a single yield expression",
            )
            return f"__j2py_todo__({node.text!r})"
        labels = _switch_label_values(label, ctx)
        if labels:
            cases.append((labels, value))
        else:
            default = value

    if default is None:
        ctx.diagnostics.record(node, supported=False, reason="switch expression without default")
        return f"__j2py_todo__({node.text!r})"

    expression = default
    for labels, value in reversed(cases):
        expression = f"{value} if {_switch_condition(subject, labels)} else {expression}"
    return expression


def _switch_rule_value_node(rule: JavaNode) -> JavaNode | None:
    children = [child for child in rule.named_children if child.type != "switch_label"]
    return children[0] if len(children) == 1 else None


def _switch_rule_value(node: JavaNode, ctx: TranslationContext) -> str | None:
    if node.type == "expression_statement" and node.named_children:
        return translate_expression(node.named_children[0], ctx)
    if node.type == "block":
        yields = [child for child in node.named_children if child.type == "yield_statement"]
        if len(yields) == 1 and len(yields[0].named_children) == 1:
            return translate_expression(yields[0].named_children[0], ctx)
    return None


def _switch_label_values(label: JavaNode, ctx: TranslationContext) -> list[str]:
    return [translate_expression(child, ctx) for child in label.named_children]


def _switch_condition(subject: str, labels: list[str]) -> str:
    if len(labels) == 1:
        return f"{subject} == {labels[0]}"
    return f"{subject} in ({', '.join(labels)})"


def _translate_binary_operator(operator: str) -> str | None:
    operators = {
        "&&": "and",
        "||": "or",
        "==": "==",
        "!=": "!=",
        ">": ">",
        ">=": ">=",
        "<": "<",
        "<=": "<=",
        "+": "+",
        "-": "-",
        "*": "*",
        "%": "%",
        "&": "&",
        "|": "|",
        "^": "^",
        "<<": "<<",
        ">>": ">>",
    }
    return operators.get(operator)


def _translate_division(
    node: JavaNode,
    left_node: JavaNode,
    right_node: JavaNode,
    ctx: TranslationContext,
) -> str:
    left_type = _expression_py_type(left_node, ctx)
    right_type = _expression_py_type(right_node, ctx)
    left = translate_expression(left_node, ctx)
    right = translate_expression(right_node, ctx)

    if left_type == "int" and right_type == "int":
        # Java int division truncates; we emit correct floor division.
        # Use warn (not unhandled) so a correct mechanical translation does not
        # force LLM or artificially lower coverage. The note is still visible
        # to reviewers via diagnostics.warnings and CLI output.
        ctx.diagnostics.warn(
            node,
            reason="integer division translated with floor division; verify truncation semantics",
        )
        return f"{left} // {right}"

    if left_type == "float" or right_type == "float":
        return f"{left} / {right}"

    ctx.diagnostics.record(
        node,
        supported=False,
        reason="division requires numeric type certainty",
    )
    return f"__j2py_todo__({node.text!r})"


def _translate_null_comparison(
    left_node: JavaNode,
    right_node: JavaNode,
    operator: str,
    ctx: TranslationContext,
) -> str | None:
    if operator not in {"==", "!="}:
        return None
    if right_node.type == "null_literal":
        left = translate_expression(left_node, ctx)
        return f"{left} {'is' if operator == '==' else 'is not'} None"
    if left_node.type == "null_literal":
        right = translate_expression(right_node, ctx)
        return f"{right} {'is' if operator == '==' else 'is not'} None"
    return None


def _translate_string_concat(node: JavaNode, ctx: TranslationContext) -> str | None:
    terms = _flatten_plus(node)
    if terms is None or not any(term.type == "string_literal" for term in terms):
        return None
    if any(term.type == "string_literal" and "\n" in _string_literal_value(term) for term in terms):
        return _translate_string_concat_as_addition(terms, ctx)

    first_string_index = next(
        index for index, term in enumerate(terms) if term.type == "string_literal"
    )
    parts: list[str] = []
    dynamic_parts: list[str] = []
    start_index = 0
    if first_string_index > 1:
        leading_expression = " + ".join(
            translate_expression(term, ctx) for term in terms[:first_string_index]
        )
        dynamic_parts.append(leading_expression)
        parts.append(f"{{{leading_expression}}}")
        start_index = first_string_index

    for term in terms[start_index:]:
        if term.type == "string_literal":
            parts.append(_string_literal_value(term).replace("{", "{{").replace("}", "}}"))
        else:
            expression = translate_expression(term, ctx)
            dynamic_parts.append(expression)
            parts.append(f"{{{expression}}}")
    if any('"' in part or "\\" in part for part in dynamic_parts):
        return _translate_string_concat_as_addition(terms, ctx)
    content = "".join(parts).replace("\\", "\\\\").replace('"', '\\"')
    return f'f"{content}"'


def _translate_string_concat_as_addition(terms: list[JavaNode], ctx: TranslationContext) -> str:
    parts: list[str] = []
    first_string_index = next(
        (index for index, term in enumerate(terms) if term.type == "string_literal"),
        0,
    )
    start_index = 0
    if first_string_index > 1:
        leading_expression = " + ".join(
            translate_expression(term, ctx) for term in terms[:first_string_index]
        )
        parts.append(f"str({leading_expression})")
        start_index = first_string_index

    for term in terms[start_index:]:
        if term.type == "string_literal":
            parts.append(repr(_string_literal_value(term)))
        else:
            parts.append(f"str({translate_expression(term, ctx)})")
    return " + ".join(parts)


def _flatten_plus(node: JavaNode) -> list[JavaNode] | None:
    if node.type != "binary_expression":
        return [node]

    children = node.children
    if len(children) != 3 or children[1].text != "+":
        return None

    left = _flatten_plus(children[0])
    right = _flatten_plus(children[2])
    if left is None or right is None:
        return None
    return left + right


def _string_literal_value(node: JavaNode) -> str:
    return java_string_literal_value(node.text)


def _expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    return infer_expression_py_type(node, ctx)


def infer_expression_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    """Best-effort static type for a Java expression node."""
    if node.type == "decimal_integer_literal":
        return "int"
    if node.type in {"decimal_floating_point_literal", "floating_point_type"}:
        return "float"
    if node.type == "integer_type" and node.text in {"int", "long", "byte", "short"}:
        return "int"
    if node.type == "string_literal":
        return "str"
    if node.type == "character_literal":
        return "str"
    if node.type == "true" or node.type == "false":
        return "bool"
    if node.type == "null_literal":
        return "None"
    if node.type == "identifier":
        return ctx.variable_types.get(node.text) or ctx.class_field_types.get(node.text)
    if node.type == "field_access":
        children = node.named_children
        if len(children) == 2 and children[0].type == "this":
            return ctx.class_field_types.get(children[1].text)
    if node.type == "parenthesized_expression" and len(node.named_children) == 1:
        return infer_expression_py_type(node.named_children[0], ctx)
    if node.type == "cast_expression":
        cast_type_node = node.named_children[0] if node.named_children else None
        if cast_type_node is not None:
            return translate_type(cast_type_node.text, ctx.cfg)
    if node.type == "object_creation_expression":
        type_node = node.child_by_field("type")
        if type_node is not None:
            return translate_type(type_node.text, ctx.cfg)
    if node.type == "method_invocation":
        return _infer_method_invocation_py_type(node, ctx)
    if node.type == "ternary_expression":
        children = node.named_children
        if len(children) >= 3:
            consequent_type = infer_expression_py_type(children[1], ctx)
            alternate_type = infer_expression_py_type(children[2], ctx)
            if consequent_type == "float" or alternate_type == "float":
                return "float"
            return consequent_type or alternate_type
    if node.type == "binary_expression" and len(node.children) == 3:
        operator = node.children[1].text
        if operator == "+":
            left_type = infer_expression_py_type(node.children[0], ctx)
            right_type = infer_expression_py_type(node.children[2], ctx)
            if left_type == "str" or right_type == "str":
                return "str"
    return None


def _infer_method_invocation_py_type(node: JavaNode, ctx: TranslationContext) -> str | None:
    named = [child for child in node.named_children if not is_comment(child)]
    args_node = first_child_by_type(node, "argument_list")
    if args_node is None or args_node not in named:
        return None
    args_index = named.index(args_node)
    if args_index == 0:
        return None
    method_name = named[args_index - 1].text
    receiver_nodes = named[: args_index - 1]

    int_return_methods = {
        "size",
        "length",
        "sum",
        "intValue",
        "longValue",
        "hashCode",
        "compare",
        "compareTo",
        "indexOf",
        "lastIndexOf",
    }
    str_return_methods = {
        "trim",
        "strip",
        "toLowerCase",
        "toUpperCase",
        "toString",
        "substring",
        "formatted",
    }
    if method_name in int_return_methods:
        return "int"
    if method_name in str_return_methods:
        return "str"
    if method_name == "isEmpty":
        return "bool"
    if method_name in {"get", "getOrDefault"} and receiver_nodes:
        receiver_type = infer_expression_py_type(receiver_nodes[0], ctx)
        if receiver_type is not None and _is_dict_type(receiver_type):
            return element_type_from_container(receiver_type) or "object"
    return None


def _is_list_type(py_type: str) -> bool:
    return py_type == "list" or py_type.startswith("list[")


def _is_dict_type(py_type: str) -> bool:
    return py_type == "dict" or py_type.startswith("dict[")

"""Lambda and method-reference expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.java_types import java_expression_type, java_type_simple_name
from j2py.translate.node_utils import first_child_by_type, unwrap_parens
from j2py.translate.rules.naming import (
    translate_class_name,
    translate_field_name,
    translate_method_name,
)
from j2py.translate.rules.types import translate_type


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
    previous_java_types = dict(ctx.variable_java_types)
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
        ctx.variable_java_types = previous_java_types
        ctx.expression_aliases = previous_aliases

    # Build signature. Follow the style of expression lambdas (types only when known).
    if params:
        sig_parts: list[str] = []
        for _raw, py_name, py_type in params:
            if ctx.cfg.emit_type_hints and py_type:
                ctx.diagnostics.imports.need_type_annotation(py_type)
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
    previous_java_types = dict(ctx.variable_java_types)
    previous_aliases = dict(ctx.expression_aliases)
    for raw_name, _py_name, py_type in params:
        ctx.local_names.add(raw_name)
        if py_type is not None:
            ctx.variable_types[raw_name] = py_type
        elif _lambda_body_is_map_get_on_param(body_node, raw_name):
            ctx.variable_types[raw_name] = "dict"
    promoted_helper_name: str | None = None
    try:
        body_inner = unwrap_parens(body_node)
        if body_inner.type in {"assignment_expression", "update_expression"}:
            result = _desugar_lambda_body_assign(node, body_inner, params, ctx)
            if isinstance(result, str) and result.startswith("_j2py_lambda_"):
                # Promoted to helper def — skip the lambda wrapping below.
                promoted_helper_name = result
                body = result  # placeholder, won't be used
            else:
                body = result
        else:
            body = translate_expression(body_node, ctx)
    finally:
        ctx.local_names = previous_locals
        ctx.variable_types = previous_types
        ctx.variable_java_types = previous_java_types
        ctx.expression_aliases = previous_aliases

    if promoted_helper_name is not None:
        return promoted_helper_name

    rendered_params = ", ".join(py_name for _raw_name, py_name, _py_type in params)
    if rendered_params:
        return f"lambda {rendered_params}: {body}"
    return f"lambda: {body}"


def _desugar_lambda_body_assign(
    node: JavaNode,
    body_inner: JavaNode,
    params: list[tuple[str, str, str | None]],
    ctx: TranslationContext,
) -> str:
    """Desugar an assignment/update in an expression-lambda body.

    Python lambda bodies must be pure expressions; assignments are not.
    - Simple dotless-name ``=``: use walrus (:=) — stays a lambda.
    - Field assignment or compound operator: promote to a named helper def so the
      assignment can appear as a statement; returns the helper name.
    """
    from j2py.translate.expr_ops import _desugar_embedded_assign

    expr = _desugar_embedded_assign(body_inner, ctx)
    if not ctx.hoisted_pre_stmts:
        # Walrus path: no hoist, body is the walrus expression.
        return expr

    # Hoist path: clear and promote to helper def.
    ctx.hoisted_pre_stmts.clear()
    if not ctx.allow_local_helpers:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="expression lambda with field-assignment body requires local helper scope",
        )
        return f"__j2py_todo__({node.text!r})"

    helper_id = len(ctx.pending_local_helpers) + 1
    helper_name = f"_j2py_lambda_{helper_id}"

    if params:
        sig_parts: list[str] = []
        for _raw, py_name, py_type in params:
            if ctx.cfg.emit_type_hints and py_type:
                ctx.diagnostics.imports.need_type_annotation(py_type)
                sig_parts.append(f"{py_name}: {py_type}")
            else:
                sig_parts.append(py_name)
        sig = f"{helper_name}({', '.join(sig_parts)})"
    else:
        sig = f"{helper_name}()"

    assign_stmt = translate_expression(body_inner, ctx)
    helper_lines: list[str] = [f"        def {sig}:", f"            {assign_stmt}"]
    ctx.pending_local_helpers.append(helper_lines)
    ctx.diagnostics.record(
        node,
        supported=True,
        reason="expression lambda with field-assignment body promoted to local helper",
    )
    ctx.diagnostics.warn(
        node,
        reason=(
            "expression lambda with field-assignment body promoted to named def; verify semantics"
        ),
    )
    return helper_name


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


def _lambda_body_is_map_get_on_param(body_node: JavaNode, param_name: str) -> bool:
    if body_node.type != "method_invocation":
        return False
    named = [child for child in body_node.named_children if not is_comment(child)]
    args_node = first_child_by_type(body_node, "argument_list")
    if args_node is None or args_node not in named:
        return False
    args_index = named.index(args_node)
    if args_index < 1 or named[args_index - 1].text != "get":
        return False
    if len(list(args_node.named_children)) != 1:
        return False
    receiver_nodes = named[: args_index - 1]
    if len(receiver_nodes) != 1:
        return False
    receiver = receiver_nodes[0]
    return receiver.type == "identifier" and receiver.text == param_name


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
    if target == "Character":
        character_predicate = _character_method_reference_predicate(method_node.text)
        if character_predicate is not None:
            return character_predicate
    method_name = translate_method_name(method_node.text, snake_case=ctx.cfg.snake_case_methods)
    if method_node.text == "contains" and _is_collection_method_reference_target(named[0], ctx):
        return f"{target}.__contains__"
    return f"{target}.{method_name}"


def _character_method_reference_predicate(method_name: str) -> str | None:
    predicate = {
        "isDigit": "isdigit",
        "isLetter": "isalpha",
        "isLetterOrDigit": "isalnum",
        "isLowerCase": "islower",
        "isUpperCase": "isupper",
        "isWhitespace": "isspace",
    }.get(method_name)
    value = "(chr(value) if isinstance(value, int) and not isinstance(value, bool) else value)"
    if predicate is not None:
        return f"(lambda value: value is not None and {value}.{predicate}())"
    if method_name == "isTitleCase":
        return f"(lambda value: value is not None and {value}.istitle() and not {value}.isupper())"
    return None


def _method_reference_target(node: JavaNode, ctx: TranslationContext) -> str:
    target_text = node.text
    if node.type == "generic_type":
        type_id = first_child_by_type(node, "type_identifier")
        if type_id is not None:
            target_text = type_id.text
    if target_text[:1].isupper():
        return translate_class_name(target_text)
    return translate_expression(node, ctx)


def _is_collection_method_reference_target(node: JavaNode, ctx: TranslationContext) -> bool:
    java_type = java_expression_type(node, ctx)
    if java_type is None:
        return False
    simple = java_type_simple_name(java_type)
    if not simple:
        return False
    if simple in {
        "Collection",
        "Deque",
        "HashSet",
        "LinkedHashSet",
        "List",
        "Queue",
        "Set",
        "SortedSet",
        "TreeSet",
    }:
        return True
    return simple.endswith(("Collection", "List", "Queue", "Set")) and not simple.endswith(
        "Multiset",
    )

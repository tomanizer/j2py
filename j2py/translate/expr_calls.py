"""Method invocation and Java standard-library call shims."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_collection_calls import translate_collection_method_invocation
from j2py.translate.expr_jdk_calls import translate_jdk_instance_method_invocation
from j2py.translate.expr_static_calls import (
    translate_static_imported_method,
    translate_static_method_invocation,
)
from j2py.translate.expressions import translate_expression
from j2py.translate.member_resolution import (
    java_type_shape_signature,
    wildcard_static_import_binding,
)
from j2py.translate.node_utils import first_child_by_type, unwrap_parens
from j2py.translate.rules.naming import (
    translate_attribute_method_name,
    translate_method_name,
)
from j2py.translate.rules.types import type_simple_name


@dataclass(frozen=True)
class _MethodInvocationParts:
    arg_nodes: list[JavaNode]
    arg_expressions: list[str]
    args: str
    method_name: str
    receiver_nodes: list[JavaNode]
    raw_receiver: str


def _route_static_instance_collision_to_static(
    py_method: str,
    args: str,
    ctx: TranslationContext,
) -> bool:
    """Whether a receiverless collision call should dispatch to the static rename."""
    if py_method not in ctx.static_instance_static_aliases:
        return True
    if args:
        return True
    instance_zero = py_method in ctx.static_instance_instance_zero_arg_names
    static_zero = py_method in ctx.static_instance_static_zero_arg_names
    if static_zero and not instance_zero:
        return True
    if instance_zero and not static_zero:
        return False
    if static_zero and instance_zero:
        return not ctx.in_instance_method
    return False


def _translate_method_invocation(node: JavaNode, ctx: TranslationContext) -> str:
    from j2py.translate.expr_streams import _translate_stream_pipeline

    stream_pipeline = _translate_stream_pipeline(node, ctx)
    if stream_pipeline is not None:
        return stream_pipeline

    parts = _method_invocation_parts(node, ctx)
    if parts is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed method invocation")
        return f"__j2py_todo__({node.text!r})"

    static_call = _translate_static_or_platform_method_invocation(node, parts, ctx)
    if static_call is not None:
        return static_call

    receiver = _receiver_expression(parts, ctx)
    overload_call = _translate_source_proven_overload_call(node, parts, receiver, ctx)
    if overload_call is not None:
        return overload_call

    special_call = _translate_receiver_special_method_invocation(node, parts, receiver, ctx)
    if special_call is not None:
        return special_call

    return _translate_generic_method_invocation(parts, receiver, ctx)


def _method_invocation_parts(
    node: JavaNode,
    ctx: TranslationContext,
) -> _MethodInvocationParts | None:
    args_node = first_child_by_type(node, "argument_list")

    named = node.named_children
    if args_node is None or len(named) < 2:
        return None

    arg_nodes = _argument_nodes(args_node)
    arg_expressions = [_translate_argument(child, ctx) for child in arg_nodes]
    args = ", ".join(arg_expressions)

    args_index = named.index(args_node)
    method_node = named[args_index - 1]
    method_name = method_node.text
    receiver_nodes = named[: args_index - 1]
    raw_receiver = receiver_nodes[0].text if receiver_nodes else ""

    return _MethodInvocationParts(
        arg_nodes=arg_nodes,
        arg_expressions=arg_expressions,
        args=args,
        method_name=method_name,
        receiver_nodes=receiver_nodes,
        raw_receiver=raw_receiver,
    )


def _translate_static_or_platform_method_invocation(
    node: JavaNode,
    parts: _MethodInvocationParts,
    ctx: TranslationContext,
) -> str | None:
    if not parts.receiver_nodes and parts.method_name in ctx.static_method_imports:
        static_call = translate_static_imported_method(
            node,
            imported_name=ctx.static_method_imports[parts.method_name],
            binding=ctx.static_member_bindings.get(parts.method_name),
            arg_nodes=parts.arg_nodes,
            args=parts.arg_expressions,
            ctx=ctx,
        )
        if static_call is not None:
            return static_call

    if not parts.receiver_nodes and ctx.wildcard_static_imports:
        for owner in ctx.wildcard_static_imports.values():
            binding = wildcard_static_import_binding(owner, parts.method_name, ctx, kind="method")
            if binding is None:
                continue
            static_call = translate_static_imported_method(
                node,
                imported_name=f"{binding.owner}.{binding.member}",
                binding=binding,
                arg_nodes=parts.arg_nodes,
                args=parts.arg_expressions,
                ctx=ctx,
            )
            if static_call is not None:
                return static_call
        ctx.diagnostics.warn(
            node,
            reason=(
                f"wildcard static import could not resolve member {parts.method_name}; "
                "verify unqualified call"
            ),
            category="wildcard_static_import_unresolved",
            facts={
                "member": parts.method_name,
                "owners": ",".join(sorted(ctx.wildcard_static_imports.values())),
            },
        )

    static_call = translate_static_method_invocation(
        node,
        raw_receiver=parts.raw_receiver,
        method_name=parts.method_name,
        arg_nodes=parts.arg_nodes,
        args=parts.arg_expressions,
        ctx=ctx,
    )
    if static_call is not None:
        return static_call

    if parts.raw_receiver == "System.out" and parts.method_name == "println":
        return f"print({parts.args})"

    return None


def _receiver_expression(parts: _MethodInvocationParts, ctx: TranslationContext) -> str:
    return translate_expression(parts.receiver_nodes[0], ctx) if parts.receiver_nodes else ""


def _translate_receiver_special_method_invocation(
    node: JavaNode,
    parts: _MethodInvocationParts,
    receiver: str,
    ctx: TranslationContext,
) -> str | None:
    if not receiver:
        return None

    collection_call = translate_collection_method_invocation(
        node,
        method_name=parts.method_name,
        receiver=receiver,
        receiver_nodes=parts.receiver_nodes,
        raw_receiver=parts.raw_receiver,
        arg_nodes=parts.arg_nodes,
        arg_expressions=parts.arg_expressions,
        args=parts.args,
        ctx=ctx,
    )
    if collection_call is not None:
        return collection_call

    jdk_instance_call = translate_jdk_instance_method_invocation(
        node,
        method_name=parts.method_name,
        receiver=receiver,
        raw_receiver=parts.raw_receiver,
        receiver_nodes=parts.receiver_nodes,
        arg_nodes=parts.arg_nodes,
        arg_expressions=parts.arg_expressions,
        args=parts.args,
        ctx=ctx,
    )
    if jdk_instance_call is not None:
        return jdk_instance_call
    return None


def _translate_source_proven_overload_call(
    node: JavaNode,
    parts: _MethodInvocationParts,
    receiver: str,
    ctx: TranslationContext,
) -> str | None:
    targets = ctx.overload_call_targets.get(parts.method_name)
    if not targets:
        return None

    from j2py.translate.java_types import java_expression_type

    java_types = [java_expression_type(arg, ctx) for arg in parts.arg_nodes]
    if any(java_type is None for java_type in java_types):
        ctx.diagnostics.warn(
            node,
            reason=f"overload call {parts.method_name} lacks source Java argument types",
            category="overload_erasure_collision",
            facts={"method": parts.method_name},
        )
        return None
    signature = java_type_shape_signature(
        [java_type or "Object" for java_type in java_types],
        ctx.cfg,
    )
    matches = [target for target in targets if target.java_shape_signature == signature]
    if len(matches) != 1:
        ctx.diagnostics.warn(
            node,
            reason=f"overload call {parts.method_name} did not match one body-backed branch",
            category="overload_erasure_collision",
            facts={
                "method": parts.method_name,
                "java_shapes": "|".join(signature),
            },
        )
        return None

    target = matches[0]
    if target.is_static:
        owner = receiver or ctx.containing_class_name
        if owner is None:
            return None
        return f"{owner}.{target.helper_name}({parts.args})"
    if receiver:
        return f"{receiver}.{target.helper_name}({parts.args})"
    if ctx.in_instance_method:
        return f"self.{target.helper_name}({parts.args})"
    return None


def _translate_generic_method_invocation(
    parts: _MethodInvocationParts,
    receiver: str,
    ctx: TranslationContext,
) -> str:
    if receiver in {"self", ""}:
        py_method = translate_method_name(
            parts.method_name,
            snake_case=ctx.cfg.snake_case_methods,
        )
        dispatched = _translate_unqualified_dispatch(parts, receiver, py_method, ctx)
        if dispatched is not None:
            return dispatched
    else:
        py_method = _translate_receiver_method_name(parts, ctx)

    if receiver:
        return f"{receiver}.{py_method}({parts.args})"
    if ctx.in_instance_method and py_method in ctx.class_methods:
        return f"self.{py_method}({parts.args})"
    return f"{py_method}({parts.args})"


def _translate_unqualified_dispatch(
    parts: _MethodInvocationParts,
    receiver: str,
    py_method: str,
    ctx: TranslationContext,
) -> str | None:
    if receiver:
        return None

    static_py_method = ctx.static_instance_static_aliases.get(py_method, py_method)
    if (
        static_py_method in ctx.class_static_methods
        and ctx.containing_class_name
        and _route_static_instance_collision_to_static(py_method, parts.args, ctx)
    ):
        return f"{ctx.containing_class_name}.{static_py_method}({parts.args})"

    enclosing_class = ctx.enclosing_static_dispatch.get(py_method)
    if enclosing_class and _route_static_instance_collision_to_static(
        py_method,
        parts.args,
        ctx,
    ):
        return f"{enclosing_class}.{static_py_method}({parts.args})"

    if parts.method_name in ctx.self_dispatch_methods and ctx.in_instance_method:
        return f"self.{py_method}({parts.args})"

    if (
        parts.method_name in ctx.static_dispatch_methods
        and ctx.static_dispatch_class_name
        and _route_static_instance_collision_to_static(py_method, parts.args, ctx)
    ):
        return f"{ctx.static_dispatch_class_name}.{static_py_method}({parts.args})"

    return None


def _translate_receiver_method_name(
    parts: _MethodInvocationParts,
    ctx: TranslationContext,
) -> str:
    if parts.receiver_nodes and _receiver_is_declared_type(parts.receiver_nodes[0], ctx):
        return translate_method_name(
            parts.method_name,
            snake_case=ctx.cfg.snake_case_methods,
        )
    return translate_attribute_method_name(
        parts.method_name,
        snake_case=ctx.cfg.snake_case_methods,
    )


def _receiver_is_declared_type(node: JavaNode, ctx: TranslationContext) -> bool:
    from j2py.translate.expr_types import _expression_py_type

    receiver_type = _expression_py_type(node, ctx)
    if receiver_type is None:
        return False
    simple = type_simple_name(receiver_type)
    if ctx.containing_class_name in {simple, receiver_type}:
        return True
    return simple in ctx.declared_type_fields or receiver_type in ctx.declared_type_fields


def _argument_nodes(args_node: JavaNode) -> list[JavaNode]:
    return [child for child in args_node.named_children if not is_comment(child)]


_ASSIGN_OR_UPDATE = frozenset({"assignment_expression", "update_expression"})


def _translate_argument(node: JavaNode, ctx: TranslationContext) -> str:
    inner = unwrap_parens(node)
    if inner.type in _ASSIGN_OR_UPDATE:
        from j2py.translate.expr_ops import _desugar_embedded_assign

        return _desugar_embedded_assign(inner, ctx)
    return translate_expression(node, ctx)

"""Static method invocation and static-import call helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_jdk_calls import translate_known_static_method_invocation
from j2py.translate.member_resolution import (
    JavaMemberBinding,
    configured_member_binding,
    static_import_binding,
    static_import_method_fallback,
)


def translate_static_method_invocation(
    node: JavaNode,
    *,
    raw_receiver: str,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    known = translate_known_static_method_invocation(
        node,
        raw_receiver=raw_receiver,
        method_name=method_name,
        arg_nodes=arg_nodes,
        args=args,
        ctx=ctx,
    )
    if known is not None:
        return known
    if raw_receiver:
        binding = configured_member_binding(
            f"{raw_receiver}.{method_name}",
            ctx.cfg,
            source="config",
        )
        if binding is not None and binding.kind in {"method", "unknown"}:
            return static_import_method_fallback(binding, args, ctx.cfg)
    return None


def translate_static_imported_method(
    node: JavaNode,
    *,
    imported_name: str,
    binding: JavaMemberBinding | None = None,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    member_binding = binding or static_import_binding(imported_name, ctx.cfg, kind="method")
    raw_receiver = member_binding.owner
    method_name = member_binding.member
    result = translate_static_method_invocation(
        node,
        raw_receiver=raw_receiver,
        method_name=method_name,
        arg_nodes=arg_nodes,
        args=args,
        ctx=ctx,
    )
    if result is not None:
        return result
    # Fallback: emit ClassName.method_name(args) for unknown receiver classes so the
    # output is always syntactically valid and reviewable rather than a bare call.
    return static_import_method_fallback(member_binding, args, ctx.cfg)

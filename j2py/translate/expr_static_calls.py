"""Static method invocation and static-import call helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_jdk_calls import translate_known_static_method_invocation
from j2py.translate.rules.naming import translate_class_name, translate_method_name


def translate_static_method_invocation(
    node: JavaNode,
    *,
    raw_receiver: str,
    method_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    return translate_known_static_method_invocation(
        node,
        raw_receiver=raw_receiver,
        method_name=method_name,
        arg_nodes=arg_nodes,
        args=args,
        ctx=ctx,
    )


def translate_static_imported_method(
    node: JavaNode,
    *,
    imported_name: str,
    arg_nodes: list[JavaNode],
    args: list[str],
    ctx: TranslationContext,
) -> str | None:
    raw_receiver, method_name = imported_name.rsplit(".", 1)
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
    class_name = translate_class_name(raw_receiver.rsplit(".", 1)[-1])
    py_method = translate_method_name(method_name, snake_case=ctx.cfg.snake_case_methods)
    return f"{class_name}.{py_method}({', '.join(args)})"

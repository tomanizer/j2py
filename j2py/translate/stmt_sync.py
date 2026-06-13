"""Synchronized statement emission helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.statements import INSTANCE_LOCK_ATTR, lock_expression_is_this, translate_body


def _translate_synchronized(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    indent: str,
) -> list[str]:
    lock = first_child_by_type(node, "parenthesized_expression")
    body = first_child_by_type(node, "block")
    if lock is None or body is None:
        ctx.diagnostics.record(node, supported=False, reason="malformed synchronized statement")
        return [f"{indent}# TODO(j2py): malformed synchronized statement", f"{indent}pass"]

    if lock_expression_is_this(lock):
        if not ctx.in_instance_method:
            ctx.diagnostics.record(
                node,
                supported=False,
                reason="synchronized(this) is invalid in static context",
            )
            return [
                f"{indent}# TODO(j2py): synchronized(this) in static context",
                f"{indent}pass",
            ]
        if ctx.class_state is not None:
            ctx.class_state.needs_instance_lock = True
        ctx.diagnostics.record(
            node,
            supported=True,
            reason="translated synchronized(this) to instance lock context manager",
        )
        lock_expr = f"self.{INSTANCE_LOCK_ATTR}"
    else:
        ctx.diagnostics.record(node, supported=True, reason="translated synchronized statement")
        ctx.diagnostics.imports.need_monitor()
        ctx.diagnostics.warn(
            node,
            reason=(
                "non-this synchronized lock wrapped with _j2py_monitor(); "
                "verify object identity matches the Java monitor"
            ),
        )
        lock_expr = f"_j2py_monitor({translate_expression(lock, ctx)})"

    lines = [f"{indent}with {lock_expr}:"]
    lines.extend(translate_body(body, ctx, indent=f"{indent}    "))
    return lines

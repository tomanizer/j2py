"""Stream pipeline expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.stream_collectors import (
    stream_collector_from_terminal,
    translate_stream_terminal,
)
from j2py.translate.stream_ops import (
    initial_stream_state,
    translate_stream_intermediates,
)
from j2py.translate.stream_sources import _stream_chain, _stream_item_name


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
    collector = stream_collector_from_terminal(node, terminal_name, terminal_arg, ctx)
    if collector is None:
        return None

    source = translate_expression(source_node, ctx)
    item_name = _stream_item_name(source, ctx)
    state = initial_stream_state(source, item_name)
    translated_state = translate_stream_intermediates(node, operations[:-1], state, ctx)
    if translated_state is None:
        return None

    return translate_stream_terminal(
        node,
        source=source,
        state=translated_state,
        collector=collector,
        terminal_arg=terminal_arg,
        ctx=ctx,
    )

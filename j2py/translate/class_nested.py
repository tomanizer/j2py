"""Nested type declaration emission for class translation."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_environment import ClassTranslationEnvironment
from j2py.translate.class_members import javadoc_docstring, type_name_of
from j2py.translate.class_model import TYPE_DECLARATION_NODES
from j2py.translate.comments import is_comment, is_javadoc_comment
from j2py.translate.diagnostics import TranslationDiagnostics


def nested_type_lines(
    body: JavaNode | None,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    env: ClassTranslationEnvironment | None = None,
    outer_capture_names: set[str] | None = None,
) -> list[str]:
    if body is None:
        return []

    from j2py.translate.classes import translate_class

    env = env or ClassTranslationEnvironment()
    lines: list[str] = []
    pending_docstring: list[str] | None = None
    capture_names = outer_capture_names or set()
    for child in body.named_children:
        if is_javadoc_comment(child):
            pending_docstring = javadoc_docstring(child, cfg, indent="    ")
            continue
        if child.type not in TYPE_DECLARATION_NODES:
            if not is_comment(child):
                pending_docstring = None
            continue
        if lines:
            lines.append("")
        requires_outer = (
            type_name_of(node=child) in capture_names and child.type == "class_declaration"
        )
        child_lines = translate_class(
            child,
            cfg,
            diagnostics,
            env=env.with_overrides(
                docstring_lines=pending_docstring,
                outer_self_alias="self._outer_self" if requires_outer else None,
                requires_outer_self=requires_outer,
            ),
        )
        pending_docstring = None
        lines.extend(f"    {line}" if line else line for line in child_lines)
    return lines

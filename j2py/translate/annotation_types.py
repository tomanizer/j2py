"""Context-aware cleanup for emitted Python type annotations."""

from __future__ import annotations

import re

from j2py.translate.diagnostics import TranslationContext
from j2py.translate.name_resolution import NameScope, scope_from_context
from j2py.translate.rules.types import translate_type

_TYPE_TOKEN = re.compile(r"(?<![\w.])([A-Z][A-Za-z_0-9]*)(?![\w.])")

_BUILTIN_OR_TYPING_NAMES = frozenset(
    {
        "Any",
        "Callable",
        "ClassVar",
        "Iterable",
        "Iterator",
        "Literal",
        "NoReturn",
        "None",
        "Protocol",
        "Self",
        "TypeVar",
    }
)


def translate_type_annotation(java_type: str, ctx: TranslationContext) -> str:
    """Translate a Java type and bind file/imported type names in context."""
    return bind_annotation_type_names(translate_type(java_type, ctx.cfg), ctx)


def split_top_level_annotation(text: str, *, delimiter: str) -> list[str]:
    """Split a Python annotation on a delimiter outside nested type groups."""

    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == delimiter and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def bind_annotation_type_names(py_type: str, ctx: TranslationContext) -> str:
    """Qualify/import type names that would otherwise be undefined in annotations."""

    scope = scope_from_context(ctx)

    def replace(match: re.Match[str]) -> str:
        raw_name = match.group(1)
        if raw_name in _BUILTIN_OR_TYPING_NAMES or len(raw_name) == 1:
            return raw_name
        resolved = ctx.name_resolver.resolve_identifier(
            raw_name,
            NameScope(
                expression_aliases=scope.expression_aliases,
                static_field_aliases=scope.static_field_aliases,
                param_names=set(),
                local_names=set(),
                class_fields=scope.class_fields,
                class_field_types=scope.class_field_types,
                enclosing_class_fields=scope.enclosing_class_fields,
                enclosing_class_field_types=scope.enclosing_class_field_types,
                outer_self_alias=scope.outer_self_alias,
                in_instance_method=scope.in_instance_method,
                in_method=True,
                containing_class_name=scope.containing_class_name,
                nested_class_names=scope.nested_class_names,
                snake_case_fields=scope.snake_case_fields,
            ),
        )
        if resolved.import_line and resolved.kind != "compilation_unit_type":
            ctx.diagnostics.imports.need_type_checking_line(resolved.import_line)
        return resolved.python_name if resolved.is_type_reference else raw_name

    return _TYPE_TOKEN.sub(replace, py_type)

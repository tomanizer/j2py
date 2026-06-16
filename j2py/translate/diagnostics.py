"""Diagnostics and shared context for rule-based translation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.name_resolution import NameResolver
from j2py.translate.runtime import (
    RUNTIME_IDIV_IMPORT_LINE,
    RUNTIME_IMPORT_LINE,
    RUNTIME_MONITOR_IMPORT_LINE,
    RUNTIME_TODO_IMPORT_LINE,
)


@dataclass(frozen=True)
class TranslationDiagnostic:
    """A single handled or unhandled Java construct observed by the rule layer."""

    node_type: str
    line: int
    text: str
    reason: str


@dataclass(frozen=True)
class PatternBinding:
    """Python binding introduced by a Java pattern expression."""

    raw_name: str
    py_name: str
    py_type: str
    source: str


@dataclass
class ImportSet:
    """Tracks imports required by emitted Python constructs."""

    lines: set[str] = field(default_factory=set)
    typing_names: set[str] = field(default_factory=set)

    def need_abc(self) -> None:
        self.lines.add("from abc import ABC, abstractmethod")

    def need_dataclass(self) -> None:
        self.lines.add("from dataclasses import dataclass")

    def need_enum(self) -> None:
        self.lines.add("from enum import Enum")

    def need_overloaded(self) -> None:
        self.lines.add(RUNTIME_IMPORT_LINE)

    def need_idiv(self) -> None:
        self.lines.add(RUNTIME_IDIV_IMPORT_LINE)

    def need_todo_sentinel(self) -> None:
        self.lines.add(RUNTIME_TODO_IMPORT_LINE)

    def need_monitor(self) -> None:
        self.lines.add(RUNTIME_MONITOR_IMPORT_LINE)

    def need_math(self) -> None:
        self.lines.add("import math")

    def need_threading(self) -> None:
        self.lines.add("import threading")

    def need_typing(self, name: str) -> None:
        self.typing_names.add(name)

    def need_line(self, line: str) -> None:
        if line:
            self.lines.add(line)

    def need_type_annotation(self, annotation: str) -> None:
        if _uses_typing_name(annotation, "Any"):
            self.need_typing("Any")

    def update(self, other: ImportSet) -> None:
        self.lines.update(other.lines)
        self.typing_names.update(other.typing_names)

    def render(self) -> list[str]:
        imports = set(self.lines)
        if self.typing_names:
            imports.add(f"from typing import {', '.join(sorted(self.typing_names))}")
        return sorted(imports)


@dataclass
class TranslationDiagnostics:
    """Tracks rule-layer coverage with source-level reasons."""

    handled: list[TranslationDiagnostic] = field(default_factory=list)
    unhandled: list[TranslationDiagnostic] = field(default_factory=list)
    warnings: list[TranslationDiagnostic] = field(default_factory=list)
    imports: ImportSet = field(default_factory=ImportSet)
    # Module-level statements emitted after all class blocks. Used for static fields
    # whose initializer references the enclosing class (e.g. a `NULL` singleton): such an
    # assignment cannot run inside the class body, where the class name is not yet bound.
    deferred_module_lines: list[str] = field(default_factory=list)

    def record(
        self,
        node: JavaNode,
        *,
        supported: bool,
        reason: str,
    ) -> None:
        diagnostic = TranslationDiagnostic(
            node_type=node.type,
            line=node.location.line,
            text=_compact_text(node.text),
            reason=reason,
        )
        if supported:
            self.handled.append(diagnostic)
        else:
            self.unhandled.append(diagnostic)

    def warn(self, node: JavaNode, *, reason: str) -> None:
        self.warnings.append(
            TranslationDiagnostic(
                node_type=node.type,
                line=node.location.line,
                text=_compact_text(node.text),
                reason=reason,
            ),
        )

    @property
    def total(self) -> int:
        return len(self.handled) + len(self.unhandled)

    @property
    def coverage(self) -> float:
        """Fraction of handled vs handled+unhandled nodes (warnings do not reduce this)."""
        if self.total == 0:
            return 0.0
        return len(self.handled) / self.total

    @property
    def semantic_warning_count(self) -> int:
        """Constructs marked handled but flagged with review warnings."""
        return len(self.warnings)

    @property
    def rule_coverage(self) -> float:
        """Alias for :attr:`coverage` — rule-layer node coverage before LLM completion."""
        return self.coverage


@dataclass
class TranslationContext:
    cfg: TranslationConfig
    diagnostics: TranslationDiagnostics
    class_fields: set[str] = field(default_factory=set)
    class_field_types: dict[str, str] = field(default_factory=dict)
    class_field_java_types: dict[str, str] = field(default_factory=dict)
    declared_type_fields: dict[str, dict[str, str]] = field(default_factory=dict)
    declared_type_java_fields: dict[str, dict[str, str]] = field(default_factory=dict)
    declared_type_method_return_types: dict[str, dict[str, str]] = field(default_factory=dict)
    class_methods: set[str] = field(default_factory=set)
    class_static_methods: set[str] = field(default_factory=set)
    # Receiverless static calls to enclosing or inherited methods map to the
    # qualifying class name (own-class siblings use class_static_methods above).
    enclosing_static_dispatch: dict[str, str] = field(default_factory=dict)
    local_names: set[str] = field(default_factory=set)
    param_names: set[str] = field(default_factory=set)
    variable_types: dict[str, str] = field(default_factory=dict)
    variable_java_types: dict[str, str] = field(default_factory=dict)
    expression_aliases: dict[str, str] = field(default_factory=dict)
    static_field_aliases: dict[str, str] = field(default_factory=dict)
    static_method_imports: dict[str, str] = field(default_factory=dict)
    name_resolver: NameResolver = field(default_factory=NameResolver.empty)
    pattern_bindings: list[PatternBinding] = field(default_factory=list)
    in_instance_method: bool = False
    allow_local_helpers: bool = False
    class_state: ClassTranslationState | None = None
    outer_self_alias: str | None = None
    inner_class_names_requiring_outer: set[str] = field(default_factory=set)
    containing_class_name: str | None = None
    nested_class_names: set[str] = field(default_factory=set)

    # Java method names that must dispatch through self when called without a
    # receiver (used for @overloaded groups so sibling overload calls re-enter
    # the runtime dispatcher; see ADR 0009).
    self_dispatch_methods: set[str] = field(default_factory=set)

    # Statements accumulated by _desugar_embedded_assign that must be emitted
    # *before* the enclosing statement.  Cleared by _flush_hoisted_pre_stmts
    # after each statement-root translate_expression call.
    hoisted_pre_stmts: list[str] = field(default_factory=list)

    # Java method name -> translated return type for the enclosing class.
    class_method_return_types: dict[str, str] = field(default_factory=dict)

    # Java static method names that must dispatch through the containing class
    # when called without a receiver (used for static @overloaded groups; see
    # ADR 0013).
    static_dispatch_methods: set[str] = field(default_factory=set)
    static_dispatch_class_name: str | None = None

    # Block lambdas (and future local helpers) are collected here during expression
    # translation and flushed near the top of the enclosing method body so the
    # generated names are in scope and the structure remains reviewable.
    pending_local_helpers: list[list[str]] = field(default_factory=list)

    # Expression visitors can surface reviewer-visible markers here; statement
    # emitters attach them as trailing comments once the full line is known.
    pending_expression_comments: list[str] = field(default_factory=list)


@dataclass
class ClassTranslationState:
    """Mutable per-class flags collected while translating a Java type."""

    needs_instance_lock: bool = False


def _compact_text(text: str, *, limit: int = 160) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: limit - 3]}..."


def _uses_typing_name(annotation: str, name: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(name)}(?![\w.])", annotation) is not None

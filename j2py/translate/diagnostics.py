"""Diagnostics and shared context for rule-based translation."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from j2py.config.loader import TranslationConfig
from j2py.framework import FrameworkMetadataRecord
from j2py.parse.java_ast import JavaNode
from j2py.translate.name_resolution import NameResolver
from j2py.translate.runtime import (
    RUNTIME_IDIV_IMPORT_LINE,
    RUNTIME_IMPORT_LINE,
    RUNTIME_MONITOR_IMPORT_LINE,
    RUNTIME_TODO_IMPORT_LINE,
)

if TYPE_CHECKING:
    from j2py.translate.class_model import ParameterInfo
    from j2py.translate.member_resolution import JavaMemberBinding, JavaOverloadCallTarget


def todo_lines(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if "TODO(j2py)" in line or "__j2py_todo__" in line
    ]


def diagnostic_payload(item: TranslationDiagnostic) -> dict[str, object]:
    return {
        "line": item.line,
        "node_type": item.node_type,
        "reason": item.reason,
        "text": item.text,
    }


@dataclass(frozen=True)
class TranslationDiagnostic:
    """A single handled or unhandled Java construct observed by the rule layer."""

    node_type: str
    line: int
    text: str
    reason: str
    category: str | None = None
    facts: dict[str, str] = field(default_factory=dict)

    @property
    def structured(self) -> dict[str, Any]:
        """Machine-readable diagnostic fields for corpus harvesters."""
        payload: dict[str, Any] = {
            "node_type": self.node_type,
            "line": self.line,
            "text": self.text,
            "reason": self.reason,
        }
        if self.category is not None:
            payload["category"] = self.category
        if self.facts:
            payload["facts"] = dict(self.facts)
        return payload


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
    type_checking_lines: set[str] = field(default_factory=set)
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

    def need_type_checking_line(self, line: str) -> None:
        if line:
            self.type_checking_lines.add(line)

    def need_type_annotation(self, annotation: str) -> None:
        for name in _TYPING_ANNOTATION_NAMES:
            if _uses_typing_name(annotation, name):
                self.need_typing(name)

    def update(self, other: ImportSet) -> None:
        self.lines.update(other.lines)
        self.type_checking_lines.update(other.type_checking_lines)
        self.typing_names.update(other.typing_names)

    def render(self) -> list[str]:
        imports = set(self.lines)
        if self.type_checking_lines:
            self.typing_names.add("TYPE_CHECKING")
        if self.typing_names:
            imports.add(f"from typing import {', '.join(_sorted_typing_names(self.typing_names))}")
        rendered = _group_import_lines(sorted(_combine_simple_from_imports(imports)))
        if self.type_checking_lines:
            rendered.append("")
            rendered.append("if TYPE_CHECKING:")
            rendered.extend(f"    {line}" for line in sorted(self.type_checking_lines))
        return rendered


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
    framework_metadata: list[FrameworkMetadataRecord] = field(default_factory=list)

    def record(
        self,
        node: JavaNode,
        *,
        supported: bool,
        reason: str,
        category: str | None = None,
        facts: dict[str, str] | None = None,
    ) -> None:
        diagnostic = TranslationDiagnostic(
            node_type=node.type,
            line=node.location.line,
            text=_compact_text(node.text),
            reason=reason,
            category=category,
            facts=dict(facts or {}),
        )
        if supported:
            self.handled.append(diagnostic)
        else:
            self.unhandled.append(diagnostic)

    def warn(
        self,
        node: JavaNode,
        *,
        reason: str,
        category: str | None = None,
        facts: dict[str, str] | None = None,
    ) -> None:
        self.warnings.append(
            TranslationDiagnostic(
                node_type=node.type,
                line=node.location.line,
                text=_compact_text(node.text),
                reason=reason,
                category=category,
                facts=dict(facts or {}),
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
    # Canonical Python method name -> emitted static overload name when static and
    # instance Java overloads share one Python name after translation.
    static_instance_static_aliases: dict[str, str] = field(default_factory=dict)
    module_static_instance_static_aliases: dict[str, dict[str, str]] = field(default_factory=dict)
    # Collision names whose instance or static overload group includes a 0-arg member.
    static_instance_instance_zero_arg_names: set[str] = field(default_factory=set)
    static_instance_static_zero_arg_names: set[str] = field(default_factory=set)
    local_names: set[str] = field(default_factory=set)
    param_names: set[str] = field(default_factory=set)
    spread_param_names: set[str] = field(default_factory=set)
    variable_types: dict[str, str] = field(default_factory=dict)
    variable_java_types: dict[str, str] = field(default_factory=dict)
    expression_aliases: dict[str, str] = field(default_factory=dict)
    static_field_aliases: dict[str, str] = field(default_factory=dict)
    static_method_imports: dict[str, str] = field(default_factory=dict)
    static_member_bindings: dict[str, JavaMemberBinding] = field(default_factory=dict)
    wildcard_static_imports: dict[str, str] = field(default_factory=dict)
    overload_call_targets: dict[str, list[JavaOverloadCallTarget]] = field(default_factory=dict)
    name_resolver: NameResolver = field(default_factory=NameResolver.empty)
    pattern_bindings: list[PatternBinding] = field(default_factory=list)
    in_instance_method: bool = False
    in_method: bool = False
    allow_local_helpers: bool = False
    class_state: ClassTranslationState | None = None
    outer_self_alias: str | None = None
    enclosing_class_fields: set[str] = field(default_factory=set)
    enclosing_class_field_types: dict[str, str] = field(default_factory=dict)
    enclosing_class_field_java_types: dict[str, str] = field(default_factory=dict)
    inner_class_names_requiring_outer: set[str] = field(default_factory=set)
    local_class_names_requiring_outer: set[str] = field(default_factory=set)
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
    # Java method name -> translated parameter signatures for the enclosing class.
    class_method_params: dict[str, tuple[tuple[ParameterInfo, ...], ...]] = field(
        default_factory=dict,
    )

    # Java static method names that must dispatch through the containing class
    # when called without a receiver (used for static @overloaded groups; see
    # ADR 0013).
    static_dispatch_methods: set[str] = field(default_factory=set)
    static_dispatch_class_name: str | None = None

    # Block lambdas (and future local helpers) are collected here during expression
    # translation and flushed near the top of the enclosing method body so the
    # generated names are in scope and the structure remains reviewable.
    pending_local_helpers: list[list[str]] = field(default_factory=list)

    # True while translating a method/constructor body. Used by _translate_identifier
    # to route same-package sibling type imports to body_local_imports (function-local)
    # instead of the module-level diagnostics.imports, breaking base↔derived circular
    # import cycles (issue #325).
    in_method_body: bool = False

    # Same-package sibling type imports accumulated during a method body translation.
    # Flushed as ``from X import Y`` lines at the start of the method body by
    # translate_method after translate_body returns.
    body_local_imports: set[str] = field(default_factory=set)

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


_TYPING_ANNOTATION_NAMES = frozenset(
    {
        "Any",
        "Annotated",
        "Callable",
        "ClassVar",
        "Iterable",
        "Iterator",
        "Optional",
        "Self",
    },
)


def _sorted_typing_names(names: set[str]) -> list[str]:
    return sorted(names, key=lambda name: (name != "TYPE_CHECKING", name))


def _group_import_lines(lines: list[str]) -> list[str]:
    stdlib = [line for line in lines if _is_stdlib_import_line(line)]
    other = [line for line in lines if not _is_stdlib_import_line(line)]
    if stdlib and other:
        return stdlib + [""] + other
    return lines


def _is_stdlib_import_line(line: str) -> bool:
    match = _IMPORT_MODULE_RE.match(line)
    return match is not None and match.group(1) in sys.stdlib_module_names


_IMPORT_MODULE_RE = re.compile(r"^(?:from|import)\s+([A-Za-z_]\w*)(?:[.\s]|$)")
_SIMPLE_FROM_IMPORT_RE = re.compile(r"^from ([A-Za-z_][\w.]*?) import ([A-Za-z_]\w*)$")


def _combine_simple_from_imports(lines: set[str]) -> set[str]:
    grouped: dict[str, set[str]] = {}
    passthrough: set[str] = set()
    for line in lines:
        match = _SIMPLE_FROM_IMPORT_RE.match(line)
        if match is None:
            passthrough.add(line)
            continue
        module, name = match.groups()
        grouped.setdefault(module, set()).add(name)
    combined = {
        f"from {module} import {', '.join(sorted(names))}" for module, names in grouped.items()
    }
    return passthrough | combined

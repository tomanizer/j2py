"""Diagnostics and shared context for rule-based translation."""

from __future__ import annotations

from dataclasses import dataclass, field

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode


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
class TranslationDiagnostics:
    """Tracks rule-layer coverage with source-level reasons."""

    handled: list[TranslationDiagnostic] = field(default_factory=list)
    unhandled: list[TranslationDiagnostic] = field(default_factory=list)
    warnings: list[TranslationDiagnostic] = field(default_factory=list)

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
    class_methods: set[str] = field(default_factory=set)
    local_names: set[str] = field(default_factory=set)
    param_names: set[str] = field(default_factory=set)
    variable_types: dict[str, str] = field(default_factory=dict)
    variable_java_types: dict[str, str] = field(default_factory=dict)
    expression_aliases: dict[str, str] = field(default_factory=dict)
    pattern_bindings: list[PatternBinding] = field(default_factory=list)
    in_instance_method: bool = False
    allow_local_helpers: bool = False
    class_state: ClassTranslationState | None = None

    # Java method names that must dispatch through self when called without a
    # receiver (used for @overloaded groups so sibling overload calls re-enter
    # the runtime dispatcher; see ADR 0009).
    self_dispatch_methods: set[str] = field(default_factory=set)

    # Block lambdas (and future local helpers) are collected here during expression
    # translation and flushed near the top of the enclosing method body so the
    # generated names are in scope and the structure remains reviewable.
    pending_local_helpers: list[list[str]] = field(default_factory=list)


@dataclass
class ClassTranslationState:
    """Mutable per-class flags collected while translating a Java type."""

    needs_instance_lock: bool = False


def _compact_text(text: str, *, limit: int = 160) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: limit - 3]}..."

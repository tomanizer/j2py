# ruff: noqa: E501
"""Pattern-family metadata for harvest repair signals → GitHub issues."""

from __future__ import annotations

from dataclasses import dataclass

# When multiple signals describe one pattern family, promote only the primary.
SIGNAL_GROUPS: tuple[tuple[str, ...], ...] = (
    (
        "protocol-stub",
        "generic-typevar",
        "jdk-import-removed",
        "anonymous-class-retained",
    ),
    (
        "overload-runtime-to-typing",
        "overload-dispatch",
        "runtime-not-implemented-stub",
    ),
)


@dataclass(frozen=True)
class SignalPattern:
    signal: str
    title: str
    family: str
    ast_or_diagnostic: str
    harvest_signals: str
    translator_home: str
    mapping: str
    related_issues: str
    out_of_scope: str


PATTERN_BY_SIGNAL: dict[str, SignalPattern] = {
    "unsupported-stmt-removed": SignalPattern(
        signal="unsupported-stmt-removed",
        title="Rule layer: unsupported Java statements → Python (harvest: unsupported-stmt-removed)",
        family="Java statements the rule layer marks `# TODO(j2py): unsupported …` — implement the general statement visitor rule, not one file.",
        ast_or_diagnostic="`unsupported statement <node_type>` (e.g. `assert_statement`)",
        harvest_signals="unsupported-stmt-removed",
        translator_home="`j2py/translate/statements.py`",
        mapping="Map each supported statement node to Python (e.g. `assert cond : msg` → `assert cond, msg`).",
        related_issues="#294 if open",
        out_of_scope="LLM prompt changes; filename-specific branches.",
    ),
    "todo-placeholder-removed": SignalPattern(
        signal="todo-placeholder-removed",
        title="Rule layer: replace __j2py_todo__ placeholders (harvest: todo-placeholder-removed)",
        family="Expression/statement shapes that emit `__j2py_todo__` or leave coverage gaps — fix the AST handler for the diagnostic reason, not one literal string.",
        ast_or_diagnostic="Rule-layer `unhandled` reason (e.g. multidimensional array creation)",
        harvest_signals="todo-placeholder-removed",
        translator_home="`j2py/translate/expr_*.py`, `statements.py`",
        mapping="Deterministic Python for the construct class (e.g. nested list allocation for `new T[a][b]`).",
        related_issues="#295 if open",
        out_of_scope="Copying one LLM diff; matching a single `__j2py_todo__` string.",
    ),
    "protocol-stub": SignalPattern(
        signal="protocol-stub",
        title="Rule layer: JDK interface typing via Protocol stubs (harvest: protocol-stub)",
        family="JDK interfaces (`java.util.Comparator`, `Callable`, …) used as types — registry + in-module Protocol stubs so skeleton passes mypy without LLM.",
        ast_or_diagnostic="Pre-LLM mypy: `Name \"Comparator\" is not defined`, missing Protocol",
        harvest_signals="protocol-stub, generic-typevar, jdk-import-removed, anonymous-class-retained",
        translator_home="`j2py/translate/name_resolution.py`, `class_nested.py`, type registry",
        mapping="FQN → Protocol/class stub; anonymous implementors type-check.",
        related_issues="#296, #298 if open",
        out_of_scope="Full JDK stub library; filename checks.",
    ),
    "jdk-import-removed": SignalPattern(
        signal="jdk-import-removed",
        title="Rule layer: JDK/platform import registry (harvest: jdk-import-removed)",
        family="Never emit invalid Python imports (`from javax.*`, `from java.*`, bogus Spring paths) — central registry maps FQN to stubs.",
        ast_or_diagnostic="Invalid `from … import …` lines in skeleton",
        harvest_signals="jdk-import-removed",
        translator_home="`j2py/translate/name_resolution.py`, import emission",
        mapping="Java FQN → local stub or valid Python import policy.",
        related_issues="#298 if open",
        out_of_scope="Per-file import deletion post-pass.",
    ),
    "adapter-class-introduced": SignalPattern(
        signal="adapter-class-introduced",
        title="Rule layer: interface static factory adapters (harvest: adapter-class-introduced)",
        family="Interface static methods returning the interface type (`noop()`, factories) → concrete adapter class in skeleton, not LLM-only wrappers.",
        ast_or_diagnostic="Static factory on interface; mypy repair on return type",
        harvest_signals="adapter-class-introduced",
        translator_home="`j2py/translate/class_methods.py`, interface modules",
        mapping="`static <U> IFoo<U> factory()` → named adapter implementing abstract methods.",
        related_issues="#299 if open",
        out_of_scope="Hardcoding one interface name (`InterfaceDefaults` only).",
    ),
    "overload-runtime-to-typing": SignalPattern(
        signal="overload-runtime-to-typing",
        title="Rule layer: static overload groups + platform stubs (harvest: overload-runtime-to-typing)",
        family="Static overload groups still emitting `j2py_runtime.overloaded` — migrate to `@typing.overload` + dispatcher; add platform type stubs where needed.",
        ast_or_diagnostic="@overloaded in skeleton; static factory overloads (e.g. `ObjectName.getInstance`)",
        harvest_signals="overload-dispatch, overload-runtime-to-typing, runtime-not-implemented-stub",
        translator_home="`j2py/translate/overloads.py`, type registry",
        mapping="Static overload tier in `overloads.py`; JMX/platform placeholders via registry.",
        related_issues="#300, #290 if open (#290 = instance append overloads)",
        out_of_scope="ObjectNameManager-only string hacks.",
    ),
}


def primary_signal(signal: str) -> str:
    """Map a signal to its group primary (first listed signal in group)."""
    for group in SIGNAL_GROUPS:
        if signal in group:
            return group[0]
    return signal


def grouped_rank(signals: list[str]) -> list[str]:
    """Rank signal names, one entry per pattern group."""
    ranked: list[str] = []
    seen_groups: set[tuple[str, ...]] = set()
    for signal in signals:
        group = next((g for g in SIGNAL_GROUPS if signal in g), (signal,))
        if group in seen_groups:
            continue
        seen_groups.add(group)
        ranked.append(group[0])
    return ranked

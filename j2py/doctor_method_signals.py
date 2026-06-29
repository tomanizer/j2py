"""Class and method-level assessment signals for doctor reports."""

from __future__ import annotations

from typing import Any

from j2py.doctor_readiness import migration_readiness_profile
from j2py.parse.java_ast import JavaNode

_CLASS_DECLARATION_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration",
    }
)
_IMPLICIT_PUBLIC_METHOD_OWNER_TYPES = frozenset(
    {"interface_declaration", "annotation_type_declaration"}
)
_METHOD_DECLARATION_TYPES = frozenset(
    {"method_declaration", "constructor_declaration", "compact_constructor_declaration"}
)
_TODO_MARKERS = ("TODO", "FIXME")


def class_method_signal_index(
    root: JavaNode,
    *,
    translation: dict[str, Any],
    parse_ok: bool,
) -> dict[str, dict[str, Any]]:
    """Return class-level signals keyed by dotted class name within the Java file."""
    semantic_warnings = list(translation.get("semantic_warnings", []))
    unhandled = list(translation.get("unhandled", []))
    signals: dict[str, dict[str, Any]] = {}
    for child in root.named_children:
        if child.type in _CLASS_DECLARATION_TYPES:
            _collect_class_signal(
                child,
                parse_ok=parse_ok,
                parent_class_name=None,
                semantic_warnings=semantic_warnings,
                unhandled=unhandled,
                signals=signals,
            )
    return signals


def _collect_class_signal(
    node: JavaNode,
    *,
    parse_ok: bool,
    parent_class_name: str | None,
    semantic_warnings: list[dict[str, Any]],
    unhandled: list[dict[str, Any]],
    signals: dict[str, dict[str, Any]],
) -> None:
    name_node = node.child_by_field("name")
    if name_node is None:
        return

    class_name = f"{parent_class_name}.{name_node.text}" if parent_class_name else name_node.text
    current_implicit_public = node.type in _IMPLICIT_PUBLIC_METHOD_OWNER_TYPES
    class_warnings = _diagnostics_in_range(semantic_warnings, node)
    class_unhandled = _diagnostics_in_range(unhandled, node)
    source_todo_count = _source_todo_count(node)
    methods = _direct_method_signals(
        node,
        class_name=class_name,
        parse_ok=parse_ok,
        implicit_public_methods=current_implicit_public,
        semantic_warnings=semantic_warnings,
        unhandled=unhandled,
    )
    profile = _readiness_profile(
        parse_ok=parse_ok,
        semantic_warnings=class_warnings,
        unhandled=class_unhandled,
        source_todo_count=source_todo_count,
    )
    signals[class_name] = {
        "qualified_name": class_name,
        "end_line": node.location.end_line,
        "range_source": "tree_sitter_node_range",
        "diagnostics": _diagnostic_counts(
            class_warnings,
            class_unhandled,
            source_todo_count=source_todo_count,
        ),
        "migration_readiness": profile,
        "risk_score": profile["risk_score"],
        "risk_band": profile["risk_band"],
        "methods": methods,
    }

    body = node.child_by_field("body")
    if body is None:
        return
    for child in body.named_children:
        if child.type in _CLASS_DECLARATION_TYPES:
            _collect_class_signal(
                child,
                parse_ok=parse_ok,
                parent_class_name=class_name,
                semantic_warnings=semantic_warnings,
                unhandled=unhandled,
                signals=signals,
            )


def _direct_method_signals(
    class_node: JavaNode,
    *,
    class_name: str,
    parse_ok: bool,
    implicit_public_methods: bool,
    semantic_warnings: list[dict[str, Any]],
    unhandled: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    body = class_node.child_by_field("body")
    if body is None:
        return []

    methods: list[dict[str, Any]] = []
    for child in body.named_children:
        if child.type not in _METHOD_DECLARATION_TYPES:
            continue
        signal = _method_signal(
            child,
            class_name=class_name,
            parse_ok=parse_ok,
            implicit_public_methods=implicit_public_methods,
            semantic_warnings=semantic_warnings,
            unhandled=unhandled,
        )
        if signal is not None:
            methods.append(signal)
    return sorted(methods, key=lambda item: (item["line"], item["name"], item["signature"]))


def _method_signal(
    node: JavaNode,
    *,
    class_name: str,
    parse_ok: bool,
    implicit_public_methods: bool,
    semantic_warnings: list[dict[str, Any]],
    unhandled: list[dict[str, Any]],
) -> dict[str, Any] | None:
    constructor = node.type in {"constructor_declaration", "compact_constructor_declaration"}
    name_node = node.child_by_field("name")
    if name_node is None:
        name = class_name.rsplit(".", 1)[-1] if constructor else "<unknown>"
    else:
        name = name_node.text

    modifier_words = _modifier_words(node)
    visibility = _visibility(modifier_words, implicit_public_methods)
    params = _parameters(node)
    return_type_node = node.child_by_field("type")
    return_type = None if constructor else (return_type_node.text if return_type_node else "void")
    method_warnings = _diagnostics_in_range(semantic_warnings, node)
    method_unhandled = _diagnostics_in_range(unhandled, node)
    source_todo_count = _source_todo_count(node)
    profile = _readiness_profile(
        parse_ok=parse_ok,
        semantic_warnings=method_warnings,
        unhandled=method_unhandled,
        source_todo_count=source_todo_count,
    )
    has_body = node.child_by_field("body") is not None
    equivalence_candidate = (
        visibility == "public" and not constructor and "abstract" not in modifier_words and has_body
    )
    return {
        "name": name,
        "signature": f"{class_name}.{name}({','.join(param['java_type'] for param in params)})",
        "line": node.location.line,
        "end_line": node.location.end_line,
        "range_source": "tree_sitter_node_range",
        "return_type": return_type,
        "parameters": params,
        "static": "static" in modifier_words,
        "constructor": constructor,
        "abstract": "abstract" in modifier_words,
        "public": visibility == "public",
        "visibility": visibility,
        "diagnostics": _diagnostic_counts(
            method_warnings,
            method_unhandled,
            source_todo_count=source_todo_count,
        ),
        "migration_readiness": profile,
        "risk_score": profile["risk_score"],
        "risk_band": profile["risk_band"],
        "readiness_bucket": profile["bucket"],
        "equivalence_candidate": equivalence_candidate,
        "equivalence_candidate_reason": _equivalence_candidate_reason(
            equivalence_candidate,
            visibility=visibility,
            constructor=constructor,
            abstract="abstract" in modifier_words,
            has_body=has_body,
        ),
        "diagnostic_mapping_source": "source_line_containment",
    }


def _readiness_profile(
    *,
    parse_ok: bool,
    semantic_warnings: list[dict[str, Any]],
    unhandled: list[dict[str, Any]],
    source_todo_count: int,
) -> dict[str, Any]:
    profile = migration_readiness_profile(
        parse_ok=parse_ok,
        parse_error_count=0 if parse_ok else 1,
        rule_coverage=1.0,
        semantic_warnings=semantic_warnings,
        unhandled=unhandled,
        todo_count=source_todo_count,
        unresolved_imports=[],
        annotations=[],
        validation=None,
    )
    if source_todo_count:
        profile = {
            **profile,
            "reasons": [
                _source_todo_reason(reason) if reason.get("reason") == "todo_markers" else reason
                for reason in profile["reasons"]
            ],
        }
    return profile


def _source_todo_reason(reason: dict[str, Any]) -> dict[str, Any]:
    return {
        **reason,
        "detail": "Java source contains TODO/FIXME markers in this scope",
    }


def _diagnostic_counts(
    semantic_warnings: list[dict[str, Any]],
    unhandled: list[dict[str, Any]],
    *,
    source_todo_count: int,
) -> dict[str, Any]:
    return {
        "semantic_warnings": len(semantic_warnings),
        "unhandled": len(unhandled),
        "todos": source_todo_count,
        "source": "source_line_containment",
        "todo_source": "java_source_comments",
    }


def _diagnostics_in_range(
    diagnostics: list[dict[str, Any]],
    node: JavaNode,
) -> list[dict[str, Any]]:
    start = node.location.line
    end = node.location.end_line
    return [
        diagnostic
        for diagnostic in diagnostics
        if isinstance(diagnostic.get("line"), int) and start <= int(diagnostic["line"]) <= end
    ]


def _source_todo_count(node: JavaNode) -> int:
    return sum(
        1
        for line in node.text.splitlines()
        if any(marker in line.upper() for marker in _TODO_MARKERS)
    )


def _modifier_words(node: JavaNode) -> set[str]:
    words: set[str] = set()
    for child in node.children:
        if child.type == "modifiers":
            words.update(child.text.split())
    return words


def _visibility(modifier_words: set[str], implicit_public: bool) -> str:
    if "public" in modifier_words or (implicit_public and "private" not in modifier_words):
        return "public"
    if "protected" in modifier_words:
        return "protected"
    if "private" in modifier_words:
        return "private"
    return "package_private"


def _parameters(method_node: JavaNode) -> list[dict[str, Any]]:
    params = method_node.child_by_field("parameters")
    if params is None:
        return []
    result: list[dict[str, Any]] = []
    for param in params.named_children:
        if param.type not in {"formal_parameter", "spread_parameter"}:
            continue
        type_node = _first_type_child(param)
        name_node = param.child_by_field("name")
        java_type = _compact_type(type_node.text) if type_node is not None else "Object"
        is_varargs = param.type == "spread_parameter"
        result.append(
            {
                "name": name_node.text if name_node is not None else "_",
                "java_type": f"{java_type}..." if is_varargs else java_type,
                "varargs": is_varargs,
            }
        )
    return result


def _first_type_child(param: JavaNode) -> JavaNode | None:
    for child in param.named_children:
        if child.type in {"modifiers", "variable_declarator", "identifier"}:
            continue
        return child
    return None


def _compact_type(text: str) -> str:
    return "".join(text.split())


def _equivalence_candidate_reason(
    candidate: bool,
    *,
    visibility: str,
    constructor: bool,
    abstract: bool,
    has_body: bool,
) -> str:
    if candidate:
        return "public concrete method with equivalence-surface signature"
    if constructor:
        return "constructors are not equivalence surface methods"
    if visibility != "public":
        return "method is not public"
    if abstract:
        return "abstract method has no executable body"
    if not has_body:
        return "method has no executable body"
    return "method is not an equivalence candidate"

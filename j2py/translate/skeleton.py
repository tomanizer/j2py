"""Rule-based skeleton generator for the deterministic translation layer."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode, ParsedFile
from j2py.translate.class_fields import (
    _collect_declared_type_fields,
    _collect_declared_type_java_fields,
)
from j2py.translate.class_methods import collect_declared_type_method_return_types
from j2py.translate.class_model import TYPE_DECLARATION_NODES
from j2py.translate.classes import collect_file_class_static_methods, translate_class
from j2py.translate.comments import is_comment, is_javadoc_comment
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.name_resolution import (
    NameResolver,
    build_file_name_bindings,
    is_static_import,
    java_import_name,
)
from j2py.translate.rules.imports import java_import_policy
from j2py.translate.rules.naming import translate_class_name, translate_field_name
from j2py.translate.rules.static_imports import (
    is_known_static_method_import,
    known_static_field_alias,
)


@dataclass
class SkeletonTranslation:
    """Rule-layer output plus structured diagnostic details."""

    source: str
    coverage: float
    diagnostics: TranslationDiagnostics


def translate_skeleton(
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
) -> tuple[str, float]:
    """Produce a partial Python translation and a coverage estimate.

    Returns:
        (skeleton_source, coverage) where coverage is 0.0-1.0.
        Coverage < 1.0 triggers the LLM layer.
    """
    result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)
    return result.source, result.coverage


def translate_skeleton_with_diagnostics(
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
) -> SkeletonTranslation:
    """Produce a partial Python translation with structured coverage diagnostics."""
    diagnostics = TranslationDiagnostics()
    static_field_aliases, static_method_imports, static_import_todos = _static_import_info(
        parsed,
        diagnostics,
        cfg,
    )
    file_name_bindings = build_file_name_bindings(
        parsed,
        symbols,
        cfg,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
    )
    name_resolver = NameResolver(file_name_bindings)
    module_declared_type_fields = _module_declared_type_fields(parsed, cfg)
    module_declared_type_java_fields = _module_declared_type_java_fields(parsed, cfg)
    module_declared_type_method_return_types = _module_declared_type_method_return_types(
        parsed,
        cfg,
    )
    file_class_static_methods = collect_file_class_static_methods(parsed.root, cfg)
    class_blocks: list[list[str]] = []
    pending_docstring: list[str] | None = None
    for class_node in parsed.root.named_children:
        if is_javadoc_comment(class_node):
            pending_docstring = _javadoc_docstring(class_node, cfg, indent="    ")
            continue
        if class_node.type not in TYPE_DECLARATION_NODES:
            if not is_comment(class_node):
                pending_docstring = None
            continue
        class_blocks.append(
            translate_class(
                class_node,
                cfg,
                diagnostics,
                static_field_aliases=static_field_aliases,
                static_method_imports=static_method_imports,
                name_resolver=name_resolver,
                docstring_lines=pending_docstring,
                inherited_declared_type_fields=module_declared_type_fields,
                inherited_declared_type_java_fields=module_declared_type_java_fields,
                inherited_declared_type_method_return_types=(
                    module_declared_type_method_return_types
                ),
                file_class_static_methods=file_class_static_methods,
            )
        )
        pending_docstring = None

    lines = ["from __future__ import annotations"]
    import_lines = _import_lines(parsed, cfg, diagnostics, static_import_todos)
    if import_lines:
        lines.append("")
        lines.extend(import_lines)
    lines.extend(["", ""])

    for index, block in enumerate(class_blocks):
        if index:
            lines.append("")
            lines.append("")
        lines.extend(block)

    if diagnostics.deferred_module_lines:
        lines.append("")
        lines.append("")
        lines.extend(diagnostics.deferred_module_lines)

    return SkeletonTranslation(
        source="\n".join(lines) + "\n",
        coverage=diagnostics.coverage,
        diagnostics=diagnostics,
    )


def _module_declared_type_fields(
    parsed: ParsedFile,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    fields: dict[str, dict[str, str]] = {}
    for class_node in parsed.root.named_children:
        if class_node.type in TYPE_DECLARATION_NODES:
            fields.update(_collect_declared_type_fields(class_node, cfg))
    return fields


def _module_declared_type_java_fields(
    parsed: ParsedFile,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    fields: dict[str, dict[str, str]] = {}
    for class_node in parsed.root.named_children:
        if class_node.type in TYPE_DECLARATION_NODES:
            fields.update(_collect_declared_type_java_fields(class_node, cfg))
    return fields


def _module_declared_type_method_return_types(
    parsed: ParsedFile,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    method_return_types: dict[str, dict[str, str]] = {}
    for class_node in parsed.root.named_children:
        if class_node.type in TYPE_DECLARATION_NODES:
            method_return_types.update(collect_declared_type_method_return_types(class_node, cfg))
    return method_return_types


def _javadoc_docstring(
    node: JavaNode,
    cfg: TranslationConfig,
    *,
    indent: str,
) -> list[str] | None:
    if not cfg.emit_line_comments:
        return None
    if not cfg.emit_docstrings:
        from j2py.translate.comments import translate_comment

        return translate_comment(node, indent=indent)
    from j2py.translate.comments import translate_javadoc_docstring

    return translate_javadoc_docstring(node, indent=indent)


def _import_lines(
    parsed: ParsedFile,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    static_import_todos: list[str] | None = None,
) -> list[str]:
    imports: set[str] = set()
    for java_import in parsed.root.find_all("import_declaration"):
        if is_static_import(java_import):
            continue
        imported_name = java_import_name(java_import)
        if not imported_name:
            continue
        policy = java_import_policy(imported_name, cfg)
        if policy is not None:
            imports.update(policy.import_lines)

    imports.update(diagnostics.imports.render())
    imports.update(static_import_todos or [])
    return sorted(imports)


def _static_import_info(
    parsed: ParsedFile,
    diagnostics: TranslationDiagnostics,
    cfg: TranslationConfig,
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    field_aliases: dict[str, str] = {}
    method_imports: dict[str, str] = {}
    todos: list[str] = []
    for java_import in parsed.root.find_all("import_declaration"):
        if not is_static_import(java_import):
            continue
        imported_name = java_import_name(java_import)
        if not imported_name:
            diagnostics.record(
                java_import,
                supported=False,
                reason="malformed static import declaration",
            )
            todos.append("# TODO(j2py): malformed static import declaration")
            continue
        member = imported_name.rsplit(".", 1)[-1]
        field_alias = known_static_field_alias(imported_name)
        if field_alias is not None:
            field_aliases[member] = field_alias
            diagnostics.record(
                java_import,
                supported=True,
                reason="translated known static field import",
            )
            continue
        if is_known_static_method_import(imported_name):
            method_imports[member] = imported_name
            diagnostics.record(
                java_import,
                supported=True,
                reason="translated known static method import",
            )
            continue
        diagnostics.record(
            java_import,
            supported=False,
            reason=f"unknown static import {imported_name}",
        )
        todos.append(f"# TODO(j2py): static import {imported_name} - resolve manually")
        # Register a syntax-safe fallback so the name always resolves to valid Python.
        # - field_alias: ClassName.member for identifier uses
        # - method_imports: FQN for call sites (handled via qualified fallback in expr_calls)
        declaring_class = imported_name.rsplit(".", 2)[-2] if imported_name.count(".") >= 2 else ""
        if declaring_class:
            py_class = translate_class_name(declaring_class)
            py_member = translate_field_name(member, snake_case=cfg.snake_case_fields)
            field_aliases[member] = f"{py_class}.{py_member}"
        method_imports[member] = imported_name
    return field_aliases, method_imports, todos

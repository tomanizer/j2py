"""Rule-based skeleton generator for the deterministic translation layer."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode, ParsedFile
from j2py.translate.class_fields import (
    _collect_declared_type_fields,
    _collect_declared_type_java_fields,
)
from j2py.translate.class_model import TYPE_DECLARATION_NODES
from j2py.translate.classes import collect_file_class_static_methods, translate_class
from j2py.translate.comments import is_comment, is_javadoc_comment
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.rules.naming import translate_class_name
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
    )
    imported_type_names, imported_type_imports = _imported_type_bindings(parsed, cfg)
    diagnostics.imported_type_names.update(imported_type_names)
    diagnostics.imported_type_imports.update(imported_type_imports)
    diagnostics.package_name = symbols.package
    module_declared_type_fields = _module_declared_type_fields(parsed, cfg)
    module_declared_type_java_fields = _module_declared_type_java_fields(parsed, cfg)
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
                docstring_lines=pending_docstring,
                inherited_declared_type_fields=module_declared_type_fields,
                inherited_declared_type_java_fields=module_declared_type_java_fields,
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
        if _is_static_import(java_import):
            continue
        imported_name = _java_import_name(java_import)
        if not imported_name or imported_name in cfg.drop_imports:
            continue
        mapped = cfg.import_map.get(imported_name)
        if mapped:
            imports.update(line for line in mapped.splitlines() if line.strip())

    imports.update(diagnostics.imports.render())
    imports.update(static_import_todos or [])
    return sorted(imports)


def _imported_type_bindings(
    parsed: ParsedFile,
    cfg: TranslationConfig,
) -> tuple[dict[str, str], dict[str, str]]:
    names: dict[str, str] = {}
    imports: dict[str, str] = {}
    for java_import in parsed.root.find_all("import_declaration"):
        if _is_static_import(java_import):
            continue
        imported_name = _java_import_name(java_import)
        if not imported_name or imported_name in cfg.drop_imports:
            continue
        raw_name = imported_name.rsplit(".", 1)[-1]
        mapped = cfg.import_map.get(imported_name)
        if mapped is not None:
            binding = _python_binding_from_import_map(mapped)
            if binding is not None:
                names[raw_name] = binding
            continue
        py_name = translate_class_name(raw_name)
        names[raw_name] = py_name
        package, _, _ = imported_name.rpartition(".")
        if package:
            imports[raw_name] = f"from {package}.{py_name} import {py_name}"
    return names, imports


def _python_binding_from_import_map(import_text: str) -> str | None:
    for line in import_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            module = ast.parse(stripped)
        except SyntaxError:
            continue
        if len(module.body) != 1:
            continue
        statement = module.body[0]
        if isinstance(statement, ast.ImportFrom) and statement.names:
            alias = statement.names[0]
            return alias.asname or alias.name
        if isinstance(statement, ast.Import) and statement.names:
            alias = statement.names[0]
            return alias.asname or alias.name.split(".", 1)[0]
    return None


def _java_import_name(node: JavaNode) -> str:
    for child in node.walk():
        if child.type in {"scoped_identifier", "identifier"}:
            return child.text
    return ""


def _is_static_import(node: JavaNode) -> bool:
    return any(child.type == "static" for child in node.children)


def _static_import_info(
    parsed: ParsedFile,
    diagnostics: TranslationDiagnostics,
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    field_aliases: dict[str, str] = {}
    method_imports: dict[str, str] = {}
    todos: list[str] = []
    for java_import in parsed.root.find_all("import_declaration"):
        if not _is_static_import(java_import):
            continue
        imported_name = _java_import_name(java_import)
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
    return field_aliases, method_imports, todos

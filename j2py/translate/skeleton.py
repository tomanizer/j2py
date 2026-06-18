"""Rule-based skeleton generator for the deterministic translation layer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode, ParsedFile
from j2py.translate.class_environment import ClassTranslationEnvironment
from j2py.translate.class_fields import (
    _collect_declared_type_fields,
    _collect_declared_type_java_fields,
)
from j2py.translate.class_interfaces import interface_type_var_plan
from j2py.translate.class_members import (
    collect_file_class_declarations,
    collect_file_class_static_instance_aliases,
)
from j2py.translate.class_methods import collect_declared_type_method_return_types
from j2py.translate.class_model import TYPE_DECLARATION_NODES
from j2py.translate.classes import collect_file_class_static_methods, translate_class
from j2py.translate.comments import is_comment, is_javadoc_comment
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.member_resolution import (
    JavaMemberBinding,
    static_import_binding,
    static_import_field_fallback,
)
from j2py.translate.name_resolution import (
    NameResolver,
    build_file_name_bindings,
    is_static_import,
    java_import_name,
)
from j2py.translate.rules.imports import java_import_policy
from j2py.translate.rules.static_imports import (
    is_known_static_method_import,
    known_static_field_alias,
)
from j2py.translate.spring_model import collect_pydantic_model_class_names
from j2py.translate.sqlalchemy_model import collect_sqlalchemy_entity_table_names


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
    *,
    module_class_static_methods: dict[str, set[str]] | None = None,
    module_class_static_instance_aliases: dict[str, dict[str, str]] | None = None,
    module_class_declarations: dict[str, JavaNode] | None = None,
) -> SkeletonTranslation:
    """Produce a partial Python translation with structured coverage diagnostics."""
    diagnostics = TranslationDiagnostics()
    (
        static_field_aliases,
        static_method_imports,
        static_member_bindings,
        wildcard_static_imports,
        static_import_todos,
    ) = _static_import_info(parsed, diagnostics, cfg)
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
    file_class_static_instance_aliases = collect_file_class_static_instance_aliases(
        parsed.root,
        cfg,
    )
    file_class_declarations = collect_file_class_declarations(parsed.root)
    type_var_plan = interface_type_var_plan(parsed.root, cfg, diagnostics)
    pydantic_model_class_names = collect_pydantic_model_class_names(parsed.root, cfg)
    sqlalchemy_entity_table_names = collect_sqlalchemy_entity_table_names(parsed.root, cfg)
    class_env = ClassTranslationEnvironment(
        inherited_declared_type_fields=module_declared_type_fields,
        inherited_declared_type_java_fields=module_declared_type_java_fields,
        inherited_declared_type_method_return_types=module_declared_type_method_return_types,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
        static_member_bindings=static_member_bindings,
        wildcard_static_imports=wildcard_static_imports,
        name_resolver=name_resolver,
        file_class_static_methods=file_class_static_methods,
        file_class_static_instance_aliases=file_class_static_instance_aliases,
        file_class_declarations=file_class_declarations,
        module_class_static_methods=module_class_static_methods or {},
        module_class_static_instance_aliases=module_class_static_instance_aliases or {},
        module_class_declarations=module_class_declarations or {},
        pydantic_model_class_names=pydantic_model_class_names,
        sqlalchemy_entity_table_names=sqlalchemy_entity_table_names,
        interface_type_var_maps=type_var_plan.interface_type_var_maps,
    )
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
                env=class_env.with_overrides(docstring_lines=pending_docstring),
            )
        )
        pending_docstring = None

    if sqlalchemy_entity_table_names:
        diagnostics.imports.need_line("from sqlalchemy.orm import DeclarativeBase")

    lines = ["from __future__ import annotations"]
    import_lines = _import_lines(parsed, cfg, diagnostics, static_import_todos)
    if import_lines:
        lines.append("")
        lines.extend(import_lines)
    lines.extend(["", ""])

    if type_var_plan.declaration_lines:
        lines.extend(type_var_plan.declaration_lines)
        lines.extend(["", ""])

    if sqlalchemy_entity_table_names:
        lines.extend(["class Base(DeclarativeBase):", "    pass", "", ""])

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
    return _module_declared_type_map(parsed, cfg, _collect_declared_type_fields)


def _module_declared_type_java_fields(
    parsed: ParsedFile,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    return _module_declared_type_map(parsed, cfg, _collect_declared_type_java_fields)


def _module_declared_type_method_return_types(
    parsed: ParsedFile,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    return _module_declared_type_map(
        parsed,
        cfg,
        collect_declared_type_method_return_types,
    )


def _module_declared_type_map(
    parsed: ParsedFile,
    cfg: TranslationConfig,
    collector: Callable[[JavaNode, TranslationConfig], dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    declared_types: dict[str, dict[str, str]] = {}
    for class_node in parsed.root.named_children:
        if class_node.type in TYPE_DECLARATION_NODES:
            declared_types.update(collector(class_node, cfg))
    return declared_types


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
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, JavaMemberBinding],
    dict[str, str],
    list[str],
]:
    field_aliases: dict[str, str] = {}
    method_imports: dict[str, str] = {}
    member_bindings: dict[str, JavaMemberBinding] = {}
    wildcard_imports: dict[str, str] = {}
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
        if ".*" in java_import.text:
            owner = imported_name
            wildcard_imports[owner.rsplit(".", 1)[-1]] = owner
            diagnostics.warn(
                java_import,
                reason=f"wildcard static import {owner}.* requires local/configured member facts",
                category="wildcard_static_import_unresolved",
                facts={"owner": owner},
            )
            continue
        field_alias = known_static_field_alias(imported_name)
        if field_alias is not None:
            binding = static_import_binding(
                imported_name,
                cfg,
                kind="field",
                intrinsic=field_alias,
            )
            field_aliases[member] = binding.intrinsic or field_alias
            member_bindings[member] = binding
            diagnostics.record(
                java_import,
                supported=True,
                reason="bound known static field import",
            )
            continue
        if is_known_static_method_import(imported_name):
            binding = static_import_binding(
                imported_name,
                cfg,
                kind="method",
                intrinsic=imported_name,
            )
            method_imports[member] = f"{binding.owner}.{binding.member}"
            member_bindings[member] = binding
            diagnostics.record(
                java_import,
                supported=True,
                reason="bound known static method import",
            )
            continue
        binding = static_import_binding(imported_name, cfg, kind="unknown")
        if binding.kind == "field":
            field_aliases[member] = static_import_field_fallback(binding, cfg)
            member_bindings[member] = binding
            diagnostics.record(
                java_import,
                supported=True,
                reason="bound configured static field import",
            )
            continue
        if binding.kind == "method":
            method_imports[member] = f"{binding.owner}.{binding.member}"
            member_bindings[member] = binding
            diagnostics.record(
                java_import,
                supported=True,
                reason="bound configured static method import",
            )
            continue
        diagnostics.record(
            java_import,
            supported=True,
            reason=f"bound explicit static import fallback {imported_name}",
        )
        diagnostics.warn(
            java_import,
            reason=(
                f"static import {imported_name} emitted as qualified fallback; "
                "verify external member semantics"
            ),
        )
        # Register syntax-safe fallbacks so both identifier and call sites stay reviewable.
        field_aliases[member] = static_import_field_fallback(binding, cfg)
        method_imports[member] = imported_name
        member_bindings[member] = binding
    return field_aliases, method_imports, member_bindings, wildcard_imports, todos

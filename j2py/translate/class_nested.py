"""Nested type declaration emission for class translation."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_members import javadoc_docstring, type_name_of
from j2py.translate.class_model import TYPE_DECLARATION_NODES
from j2py.translate.comments import is_comment, is_javadoc_comment
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.name_resolution import NameResolver


def nested_type_lines(
    body: JavaNode | None,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    inherited_class_field_types: dict[str, str],
    inherited_class_field_java_types: dict[str, str],
    inherited_declared_type_fields: dict[str, dict[str, str]],
    inherited_declared_type_java_fields: dict[str, dict[str, str]],
    inherited_declared_type_method_return_types: dict[str, dict[str, str]],
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    outer_capture_names: set[str] | None = None,
    file_class_static_methods: dict[str, set[str]] | None = None,
    file_class_static_instance_aliases: dict[str, dict[str, str]] | None = None,
    file_class_declarations: dict[str, JavaNode] | None = None,
    module_class_static_methods: dict[str, set[str]] | None = None,
    module_class_static_instance_aliases: dict[str, dict[str, str]] | None = None,
    module_class_declarations: dict[str, JavaNode] | None = None,
    enclosing_static_dispatch: dict[str, str] | None = None,
    interface_type_var_maps: dict[tuple[int, int, int, int, str], dict[str, str]] | None = None,
) -> list[str]:
    if body is None:
        return []

    from j2py.translate.classes import translate_class

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
        child_lines = translate_class(
            child,
            cfg,
            diagnostics,
            inherited_class_field_types=inherited_class_field_types,
            inherited_class_field_java_types=inherited_class_field_java_types,
            inherited_declared_type_fields=inherited_declared_type_fields,
            inherited_declared_type_java_fields=inherited_declared_type_java_fields,
            inherited_declared_type_method_return_types=(
                inherited_declared_type_method_return_types
            ),
            static_field_aliases=static_field_aliases,
            static_method_imports=static_method_imports,
            name_resolver=name_resolver,
            docstring_lines=pending_docstring,
            outer_self_alias=(
                "self._outer_self"
                if type_name_of(node=child) in capture_names and child.type == "class_declaration"
                else None
            ),
            requires_outer_self=(
                type_name_of(node=child) in capture_names and child.type == "class_declaration"
            ),
            file_class_static_methods=file_class_static_methods,
            file_class_static_instance_aliases=file_class_static_instance_aliases,
            file_class_declarations=file_class_declarations,
            module_class_static_methods=module_class_static_methods,
            module_class_static_instance_aliases=module_class_static_instance_aliases,
            module_class_declarations=module_class_declarations,
            enclosing_static_dispatch=enclosing_static_dispatch,
            interface_type_var_maps=interface_type_var_maps,
        )
        pending_docstring = None
        lines.extend(f"    {line}" if line else line for line in child_lines)
    return lines

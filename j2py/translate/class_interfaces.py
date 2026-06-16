"""Interface (Protocol) declaration emission for class translation."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import (
    annotation_comment_lines,
    record_annotation_diagnostics,
)
from j2py.translate.class_members import (
    member_method_names,
    member_python_name,
    member_static_method_names,
    sealed_type_alias_lines,
    type_metadata_comment_lines,
)
from j2py.translate.class_methods import (
    class_method_return_types,
    method_body,
    parameter_infos,
    return_type,
    signature,
    translate_method,
)
from j2py.translate.class_model import _modifiers
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.framework_annotations import (
    class_annotation_mapping,
    method_annotation_decorator_lines,
)
from j2py.translate.name_resolution import NameResolver
from j2py.translate.rules.naming import translate_class_name


def translate_interface(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    docstring_lines: list[str] | None = None,
) -> list[str]:
    from j2py.translate.class_nested import nested_type_lines

    diagnostics.record(node, supported=True, reason="translated interface declaration")
    diagnostics.imports.need_typing("Protocol")
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    body = node.child_by_field("body")
    methods = (
        []
        if body is None
        else [child for child in body.named_children if child.type == "method_declaration"]
    )
    class_method_names = member_method_names(methods, cfg)
    class_static_method_names = member_static_method_names(methods, cfg)
    method_return_types = class_method_return_types(methods, cfg)
    nested_lines = nested_type_lines(
        body,
        cfg,
        diagnostics,
        inherited_class_field_types={},
        inherited_class_field_java_types={},
        inherited_declared_type_fields={},
        inherited_declared_type_java_fields={},
        inherited_declared_type_method_return_types={},
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
        name_resolver=name_resolver,
    )
    sealed_alias_lines = sealed_type_alias_lines(node, body, class_name, indent="    ")

    record_annotation_diagnostics(
        node,
        cfg,
        diagnostics,
        target_kind="class",
        target_name=class_name,
    )
    class_mapping = class_annotation_mapping(node, cfg, diagnostics)
    lines: list[str] = []
    lines.extend(annotation_comment_lines(node, cfg))
    lines.extend(class_mapping.decorators)
    bases = [*class_mapping.bases, "Protocol"]
    lines.append(f"class {class_name}({', '.join(bases)}):")
    if docstring_lines:
        lines.extend(docstring_lines)
    metadata_lines = type_metadata_comment_lines(node, indent="    ")
    lines.extend(metadata_lines)
    wrote_member = bool(docstring_lines or metadata_lines)
    if nested_lines:
        if wrote_member:
            lines.append("")
        lines.extend(nested_lines)
        wrote_member = True
    if sealed_alias_lines:
        if wrote_member:
            lines.append("")
        lines.extend(sealed_alias_lines)
        wrote_member = True
    for method in methods:
        if wrote_member:
            lines.append("")
        method_body_node = method_body(method)
        if method_body_node is not None:
            reason = (
                "translated interface static method"
                if "static" in _modifiers(method)
                else "translated interface default method"
            )
            diagnostics.record(method, supported=True, reason=reason)
            ctx = TranslationContext(
                cfg=cfg,
                diagnostics=diagnostics,
                class_fields=set(),
                class_field_types={},
                class_field_java_types={},
                class_methods=class_method_names,
                class_static_methods=class_static_method_names,
                class_method_return_types=method_return_types,
                static_field_aliases=static_field_aliases,
                static_method_imports=static_method_imports,
                name_resolver=name_resolver,
                containing_class_name=class_name,
                allow_local_helpers=True,
            )
            lines.extend(translate_method(method, ctx, supported_reason=reason))
            wrote_member = True
            continue

        diagnostics.record(method, supported=True, reason="translated abstract interface method")
        py_name = member_python_name(method)
        record_annotation_diagnostics(
            method,
            cfg,
            diagnostics,
            target_kind="method",
            target_name=py_name,
        )
        lines.extend(annotation_comment_lines(method, cfg, indent="    "))
        lines.extend(method_annotation_decorator_lines(method, cfg, diagnostics, indent="    "))
        params = parameter_infos(method, cfg)
        method_return_type = return_type(method, cfg)
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(method_return_type)
            for param in params:
                diagnostics.imports.need_type_annotation(param.py_type)
        method_signature = signature(
            member_python_name(method),
            params,
            return_type=method_return_type,
            include_self="static" not in _modifiers(method),
            emit_type_hints=cfg.emit_type_hints,
        )
        lines.append(f"    {method_signature}: ...")
        wrote_member = True

    if not wrote_member:
        lines.append("    pass")
    return lines

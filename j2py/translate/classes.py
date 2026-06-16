"""Class declaration facade for the rule-based skeleton translator."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import (
    annotation_comment_lines,
    record_annotation_diagnostics,
)
from j2py.translate.class_fields import (
    _class_field_java_types,
    _class_field_types,
    _class_fields,
    _collect_declared_type_fields,
    _collect_declared_type_java_fields,
    _constructor_assigned_fields,
    _instance_field_names,
    _translate_fields,
    field_infos_from_declaration,
)
from j2py.translate.class_members import (
    base_suffix,
    collect_file_class_static_methods,
    direct_nested_type_names,
    docstring_for_group,
    enclosing_static_dispatch_for_nested_types,
    inherited_static_dispatch,
    member_docstrings,
    member_groups,
    member_method_names,
    member_static_method_names,
    nested_type_names_using_qualified_this,
    node_key,
    type_metadata_comment_lines,
)
from j2py.translate.class_methods import (
    class_method_return_types,
    parameter_infos,
    translate_method,
)
from j2py.translate.class_model import (
    TYPE_DECLARATION_NODES,
    FieldInfo,
    ParameterInfo,
    _modifiers,
)
from j2py.translate.diagnostics import (
    ClassTranslationState,
    TranslationContext,
    TranslationDiagnostics,
)
from j2py.translate.name_resolution import NameResolver, NameScope
from j2py.translate.node_utils import class_body_needs_pass
from j2py.translate.rules.naming import translate_class_name
from j2py.translate.statements import (
    class_uses_synchronized_this,
    instance_lock_init_line,
)

__all__ = [
    "FieldInfo",
    "ParameterInfo",
    "collect_file_class_static_methods",
    "field_infos_from_declaration",
    "top_level_classes",
    "translate_class",
    "translate_overloaded_members",
]


def top_level_classes(root: JavaNode) -> list[JavaNode]:
    return [child for child in root.named_children if child.type in TYPE_DECLARATION_NODES]


def translate_class(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    inherited_class_field_types: dict[str, str] | None = None,
    inherited_class_field_java_types: dict[str, str] | None = None,
    inherited_declared_type_fields: dict[str, dict[str, str]] | None = None,
    inherited_declared_type_java_fields: dict[str, dict[str, str]] | None = None,
    static_field_aliases: dict[str, str] | None = None,
    static_method_imports: dict[str, str] | None = None,
    name_resolver: NameResolver | None = None,
    docstring_lines: list[str] | None = None,
    outer_self_alias: str | None = None,
    requires_outer_self: bool = False,
    file_class_static_methods: dict[str, set[str]] | None = None,
    enclosing_static_dispatch: dict[str, str] | None = None,
) -> list[str]:
    resolver = name_resolver or NameResolver.empty()
    if node.type == "interface_declaration":
        from j2py.translate.class_interfaces import translate_interface

        return translate_interface(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            name_resolver=resolver,
            docstring_lines=docstring_lines,
        )
    if node.type == "enum_declaration":
        from j2py.translate.class_enums import translate_enum

        return translate_enum(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            name_resolver=resolver,
        )
    if node.type == "record_declaration":
        return _translate_record(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            docstring_lines=docstring_lines,
        )
    if node.type == "annotation_type_declaration":
        from j2py.translate.class_annotations import translate_annotation_declaration

        return translate_annotation_declaration(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            name_resolver=resolver,
            docstring_lines=docstring_lines,
        )

    is_supported_class = node.type == "class_declaration"
    diagnostics.record(
        node,
        supported=is_supported_class,
        reason=(
            "translated class declaration"
            if is_supported_class
            else f"unsupported top-level declaration {node.type}"
        ),
    )

    name_node = node.child_by_field("name")
    if name_node is None:
        diagnostics.record(node, supported=False, reason="class declaration without a name")
        return ["class Unknown:", "    # TODO(j2py): class declaration without a name", "    pass"]

    class_name = translate_class_name(name_node.text)
    if not is_supported_class:
        return [
            f"class {class_name}:",
            f"    # TODO(j2py): unsupported top-level declaration {node.type}",
            "    pass",
        ]

    fields = _class_fields(node, cfg)
    instance_field_names = _instance_field_names(fields)
    class_field_types = {
        **(inherited_class_field_types or {}),
        **_class_field_types(fields),
    }
    class_field_java_types = {
        **(inherited_class_field_java_types or {}),
        **_class_field_java_types(fields),
    }
    declared_type_fields = {
        **(inherited_declared_type_fields or {}),
        **_collect_declared_type_fields(node, cfg),
    }
    declared_type_java_fields = {
        **(inherited_declared_type_java_fields or {}),
        **_collect_declared_type_java_fields(node, cfg),
    }
    assigned_fields = _constructor_assigned_fields(node)
    body = node.child_by_field("body")
    members = (
        []
        if body is None
        else [
            child
            for child in body.named_children
            if child.type in {"constructor_declaration", "method_declaration"}
        ]
    )
    class_method_names = member_method_names(members, cfg)
    class_static_method_names = member_static_method_names(members, cfg)
    method_return_types = class_method_return_types(members, cfg)
    enclosing_dispatch = dict(enclosing_static_dispatch or {})
    enclosing_dispatch.update(inherited_static_dispatch(node, file_class_static_methods or {}, cfg))
    nested_enclosing_dispatch = enclosing_static_dispatch_for_nested_types(
        class_name=class_name,
        class_static_methods=class_static_method_names,
        enclosing_static_dispatch=enclosing_dispatch,
    )
    class_state = ClassTranslationState(needs_instance_lock=class_uses_synchronized_this(node))
    if class_state.needs_instance_lock:
        diagnostics.imports.need_threading()
    modifiers = _modifiers(node)
    if "abstract" in modifiers:
        diagnostics.imports.need_abc()
    lock_init_lines = [instance_lock_init_line()] if class_state.needs_instance_lock else []

    metadata_lines = type_metadata_comment_lines(node, indent="    ")
    direct_nested_names = set() if body is None else direct_nested_type_names(body)
    base_scope = NameScope(
        containing_class_name=class_name,
        nested_class_names=direct_nested_names,
        snake_case_fields=cfg.snake_case_fields,
    )
    record_annotation_diagnostics(
        node,
        cfg,
        diagnostics,
        target_kind="class",
        target_name=class_name,
    )
    lines: list[str] = []
    lines.extend(annotation_comment_lines(node, cfg))
    lines.append(
        f"class {class_name}{base_suffix(node, diagnostics, resolver=resolver, scope=base_scope)}:",
    )
    if docstring_lines:
        lines.extend(docstring_lines)
    lines.extend(metadata_lines)
    static_field_lines, instance_init_lines = _translate_fields(
        node,
        fields,
        assigned_fields,
        instance_field_names,
        cfg,
        diagnostics,
        declared_type_fields=declared_type_fields,
        declared_type_java_fields=declared_type_java_fields,
        class_static_methods=class_static_method_names,
        containing_class_name=class_name,
        enclosing_static_dispatch=enclosing_dispatch,
        name_resolver=resolver,
    )
    nested_outer_capture_names = nested_type_names_using_qualified_this(body)
    from j2py.translate.class_nested import nested_type_lines

    nested_lines = nested_type_lines(
        body,
        cfg,
        diagnostics,
        inherited_class_field_types=class_field_types,
        inherited_class_field_java_types=class_field_java_types,
        inherited_declared_type_fields=declared_type_fields,
        inherited_declared_type_java_fields=declared_type_java_fields,
        static_field_aliases=static_field_aliases or {},
        static_method_imports=static_method_imports or {},
        name_resolver=resolver,
        outer_capture_names=nested_outer_capture_names,
        file_class_static_methods=file_class_static_methods,
        enclosing_static_dispatch=nested_enclosing_dispatch,
    )
    has_constructor = any(member.type == "constructor_declaration" for member in members)
    needs_synthetic_init = (
        bool(instance_init_lines) or class_state.needs_instance_lock or requires_outer_self
    ) and not has_constructor

    if (
        not members
        and not static_field_lines
        and not instance_init_lines
        and not nested_lines
        and not needs_synthetic_init
    ):
        if class_body_needs_pass(lines):
            lines.append("    pass")
        return lines

    if static_field_lines:
        if docstring_lines or metadata_lines:
            lines.append("")
        lines.extend(static_field_lines)

    if needs_synthetic_init:
        if static_field_lines or docstring_lines or metadata_lines:
            lines.append("")
        init_params = "self, _outer_self: object" if requires_outer_self else "self"
        lines.append(f"    def __init__({init_params}) -> None:")
        if requires_outer_self:
            lines.append("        self._outer_self = _outer_self")
        lines.extend(lock_init_lines)
        lines.extend(instance_init_lines)

    if nested_lines:
        if static_field_lines or needs_synthetic_init or docstring_lines or metadata_lines:
            lines.append("")
        lines.extend(nested_lines)

    member_docstring_map = member_docstrings(body, cfg)
    for group in member_groups(members):
        lines.append("")
        if len(group) > 1:
            lines.extend(
                translate_overloaded_members(
                    group,
                    cfg=cfg,
                    diagnostics=diagnostics,
                    containing_class_name=class_name,
                    class_fields=instance_field_names,
                    class_field_types=class_field_types,
                    class_field_java_types=class_field_java_types,
                    declared_type_fields=declared_type_fields,
                    declared_type_java_fields=declared_type_java_fields,
                    class_methods=class_method_names,
                    class_static_methods=class_static_method_names,
                    class_method_return_types=method_return_types,
                    static_field_aliases=static_field_aliases or {},
                    static_method_imports=static_method_imports or {},
                    name_resolver=resolver,
                    pre_body_lines=(
                        lock_init_lines + instance_init_lines
                        if group[0].type == "constructor_declaration"
                        else []
                    ),
                    class_state=class_state,
                    docstring_lines=docstring_for_group(group, member_docstring_map),
                    inner_class_names_requiring_outer=nested_outer_capture_names,
                    nested_class_names=direct_nested_names,
                    enclosing_static_dispatch=enclosing_dispatch,
                ),
            )
            continue

        member = group[0]
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
            class_field_types=class_field_types,
            class_field_java_types=class_field_java_types,
            declared_type_fields=declared_type_fields,
            declared_type_java_fields=declared_type_java_fields,
            class_methods=class_method_names,
            class_static_methods=class_static_method_names,
            class_method_return_types=method_return_types,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            name_resolver=resolver,
            allow_local_helpers=True,
            class_state=class_state,
            outer_self_alias=outer_self_alias,
            inner_class_names_requiring_outer=nested_outer_capture_names,
            containing_class_name=class_name,
            nested_class_names=direct_nested_names,
            enclosing_static_dispatch=enclosing_dispatch,
        )
        pre_body_lines = (
            lock_init_lines + instance_init_lines
            if member.type == "constructor_declaration"
            else []
        )
        lines.extend(
            translate_method(
                member,
                ctx,
                pre_body_lines=pre_body_lines,
                docstring_lines=member_docstring_map.get(node_key(member)),
            )
        )

    if class_body_needs_pass(lines):
        lines.append("    pass")

    return lines


def _translate_record(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    docstring_lines: list[str] | None = None,
) -> list[str]:
    del static_field_aliases, static_method_imports
    diagnostics.record(node, supported=True, reason="translated record declaration")
    diagnostics.imports.need_dataclass()
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    params = parameter_infos(node, cfg)
    for param in params:
        diagnostics.imports.need_type_annotation(param.py_type)

    record_annotation_diagnostics(
        node,
        cfg,
        diagnostics,
        target_kind="class",
        target_name=class_name,
    )
    lines: list[str] = []
    lines.extend(annotation_comment_lines(node, cfg))
    lines.extend(["@dataclass(frozen=True)", f"class {class_name}:"])
    if docstring_lines:
        lines.extend(docstring_lines)
    metadata_lines = type_metadata_comment_lines(node, indent="    ")
    lines.extend(metadata_lines)
    if not params:
        if not docstring_lines and not metadata_lines:
            lines.append("    pass")
        return lines
    for param in params:
        lines.append(f"    {param.py_name}: {param.py_type}")
    return lines


def translate_overloaded_members(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    containing_class_name: str,
    class_fields: set[str],
    class_field_types: dict[str, str] | None = None,
    class_field_java_types: dict[str, str] | None = None,
    declared_type_fields: dict[str, dict[str, str]] | None = None,
    declared_type_java_fields: dict[str, dict[str, str]] | None = None,
    class_methods: set[str] | None = None,
    class_static_methods: set[str] | None = None,
    enclosing_static_dispatch: dict[str, str] | None = None,
    class_method_return_types: dict[str, str] | None = None,
    static_field_aliases: dict[str, str] | None = None,
    static_method_imports: dict[str, str] | None = None,
    name_resolver: NameResolver | None = None,
    pre_body_lines: list[str],
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
) -> list[str]:
    from j2py.translate.overloads import translate_overloaded_members as impl

    return impl(
        members,
        cfg=cfg,
        diagnostics=diagnostics,
        containing_class_name=containing_class_name,
        class_fields=class_fields,
        class_field_types=class_field_types,
        class_field_java_types=class_field_java_types,
        declared_type_fields=declared_type_fields,
        declared_type_java_fields=declared_type_java_fields,
        class_methods=class_methods,
        class_static_methods=class_static_methods,
        enclosing_static_dispatch=enclosing_static_dispatch,
        class_method_return_types=class_method_return_types,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
        name_resolver=name_resolver,
        pre_body_lines=pre_body_lines,
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
        nested_class_names=nested_class_names or set(),
    )

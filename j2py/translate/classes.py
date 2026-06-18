"""Class declaration facade for the rule-based skeleton translator."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.framework import FrameworkTransformResult
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import (
    annotation_comment_lines,
    record_annotation_diagnostics,
)
from j2py.translate.class_environment import ClassTranslationEnvironment
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
    inherited_static_instance_static_aliases,
    inherited_static_instance_zero_arg_names,
    member_docstrings,
    member_groups,
    member_method_names,
    member_static_method_names,
    merge_class_declaration_indexes,
    merge_class_static_instance_alias_indexes,
    merge_class_static_method_indexes,
    nested_type_names_using_qualified_this,
    node_key,
    static_instance_collision_static_aliases,
    static_instance_collision_zero_arg_names,
    type_metadata_comment_lines,
)
from j2py.translate.class_methods import (
    class_method_return_types,
    collect_declared_type_method_return_types,
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
from j2py.translate.framework_dispatch import resolve_class, resolve_field
from j2py.translate.member_resolution import JavaMemberBinding
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
    env: ClassTranslationEnvironment | None = None,
    **legacy_env_kwargs: object,
) -> list[str]:
    env = _translation_env(env, legacy_env_kwargs)
    resolver = env.name_resolver
    if node.type == "interface_declaration":
        from j2py.translate.class_interfaces import translate_interface

        return translate_interface(node, cfg, diagnostics, env=env)
    if node.type == "enum_declaration":
        from j2py.translate.class_enums import translate_enum

        return translate_enum(node, cfg, diagnostics, env=env)
    if node.type == "record_declaration":
        return _translate_record(node, cfg, diagnostics, env=env)
    if node.type == "annotation_type_declaration":
        from j2py.translate.class_annotations import translate_annotation_declaration

        return translate_annotation_declaration(node, cfg, diagnostics, env=env)

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
        **env.inherited_class_field_types,
        **_class_field_types(fields),
    }
    class_field_java_types = {
        **env.inherited_class_field_java_types,
        **_class_field_java_types(fields),
    }
    declared_type_fields = {
        **env.inherited_declared_type_fields,
        **_collect_declared_type_fields(node, cfg),
    }
    declared_type_java_fields = {
        **env.inherited_declared_type_java_fields,
        **_collect_declared_type_java_fields(node, cfg),
    }
    declared_type_method_return_types = {
        **env.inherited_declared_type_method_return_types,
        **collect_declared_type_method_return_types(node, cfg),
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
    merged_static_methods = merge_class_static_method_indexes(
        env.module_class_static_methods,
        env.file_class_static_methods,
    )
    merged_static_instance_aliases = merge_class_static_instance_alias_indexes(
        env.module_class_static_instance_aliases,
        env.file_class_static_instance_aliases,
    )
    merged_class_declarations = merge_class_declaration_indexes(
        env.module_class_declarations,
        env.file_class_declarations,
    )
    own_collision_aliases = static_instance_collision_static_aliases(members, cfg)
    inherited_collision_aliases = inherited_static_instance_static_aliases(
        node,
        merged_static_instance_aliases,
        merged_class_declarations,
        cfg,
    )
    static_instance_aliases = {**inherited_collision_aliases, **own_collision_aliases}
    own_instance_zero, own_static_zero = static_instance_collision_zero_arg_names(members, cfg)
    inherited_instance_zero, inherited_static_zero = inherited_static_instance_zero_arg_names(
        node,
        merged_class_declarations,
        cfg,
    )
    static_instance_instance_zero_arg = set(own_instance_zero) | set(inherited_instance_zero)
    static_instance_static_zero_arg = set(own_static_zero) | set(inherited_static_zero)
    method_return_types = class_method_return_types(members, cfg)
    enclosing_dispatch = dict(env.enclosing_static_dispatch)
    enclosing_dispatch.update(
        inherited_static_dispatch(
            node,
            merged_static_methods,
            merged_static_instance_aliases,
            merged_class_declarations,
            cfg,
        ),
    )
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
    class_transform = resolve_class(
        node,
        cfg,
        diagnostics,
        java_name=name_node.text,
        py_name=class_name,
    )
    if not class_transform.handled:
        record_annotation_diagnostics(
            node,
            cfg,
            diagnostics,
            target_kind="class",
            target_name=class_name,
        )
    field_transforms = [
        resolve_field(field, cfg, diagnostics, indent="    " if field.is_static else "        ")
        for field in fields
    ]
    injected_init_params = _annotation_init_params(fields, field_transforms)
    lines: list[str] = []
    if not class_transform.handled:
        lines.extend(annotation_comment_lines(node, cfg))
    lines.extend(class_transform.prefix_lines)
    class_bases = base_suffix(
        node,
        diagnostics,
        resolver=resolver,
        scope=base_scope,
        extra_bases=list(class_transform.base_classes),
    )
    lines.append(f"class {class_name}{class_bases}:")
    if env.docstring_lines:
        lines.extend(env.docstring_lines)
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
        field_transforms=field_transforms,
    )
    nested_outer_capture_names = nested_type_names_using_qualified_this(body)
    from j2py.translate.class_nested import nested_type_lines

    nested_env = env.with_overrides(
        inherited_class_field_types=class_field_types,
        inherited_class_field_java_types=class_field_java_types,
        inherited_declared_type_fields=declared_type_fields,
        inherited_declared_type_java_fields=declared_type_java_fields,
        inherited_declared_type_method_return_types=declared_type_method_return_types,
        enclosing_static_dispatch=nested_enclosing_dispatch,
        docstring_lines=None,
        outer_self_alias=None,
        requires_outer_self=False,
    )
    nested_lines = nested_type_lines(
        body,
        cfg,
        diagnostics,
        env=nested_env,
        outer_capture_names=nested_outer_capture_names,
    )
    has_constructor = any(member.type == "constructor_declaration" for member in members)
    needs_synthetic_init = (
        bool(instance_init_lines) or class_state.needs_instance_lock or env.requires_outer_self
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
        if env.docstring_lines or metadata_lines:
            lines.append("")
        lines.extend(static_field_lines)

    if needs_synthetic_init:
        if static_field_lines or env.docstring_lines or metadata_lines:
            lines.append("")
        init_params = ["self"]
        if env.requires_outer_self:
            init_params.append("_outer_self: object" if cfg.emit_type_hints else "_outer_self")
        init_params.extend(_render_init_params(injected_init_params, cfg, diagnostics))
        lines.append(f"    def __init__({', '.join(init_params)}) -> None:")
        if env.requires_outer_self:
            lines.append("        self._outer_self = _outer_self")
        lines.extend(lock_init_lines)
        lines.extend(instance_init_lines)

    if nested_lines:
        if static_field_lines or needs_synthetic_init or env.docstring_lines or metadata_lines:
            lines.append("")
        lines.extend(nested_lines)

    member_docstring_map = member_docstrings(body, cfg)
    outer_self_params = _outer_self_init_params() if env.requires_outer_self else []
    outer_self_init_lines = _outer_self_init_lines() if env.requires_outer_self else []
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
                    declared_type_method_return_types=declared_type_method_return_types,
                    class_methods=class_method_names,
                    class_static_methods=class_static_method_names,
                    class_method_return_types=method_return_types,
                    static_field_aliases=env.static_field_aliases,
                    static_method_imports=env.static_method_imports,
                    static_member_bindings=env.static_member_bindings,
                    name_resolver=resolver,
                    pre_body_lines=(
                        outer_self_init_lines + lock_init_lines + instance_init_lines
                        if group[0].type == "constructor_declaration"
                        else []
                    ),
                    extra_params=(
                        outer_self_params + injected_init_params
                        if group[0].type == "constructor_declaration"
                        else []
                    ),
                    class_state=class_state,
                    docstring_lines=docstring_for_group(group, member_docstring_map),
                    inner_class_names_requiring_outer=nested_outer_capture_names,
                    nested_class_names=direct_nested_names,
                    enclosing_static_dispatch=enclosing_dispatch,
                    static_instance_static_aliases=static_instance_aliases,
                    static_instance_instance_zero_arg_names=static_instance_instance_zero_arg,
                    static_instance_static_zero_arg_names=static_instance_static_zero_arg,
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
            declared_type_method_return_types=declared_type_method_return_types,
            class_methods=class_method_names,
            class_static_methods=class_static_method_names,
            class_method_return_types=method_return_types,
            static_field_aliases=env.static_field_aliases,
            static_method_imports=env.static_method_imports,
            static_member_bindings=env.static_member_bindings,
            name_resolver=resolver,
            allow_local_helpers=True,
            class_state=class_state,
            outer_self_alias=env.outer_self_alias,
            inner_class_names_requiring_outer=nested_outer_capture_names,
            containing_class_name=class_name,
            nested_class_names=direct_nested_names,
            enclosing_static_dispatch=enclosing_dispatch,
            static_instance_static_aliases=static_instance_aliases,
            static_instance_instance_zero_arg_names=static_instance_instance_zero_arg,
            static_instance_static_zero_arg_names=static_instance_static_zero_arg,
        )
        pre_body_lines = (
            outer_self_init_lines + lock_init_lines + instance_init_lines
            if member.type == "constructor_declaration"
            else []
        )
        lines.extend(
            translate_method(
                member,
                ctx,
                pre_body_lines=pre_body_lines,
                extra_params=(
                    outer_self_params + injected_init_params
                    if member.type == "constructor_declaration"
                    else []
                ),
                docstring_lines=member_docstring_map.get(node_key(member)),
            )
        )

    if class_body_needs_pass(lines):
        lines.append("    pass")

    return lines


_LEGACY_ENV_KEYS = frozenset(
    {
        "inherited_class_field_types",
        "inherited_class_field_java_types",
        "inherited_declared_type_fields",
        "inherited_declared_type_java_fields",
        "inherited_declared_type_method_return_types",
        "static_field_aliases",
        "static_method_imports",
        "name_resolver",
        "docstring_lines",
        "outer_self_alias",
        "requires_outer_self",
        "file_class_static_methods",
        "file_class_static_instance_aliases",
        "file_class_declarations",
        "module_class_static_methods",
        "module_class_static_instance_aliases",
        "module_class_declarations",
        "enclosing_static_dispatch",
        "interface_type_var_maps",
    },
)


def _translation_env(
    env: ClassTranslationEnvironment | None,
    legacy_env_kwargs: dict[str, object],
) -> ClassTranslationEnvironment:
    base = env or ClassTranslationEnvironment()
    if not legacy_env_kwargs:
        return base
    unknown_keys = sorted(set(legacy_env_kwargs) - _LEGACY_ENV_KEYS)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise TypeError(f"translate_class() got unexpected keyword argument(s): {joined}")
    overrides = {key: value for key, value in legacy_env_kwargs.items() if value is not None}
    if not overrides:
        return base
    return base.with_overrides(**overrides)


def _translate_record(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    env: ClassTranslationEnvironment,
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated record declaration")
    diagnostics.imports.need_dataclass()
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    params = parameter_infos(node, cfg)
    for param in params:
        diagnostics.imports.need_type_annotation(param.py_type)

    java_name = name_node.text if name_node is not None else "Unknown"
    class_transform = resolve_class(
        node,
        cfg,
        diagnostics,
        java_name=java_name,
        py_name=class_name,
    )
    if not class_transform.handled:
        record_annotation_diagnostics(
            node,
            cfg,
            diagnostics,
            target_kind="class",
            target_name=class_name,
        )
    lines: list[str] = []
    if not class_transform.handled:
        lines.extend(annotation_comment_lines(node, cfg))
    lines.extend(class_transform.prefix_lines)
    base_text = (
        f"({', '.join(class_transform.base_classes)})" if class_transform.base_classes else ""
    )
    lines.extend(["@dataclass(frozen=True)", f"class {class_name}{base_text}:"])
    if env.docstring_lines:
        lines.extend(env.docstring_lines)
    metadata_lines = type_metadata_comment_lines(node, indent="    ")
    lines.extend(metadata_lines)
    if not params:
        if not env.docstring_lines and not metadata_lines:
            lines.append("    pass")
        return lines
    for param in params:
        lines.append(f"    {param.py_name}: {param.py_type}")
    return lines


def _annotation_init_params(
    fields: list[FieldInfo],
    field_transforms: list[FrameworkTransformResult],
) -> list[ParameterInfo]:
    params: list[ParameterInfo] = []
    seen: set[str] = set()
    for field, transform in zip(fields, field_transforms, strict=True):
        for init_param in transform.init_params:
            if init_param.py_name in seen:
                continue
            params.append(
                ParameterInfo(
                    raw_name=field.name,
                    py_name=init_param.py_name,
                    py_type=init_param.py_type,
                    java_type=field.java_type,
                ),
            )
            seen.add(init_param.py_name)
    return params


def _outer_self_init_params() -> list[ParameterInfo]:
    return [
        ParameterInfo(
            raw_name="_outer_self",
            py_name="_outer_self",
            py_type="object",
            java_type="Object",
        ),
    ]


def _outer_self_init_lines() -> list[str]:
    return ["        self._outer_self = _outer_self"]


def _render_init_params(
    params: list[ParameterInfo],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    rendered: list[str] = []
    for param in params:
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(param.py_type)
            rendered.append(f"{param.py_name}: {param.py_type}")
        else:
            rendered.append(param.py_name)
    return rendered


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
    declared_type_method_return_types: dict[str, dict[str, str]] | None = None,
    class_methods: set[str] | None = None,
    class_static_methods: set[str] | None = None,
    enclosing_static_dispatch: dict[str, str] | None = None,
    class_method_return_types: dict[str, str] | None = None,
    static_field_aliases: dict[str, str] | None = None,
    static_method_imports: dict[str, str] | None = None,
    static_member_bindings: dict[str, JavaMemberBinding] | None = None,
    name_resolver: NameResolver | None = None,
    pre_body_lines: list[str],
    extra_params: list[ParameterInfo] | None = None,
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
    static_instance_static_aliases: dict[str, str] | None = None,
    static_instance_instance_zero_arg_names: set[str] | None = None,
    static_instance_static_zero_arg_names: set[str] | None = None,
    python_name_override: str | None = None,
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
        static_member_bindings=static_member_bindings,
        name_resolver=name_resolver,
        pre_body_lines=pre_body_lines,
        extra_params=extra_params or [],
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
        nested_class_names=nested_class_names or set(),
        static_instance_static_aliases=static_instance_static_aliases,
        static_instance_instance_zero_arg_names=static_instance_instance_zero_arg_names,
        static_instance_static_zero_arg_names=static_instance_static_zero_arg_names,
        python_name_override=python_name_override,
    )

"""Overload translation helpers for class emission."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import record_annotation_diagnostics
from j2py.translate.class_members import (
    member_python_name,
    static_instance_collision_static_python_name,
    static_instance_collision_zero_arg_names,
)
from j2py.translate.class_methods import translate_method
from j2py.translate.class_model import ParameterInfo, _modifiers
from j2py.translate.diagnostics import (
    ClassTranslationState,
    TranslationContext,
    TranslationDiagnostics,
)
from j2py.translate.name_resolution import NameResolver
from j2py.translate.overload_classification import OverloadKind, classify_overload_group
from j2py.translate.overload_dispatch import (
    _dispatch_overload_members,
    _value_dispatch_overload,
)
from j2py.translate.overload_equivalence import _deduplicate_same_body_erased_sig
from j2py.translate.overload_merge import (
    _merged_constructor_overload,
    _merged_forwarding_method_overload,
    _merged_method_overload,
)
from j2py.translate.overload_signatures import (
    _overload_stubs,
    _readable_signature,
    _static_instance_overload_stubs,
)

__all__ = ["translate_overloaded_members"]


def _emit_static_instance_collision_split(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    containing_class_name: str,
    class_fields: set[str],
    class_field_types: dict[str, str],
    class_field_java_types: dict[str, str],
    declared_type_fields: dict[str, dict[str, str]],
    declared_type_java_fields: dict[str, dict[str, str]],
    class_methods: set[str],
    class_static_methods: set[str],
    enclosing_static_dispatch: dict[str, str],
    class_method_return_types: dict[str, str],
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    class_state: ClassTranslationState | None,
    docstring_lines: list[str] | None,
    inner_class_names_requiring_outer: set[str],
    nested_class_names: set[str],
    static_instance_static_aliases: dict[str, str],
    static_instance_instance_zero_arg_names: set[str] | None = None,
    static_instance_static_zero_arg_names: set[str] | None = None,
) -> list[str]:
    """Emit static and instance overload members under distinct Python names."""
    static_members = [member for member in members if "static" in _modifiers(member)]
    instance_members = [member for member in members if "static" not in _modifiers(member)]
    if not static_members or not instance_members:
        return []

    canonical_name = member_python_name(members[0])
    static_name = static_instance_collision_static_python_name(canonical_name)

    lines = [
        "    # static/instance overload split: static members use "
        f"{static_name!r} to preserve both Java overload bodies",
    ]
    if len(static_members) == 1 and len(instance_members) == 1:
        lines.extend(
            _static_instance_overload_stubs(
                members,
                canonical_name=canonical_name,
                static_name=static_name,
                cfg=cfg,
                diagnostics=diagnostics,
            ),
        )

    own_instance_zero, own_static_zero = static_instance_collision_zero_arg_names(members, cfg)
    instance_zero_arg = set(static_instance_instance_zero_arg_names or ()) | set(own_instance_zero)
    static_zero_arg = set(static_instance_static_zero_arg_names or ()) | set(own_static_zero)

    def translation_context() -> TranslationContext:
        return TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=class_fields,
            class_field_types=dict(class_field_types),
            class_field_java_types=dict(class_field_java_types),
            declared_type_fields=dict(declared_type_fields),
            declared_type_java_fields=dict(declared_type_java_fields),
            class_methods=class_methods,
            class_static_methods=class_static_methods,
            enclosing_static_dispatch=dict(enclosing_static_dispatch),
            class_method_return_types=dict(class_method_return_types),
            static_field_aliases=dict(static_field_aliases),
            static_method_imports=dict(static_method_imports),
            name_resolver=name_resolver,
            allow_local_helpers=True,
            class_state=class_state,
            inner_class_names_requiring_outer=inner_class_names_requiring_outer,
            containing_class_name=containing_class_name,
            nested_class_names=nested_class_names,
            static_instance_static_aliases=dict(static_instance_static_aliases),
            static_instance_instance_zero_arg_names=instance_zero_arg,
            static_instance_static_zero_arg_names=static_zero_arg,
        )

    emitted_static = False
    emitted_instance = False
    for member in members:
        is_static = "static" in _modifiers(member)
        if is_static and emitted_static:
            continue
        if not is_static and emitted_instance:
            continue

        member_docstring = docstring_lines if member is members[0] else None
        if is_static:
            if len(static_members) == 1:
                lines.extend(
                    translate_method(
                        static_members[0],
                        translation_context(),
                        python_name_override=static_name,
                        supported_reason="translated static/instance overload split",
                        docstring_lines=member_docstring,
                    ),
                )
            else:
                lines.extend(
                    translate_overloaded_members(
                        static_members,
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
                        pre_body_lines=[],
                        class_state=class_state,
                        docstring_lines=member_docstring,
                        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
                        nested_class_names=nested_class_names,
                        static_instance_static_aliases=static_instance_static_aliases,
                        static_instance_instance_zero_arg_names=instance_zero_arg,
                        static_instance_static_zero_arg_names=static_zero_arg,
                        python_name_override=static_name,
                    ),
                )
            emitted_static = True
        else:
            if len(instance_members) == 1:
                lines.extend(
                    translate_method(
                        instance_members[0],
                        translation_context(),
                        supported_reason="translated static/instance overload split",
                        docstring_lines=member_docstring,
                    ),
                )
            else:
                lines.extend(
                    translate_overloaded_members(
                        instance_members,
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
                        pre_body_lines=[],
                        class_state=class_state,
                        docstring_lines=member_docstring,
                        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
                        nested_class_names=nested_class_names,
                        static_instance_static_aliases=static_instance_static_aliases,
                        static_instance_instance_zero_arg_names=instance_zero_arg,
                        static_instance_static_zero_arg_names=static_zero_arg,
                    ),
                )
            emitted_instance = True

        if not (emitted_static and emitted_instance) and member is not members[-1]:
            lines.append("")

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
    name = python_name_override or member_python_name(members[0])
    for member in members:
        py_name = member_python_name(member)
        target_kind = "constructor" if member.type == "constructor_declaration" else "method"
        record_annotation_diagnostics(
            member,
            cfg,
            diagnostics,
            target_kind=target_kind,
            target_name=py_name,
        )

    field_types = class_field_types or {f: "object" for f in class_fields}
    field_java_types = class_field_java_types or {}
    nested_type_fields = declared_type_fields or {}
    nested_type_java_fields = declared_type_java_fields or {}
    static_fields = static_field_aliases or {}
    static_methods = static_method_imports or {}
    resolver = name_resolver or NameResolver.empty()
    static_class_methods = class_static_methods or set()
    enclosing_dispatch = dict(enclosing_static_dispatch or {})
    inner_capture_names = inner_class_names_requiring_outer or set()
    direct_nested_names = nested_class_names or set()
    method_return_types = dict(class_method_return_types or {})
    injected_params = extra_params or []
    collision_aliases = dict(static_instance_static_aliases or {})
    instance_zero_arg = set(static_instance_instance_zero_arg_names or ())
    static_zero_arg = set(static_instance_static_zero_arg_names or ())

    # Classify first so overload-family rules share one decision table (#394 / #408).
    classification = classify_overload_group(members, cfg)

    if (
        classification.kind is OverloadKind.STATIC_INSTANCE_COLLISION
        and python_name_override is None
    ):
        split = _emit_static_instance_collision_split(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            containing_class_name=containing_class_name,
            class_fields=class_fields,
            class_field_types=field_types,
            class_field_java_types=field_java_types,
            declared_type_fields=nested_type_fields,
            declared_type_java_fields=nested_type_java_fields,
            class_methods=class_methods or set(),
            class_static_methods=static_class_methods,
            enclosing_static_dispatch=enclosing_dispatch,
            class_method_return_types=method_return_types,
            static_field_aliases=static_fields,
            static_method_imports=static_methods,
            name_resolver=resolver,
            class_state=class_state,
            docstring_lines=docstring_lines,
            inner_class_names_requiring_outer=inner_capture_names,
            nested_class_names=direct_nested_names,
            static_instance_static_aliases=collision_aliases,
            static_instance_instance_zero_arg_names=instance_zero_arg,
            static_instance_static_zero_arg_names=static_zero_arg,
        )
        if split:
            return split

    if members[0].type == "constructor_declaration":
        merged_constructor = _merged_constructor_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            containing_class_name=containing_class_name,
            class_fields=class_fields,
            class_field_types=field_types,
            class_field_java_types=field_java_types,
            declared_type_fields=nested_type_fields,
            declared_type_java_fields=nested_type_java_fields,
            class_methods=class_methods or set(),
            class_static_methods=static_class_methods,
            enclosing_static_dispatch=enclosing_dispatch,
            class_method_return_types=method_return_types,
            static_field_aliases=static_fields,
            static_method_imports=static_methods,
            name_resolver=resolver,
            pre_body_lines=pre_body_lines,
            extra_params=injected_params,
            class_state=class_state,
            docstring_lines=docstring_lines,
            inner_class_names_requiring_outer=inner_capture_names,
            nested_class_names=direct_nested_names,
        )
        if merged_constructor is not None:
            return merged_constructor
    else:
        merged_method = _merged_method_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            containing_class_name=containing_class_name,
            class_fields=class_fields,
            class_field_types=field_types,
            class_field_java_types=field_java_types,
            declared_type_fields=nested_type_fields,
            declared_type_java_fields=nested_type_java_fields,
            class_methods=class_methods or set(),
            class_static_methods=static_class_methods,
            enclosing_static_dispatch=enclosing_dispatch,
            class_method_return_types=method_return_types,
            static_field_aliases=static_fields,
            static_method_imports=static_methods,
            name_resolver=resolver,
            class_state=class_state,
            docstring_lines=docstring_lines,
            inner_class_names_requiring_outer=inner_capture_names,
            nested_class_names=direct_nested_names,
        )
        if merged_method is not None:
            return merged_method

        forwarded_method = _merged_forwarding_method_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            containing_class_name=containing_class_name,
            class_fields=class_fields,
            class_field_types=field_types,
            class_field_java_types=field_java_types,
            declared_type_fields=nested_type_fields,
            declared_type_java_fields=nested_type_java_fields,
            class_methods=class_methods or set(),
            class_static_methods=static_class_methods,
            enclosing_static_dispatch=enclosing_dispatch,
            class_method_return_types=method_return_types,
            static_field_aliases=static_fields,
            static_method_imports=static_methods,
            name_resolver=resolver,
            docstring_lines=docstring_lines,
            inner_class_names_requiring_outer=inner_capture_names,
            nested_class_names=direct_nested_names,
        )
        if forwarded_method is not None:
            return forwarded_method

    if classification.kind in {
        OverloadKind.VALUE_DISPATCH_SAFE,
        OverloadKind.VALUE_DISPATCH_VARARGS_SAFE,
    }:
        value_dispatch = _value_dispatch_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            containing_class_name=containing_class_name,
            class_fields=class_fields,
            class_field_types=field_types,
            class_field_java_types=field_java_types,
            declared_type_fields=nested_type_fields,
            declared_type_java_fields=nested_type_java_fields,
            class_methods=class_methods or set(),
            class_static_methods=static_class_methods,
            enclosing_static_dispatch=enclosing_dispatch,
            class_method_return_types=method_return_types,
            static_field_aliases=static_fields,
            static_method_imports=static_methods,
            name_resolver=resolver,
            class_state=class_state,
            docstring_lines=docstring_lines,
            inner_class_names_requiring_outer=inner_capture_names,
            nested_class_names=direct_nested_names,
            python_name_override=python_name_override,
            static_instance_static_aliases=collision_aliases,
        )
        if value_dispatch is not None:
            return value_dispatch

    deduped_members = _deduplicate_same_body_erased_sig(members, cfg)
    dispatch_input = deduped_members if deduped_members is not None else members

    dispatched = _dispatch_overload_members(
        dispatch_input,
        cfg=cfg,
        diagnostics=diagnostics,
        containing_class_name=containing_class_name,
        class_fields=class_fields,
        class_field_types=field_types,
        class_field_java_types=field_java_types,
        declared_type_fields=nested_type_fields,
        declared_type_java_fields=nested_type_java_fields,
        class_methods=class_methods or set(),
        class_static_methods=static_class_methods,
        class_method_return_types=method_return_types,
        static_field_aliases=static_fields,
        static_method_imports=static_methods,
        name_resolver=resolver,
        pre_body_lines=pre_body_lines,
        extra_params=injected_params,
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_capture_names,
        nested_class_names=direct_nested_names,
        enclosing_static_dispatch=enclosing_dispatch,
        python_name_override=python_name_override,
        static_instance_static_aliases=collision_aliases,
    )
    if dispatched is not None:
        if deduped_members is not None:
            # Record dropped duplicates as handled (deduplicated into one representative)
            deduped_ids = {id(m) for m in deduped_members}
            for member in members:
                if id(member) not in deduped_ids:
                    diagnostics.record(
                        member,
                        supported=True,
                        reason="deduplicated same-body erased-signature overload",
                    )
        return dispatched

    for member in members:
        diagnostics.record(
            member,
            supported=False,
            reason=f"overloaded method {name} requires manual dispatch",
        )
    lines = _overload_stubs(members, cfg, diagnostics)
    fallback_return = "None" if members[0].type == "constructor_declaration" else "object"
    is_static = "static" in _modifiers(members[0])
    if is_static:
        lines.append("    @staticmethod")
    fallback_params = "*args: object" if is_static else "self, *args: object"
    lines.append(f"    def {name}({fallback_params}) -> {fallback_return}:")
    if docstring_lines:
        lines.extend(docstring_lines)
        lines.append("")
    signatures = "; ".join(_readable_signature(member, cfg) for member in members)
    lines.append(
        f"        # TODO(j2py): overloaded method {name} requires manual dispatch "
        f"for signatures: {signatures}",
    )
    lines.append('        raise NotImplementedError("j2py overload dispatch required")')
    return lines

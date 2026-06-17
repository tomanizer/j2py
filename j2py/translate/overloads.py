"""Overload translation helpers for class emission."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import record_annotation_diagnostics
from j2py.translate.class_members import member_python_name
from j2py.translate.class_model import ParameterInfo, _modifiers
from j2py.translate.diagnostics import ClassTranslationState, TranslationDiagnostics
from j2py.translate.name_resolution import NameResolver
from j2py.translate.overload_classification import classify_overload_group
from j2py.translate.overload_dispatch import (
    _deduplicate_same_body_erased_sig,
    _dispatch_overload_members,
    _value_dispatch_overload,
)
from j2py.translate.overload_merge import (
    _merged_constructor_overload,
    _merged_forwarding_method_overload,
    _merged_method_overload,
)
from j2py.translate.overload_signatures import _overload_stubs, _readable_signature

__all__ = ["translate_overloaded_members"]


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
) -> list[str]:
    name = member_python_name(members[0])
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

    # Classify first so future overload-family rules have a single decision table.
    # Emission below remains behavior-preserving for this first slice (#394).
    _ = classify_overload_group(members, cfg)

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
    )
    if value_dispatch is not None:
        return value_dispatch

    # When same-erased-signature overloads have identical Java bodies (e.g. sort(int[])
    # and sort(long[]) both do Arrays.sort(array)), deduplicate to one representative so
    # _dispatch_overload_members can proceed with a distinct-signature set.
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

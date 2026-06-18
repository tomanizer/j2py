"""Overload translation helpers for class emission."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import record_annotation_diagnostics
from j2py.translate.class_members import (
    member_python_name,
    raw_member_name,
    static_instance_collision_static_python_name,
    static_instance_collision_zero_arg_names,
)
from j2py.translate.class_methods import parameter_infos, translate_method
from j2py.translate.class_model import ParameterInfo, _modifiers
from j2py.translate.diagnostics import (
    ClassTranslationState,
    TranslationContext,
    TranslationDiagnostics,
)
from j2py.translate.member_resolution import (
    JavaMemberBinding,
    JavaOverloadCallTarget,
    java_type_shape_signature,
)
from j2py.translate.name_resolution import NameResolver
from j2py.translate.overload_classification import (
    OverloadClassification,
    OverloadKind,
    classify_overload_group,
)
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

__all__ = ["overload_call_targets_for_group", "translate_overloaded_members"]


def overload_call_targets_for_group(
    members: list[JavaNode],
    cfg: TranslationConfig,
    *,
    python_name_override: str | None = None,
) -> list[JavaOverloadCallTarget]:
    """Return body-backed helper targets for manual-dispatch overload groups."""
    if not members or members[0].type != "method_declaration":
        return []
    classification = classify_overload_group(members, cfg)
    if classification.kind is not OverloadKind.ERASURE_COLLISION_UNSAFE:
        return []
    name = python_name_override or member_python_name(members[0])
    targets: list[JavaOverloadCallTarget] = []
    for index, member in enumerate(members, 1):
        targets.append(
            JavaOverloadCallTarget(
                member=raw_member_name(member),
                python_member=name,
                java_shape_signature=java_type_shape_signature(
                    [param.java_type for param in parameter_infos(member, cfg)],
                    cfg,
                ),
                is_static="static" in _modifiers(member),
                helper_name=_overload_branch_helper_name(name, index),
            ),
        )
    return targets


def _overload_branch_helper_name(name: str, index: int) -> str:
    return f"_j2py_overload_{name}_{index}"


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
    static_member_bindings: dict[str, JavaMemberBinding],
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
            static_member_bindings=dict(static_member_bindings),
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
    static_member_map = static_member_bindings or {}
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
            static_member_bindings=static_member_map,
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
            static_member_bindings=static_member_map,
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
            static_member_bindings=static_member_map,
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
            static_member_bindings=static_member_map,
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
        static_member_bindings=static_member_map,
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

    manual_reason = _manual_dispatch_reason(name, classification)
    manual_category = (
        "unsafe_numeric_width_boundary"
        if _numeric_width_boundary_note(classification.java_type_shape_signatures)
        else "overload_erasure_collision"
    )
    manual_facts = {
        "method": name,
        "erased": _format_signature_set(classification.erased_signatures),
        "java_shapes": _format_signature_set(classification.java_type_shape_signatures),
    }
    lines = _overload_stubs(members, cfg, diagnostics)
    branch_targets = overload_call_targets_for_group(
        members,
        cfg,
        python_name_override=name,
    )
    if branch_targets:
        lines.extend(
            _manual_overload_branch_helpers(
                members,
                branch_targets,
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
                static_member_bindings=static_member_map,
                name_resolver=resolver,
                class_state=class_state,
                inner_class_names_requiring_outer=inner_capture_names,
                nested_class_names=direct_nested_names,
            ),
        )
    fallback_return = "None" if members[0].type == "constructor_declaration" else "object"
    is_static = "static" in _modifiers(members[0])
    if branch_targets:
        char_dispatch = _manual_char_string_erasure_dispatcher(
            members,
            branch_targets,
            cfg,
            name=name,
            is_static=is_static,
            return_type=fallback_return,
            containing_class_name=containing_class_name,
        )
        if char_dispatch is not None:
            for member in members:
                diagnostics.record(
                    member,
                    supported=True,
                    reason="translated char/String erasure overload via helper dispatch",
                )
            lines.extend(char_dispatch)
            return lines
    for member in members:
        diagnostics.record(
            member,
            supported=False,
            reason=manual_reason,
            category=manual_category,
            facts=manual_facts,
        )
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
    lines.append(f"        # {manual_reason}")
    lines.append('        raise NotImplementedError("j2py overload dispatch required")')
    return lines


def _manual_overload_branch_helpers(
    members: list[JavaNode],
    targets: list[JavaOverloadCallTarget],
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
    static_member_bindings: dict[str, JavaMemberBinding],
    name_resolver: NameResolver,
    class_state: ClassTranslationState | None,
    inner_class_names_requiring_outer: set[str],
    nested_class_names: set[str],
) -> list[str]:
    lines: list[str] = []
    target_map = {targets[0].member: list(targets)}
    for member, target in zip(members, targets, strict=True):
        lines.append("")
        ctx = TranslationContext(
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
            static_member_bindings=dict(static_member_bindings),
            overload_call_targets=target_map,
            name_resolver=name_resolver,
            allow_local_helpers=True,
            class_state=class_state,
            inner_class_names_requiring_outer=inner_class_names_requiring_outer,
            containing_class_name=containing_class_name,
            nested_class_names=nested_class_names,
        )
        lines.extend(
            translate_method(
                member,
                ctx,
                python_name_override=target.helper_name,
                supported_reason="translated body-backed overload branch",
            ),
        )
    if lines:
        lines.append("")
    return lines


def _manual_dispatch_reason(name: str, classification: OverloadClassification) -> str:
    details = [
        f"erased={_format_signature_set(classification.erased_signatures)}",
        f"java_shapes={_format_signature_set(classification.java_type_shape_signatures)}",
    ]
    boundary = _numeric_width_boundary_note(classification.java_type_shape_signatures)
    if boundary:
        details.append(boundary)
    return f"overloaded method {name} requires manual dispatch [{' | '.join(details)}]"


def _manual_char_string_erasure_dispatcher(
    members: list[JavaNode],
    targets: list[JavaOverloadCallTarget],
    cfg: TranslationConfig,
    *,
    name: str,
    is_static: bool,
    return_type: str,
    containing_class_name: str,
) -> list[str] | None:
    """Route char/Character/String erasure collisions through emitted helpers."""
    if len(members) != len(targets):
        return None
    params_by_member = [parameter_infos(member, cfg) for member in members]
    if any(any(param.is_spread for param in params) for params in params_by_member):
        return None
    if not _is_char_string_erasure_group(params_by_member):
        return None
    if not _character_wrappers_are_reviewable(members, params_by_member):
        return None

    entries = list(zip(members, targets, params_by_member, strict=True))
    lines: list[str] = []
    if is_static:
        lines.append("    @staticmethod  # type: ignore[misc]")
        signature = f"def {name}(*args: object) -> {return_type}:"
    else:
        signature = f"def {name}(self, *args: object) -> {return_type}:"
    lines.append(f"    {signature}")
    indent = "        "
    emitted = False
    for arity in sorted({len(params) for _, _, params in entries}):
        arity_entries = [entry for entry in entries if len(entry[2]) == arity]
        null_entry = _nullable_reference_entry(arity_entries)
        if null_entry is not None:
            _, target, params = null_entry
            condition = _char_erasure_condition(params, nullable=True, require_none=True)
            if condition is not None:
                helper_call = _helper_call(
                    target,
                    params,
                    is_static=is_static,
                    owner=containing_class_name,
                )
                lines.append(f"{indent}if {condition}:")
                lines.append(f"{indent}    return {helper_call}")
                emitted = True
        for _, target, params in sorted(
            arity_entries,
            key=lambda entry: _char_erasure_specificity(entry[2]),
            reverse=True,
        ):
            condition = _char_erasure_condition(params, nullable=False, require_none=False)
            if condition is None:
                return None
            helper_call = _helper_call(
                target,
                params,
                is_static=is_static,
                owner=containing_class_name,
            )
            lines.append(f"{indent}if {condition}:")
            lines.append(f"{indent}    return {helper_call}")
            emitted = True
    if not emitted:
        return None
    lines.append(f'{indent}raise TypeError("{name} overload dispatch failed")')
    return lines


def _is_char_string_erasure_group(params_by_member: list[list[ParameterInfo]]) -> bool:
    saw_erased_collision = False
    by_arity: dict[int, set[tuple[str, ...]]] = {}
    for params in params_by_member:
        signature: list[str] = []
        for param in params:
            simple = param.java_type.rsplit(".", 1)[-1]
            if simple in {"char", "Character", "String"}:
                signature.append("str")
            elif simple in {"int", "Integer"}:
                signature.append("int")
            else:
                return False
        signatures = by_arity.setdefault(len(params), set())
        current = tuple(signature)
        if current in signatures:
            saw_erased_collision = True
        signatures.add(current)
    return saw_erased_collision


def _character_wrappers_are_reviewable(
    members: list[JavaNode],
    params_by_member: list[list[ParameterInfo]],
) -> bool:
    for member, params in zip(members, params_by_member, strict=True):
        if not any(param.java_type.rsplit(".", 1)[-1] == "Character" for param in params):
            continue
        body = member.child_by_field("body")
        text = body.text if body is not None else ""
        if "charValue()" not in text and "requireNonNull" not in text and "toChar(" not in text:
            return False
    return True


def _nullable_reference_entry(
    entries: list[tuple[JavaNode, JavaOverloadCallTarget, list[ParameterInfo]]],
) -> tuple[JavaNode, JavaOverloadCallTarget, list[ParameterInfo]] | None:
    for simple_name in ("Character", "String"):
        for entry in entries:
            if any(param.java_type.rsplit(".", 1)[-1] == simple_name for param in entry[2]):
                return entry
    return None


def _char_erasure_condition(
    params: list[ParameterInfo],
    *,
    nullable: bool,
    require_none: bool,
) -> str | None:
    parts = [f"len(args) == {len(params)}"]
    none_checks: list[str] = []
    for index, param in enumerate(params):
        simple = param.java_type.rsplit(".", 1)[-1]
        arg = f"args[{index}]"
        if simple == "char":
            parts.append(f"isinstance({arg}, str) and len({arg}) == 1")
        elif simple == "Character":
            if nullable:
                parts.append(f"({arg} is None or (isinstance({arg}, str) and len({arg}) == 1))")
                none_checks.append(f"{arg} is None")
            else:
                parts.append(f"isinstance({arg}, str) and len({arg}) == 1")
        elif simple == "String":
            if nullable:
                parts.append(f"({arg} is None or isinstance({arg}, str))")
                none_checks.append(f"{arg} is None")
            else:
                parts.append(f"isinstance({arg}, str)")
        elif simple in {"int", "Integer"}:
            parts.append(f"isinstance({arg}, int) and not isinstance({arg}, bool)")
        else:
            return None
    if require_none:
        if not none_checks:
            return None
        parts.append("(" + " or ".join(none_checks) + ")")
    return " and ".join(parts)


def _char_erasure_specificity(params: list[ParameterInfo]) -> tuple[int, int]:
    score = 0
    for param in params:
        simple = param.java_type.rsplit(".", 1)[-1]
        if simple == "char":
            score += 30
        elif simple == "Character":
            score += 20
        elif simple == "String":
            score += 10
        else:
            score += 5
    return (score, len(params))


def _helper_call(
    target: JavaOverloadCallTarget,
    params: list[ParameterInfo],
    *,
    is_static: bool,
    owner: str,
) -> str:
    args = ", ".join(f"args[{index}]" for index in range(len(params)))
    if is_static:
        return f"{owner}.{target.helper_name}({args})"
    return f"self.{target.helper_name}({args})"


def _format_signature_set(signatures: tuple[tuple[str, ...], ...]) -> str:
    if not signatures:
        return "()"
    return "|".join("(" + ", ".join(signature) + ")" for signature in signatures)


def _numeric_width_boundary_note(
    java_shapes: tuple[tuple[str, ...], ...],
) -> str:
    if not java_shapes:
        return ""
    by_position: dict[int, set[str]] = {}
    by_position_erasure: dict[int, set[str]] = {}
    for signature in java_shapes:
        for index, shape in enumerate(signature):
            category, _, rest = shape.partition(":")
            simple, _, erasure = rest.partition("->")
            if category != "numeric" or not simple or not erasure:
                continue
            by_position.setdefault(index, set()).add(simple)
            by_position_erasure.setdefault(index, set()).add(erasure.split("[", 1)[0])
    for index, simples in by_position.items():
        if len(simples) > 1 and by_position_erasure.get(index) == {"int"}:
            return "note=Java numeric widths erase to one Python runtime int"
    return ""

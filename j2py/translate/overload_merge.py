"""Default-parameter and forwarding overload merge helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_members import member_python_name
from j2py.translate.class_methods import (
    _IMMUTABLE_LITERAL_NODES,
    method_body,
    parameter_infos,
    register_param,
)
from j2py.translate.class_methods import return_type as method_return_type
from j2py.translate.class_methods import signature as render_method_signature
from j2py.translate.class_model import ParameterInfo, _modifiers
from j2py.translate.diagnostics import (
    ClassTranslationState,
    TranslationContext,
    TranslationDiagnostics,
)
from j2py.translate.expressions import translate_expression
from j2py.translate.member_resolution import JavaMemberBinding
from j2py.translate.name_resolution import NameResolver
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.overload_equivalence import (
    _comparison_body_form,
    _member_body_equivalence_key,
    _member_body_preference_score,
)
from j2py.translate.overload_signatures import _overload_stubs, _union_types
from j2py.translate.statements import translate_body


@dataclass(frozen=True)
class _OverloadForward:
    """One member of an overload group with its forwarded argument nodes, if any."""

    member: JavaNode
    params: list[ParameterInfo]
    forwarded: list[JavaNode] | None


@dataclass(frozen=True)
class _MergedDefault:
    text: str
    is_literal: bool


def _constant_python_name(name: str) -> Callable[[JavaNode], str]:
    def python_name_for_member(_member: JavaNode) -> str:
        return name

    return python_name_for_member


def _merged_constructor_overload(
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
    static_member_bindings: dict[str, JavaMemberBinding] | None,
    name_resolver: NameResolver,
    pre_body_lines: list[str],
    extra_params: list[ParameterInfo],
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
) -> list[str] | None:
    super_delegating = _merged_super_constructor_overload(
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
        extra_params=extra_params,
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        nested_class_names=nested_class_names,
    )
    if super_delegating is not None:
        return super_delegating

    equivalent = _merged_equivalent_constructor_overload(
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
        extra_params=extra_params,
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        nested_class_names=nested_class_names,
    )
    if equivalent is not None:
        return equivalent

    forwards = [
        _OverloadForward(member, parameter_infos(member, cfg), _constructor_forward_args(member))
        for member in members
    ]
    merged = _resolve_overload_defaults(
        forwards,
        cfg,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
        static_member_bindings=static_member_bindings,
        name_resolver=name_resolver,
    )
    if merged is None:
        return None
    impl, defaults_by_position, throwaway_diagnostics = merged
    diagnostics.handled.extend(throwaway_diagnostics.handled)
    diagnostics.unhandled.extend(throwaway_diagnostics.unhandled)
    diagnostics.warnings.extend(throwaway_diagnostics.warnings)

    diagnostics.record(
        impl.member,
        supported=True,
        reason="translated overloaded constructor implementation",
    )
    for forward in forwards:
        if forward is not impl:
            diagnostics.record(
                forward.member,
                supported=True,
                reason="translated constructor delegation",
            )

    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_methods=class_methods,
        class_static_methods=class_static_methods,
        enclosing_static_dispatch=enclosing_static_dispatch,
        static_field_aliases=dict(static_field_aliases),
        static_method_imports=dict(static_method_imports),
        static_member_bindings=dict(static_member_bindings or {}),
        name_resolver=name_resolver,
        allow_local_helpers=True,
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
        containing_class_name=containing_class_name,
        nested_class_names=nested_class_names or set(),
    )
    ctx.class_field_types = dict(class_field_types)
    ctx.class_field_java_types = dict(class_field_java_types)
    ctx.declared_type_fields = dict(declared_type_fields)
    ctx.declared_type_java_fields = dict(declared_type_java_fields)
    ctx.class_method_return_types = dict(class_method_return_types)
    ctx.in_instance_method = True
    for param in extra_params:
        register_param(ctx, param)
    for param in impl.params:
        register_param(ctx, param)

    signature_params, defaults, sentinel_lines = _defaulted_parameters(
        impl.params,
        defaults_by_position,
    )
    signature_params = [
        param
        for param in extra_params
        if param.raw_name not in {item.raw_name for item in impl.params}
    ] + signature_params
    if cfg.emit_type_hints:
        for param in extra_params:
            diagnostics.imports.need_type_annotation(param.py_type)

    diagnostics.imports.update(throwaway_diagnostics.imports)

    lines = _overload_stubs(members, cfg, diagnostics)
    signature = render_method_signature(
        "__init__",
        signature_params,
        return_type="None",
        include_self=True,
        defaults=defaults,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    body = method_body(impl.member)
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    if docstring_lines:
        lines.extend(docstring_lines)
        if sentinel_lines or pre_body_lines or body_lines != ["        pass"]:
            lines.append("")
    lines.extend(sentinel_lines)
    lines.extend(pre_body_lines)

    # Flush block-lambda helpers for the merged constructor implementation
    # (same pattern as the normal method path).
    if ctx.pending_local_helpers:
        for helper in ctx.pending_local_helpers:
            lines.append("")
            lines.extend(helper)

    lines.extend(body_lines)
    return lines


def _merged_equivalent_constructor_overload(
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
    pre_body_lines: list[str],
    extra_params: list[ParameterInfo],
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
) -> list[str] | None:
    if any(member.type != "constructor_declaration" for member in members):
        return None
    body_keys = {_member_body_equivalence_key(member, cfg) for member in members}
    if len(body_keys) != 1:
        return None
    if all(_comparison_body_form(member, cfg) is not None for member in members):
        return None
    param_sets = [parameter_infos(member, cfg) for member in members]
    if not _same_constructor_parameter_shape(param_sets):
        return None
    impl_member = min(members, key=lambda member: _member_body_preference_score(member, cfg))
    return _emit_merged_constructor(
        members,
        impl_member=impl_member,
        signature_params=_merged_constructor_parameters(param_sets),
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
        extra_params=extra_params,
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        nested_class_names=nested_class_names,
        implementation_reason="translated overloaded constructor implementation",
        merged_reason="translated equivalent constructor overload",
    )


def _merged_super_constructor_overload(
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
    pre_body_lines: list[str],
    extra_params: list[ParameterInfo],
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
) -> list[str] | None:
    if any(member.type != "constructor_declaration" for member in members):
        return None
    forwards = [
        _OverloadForward(
            member,
            parameter_infos(member, cfg),
            _constructor_super_forward_args(member),
        )
        for member in members
    ]
    if any(forward.forwarded is None for forward in forwards):
        return None
    param_sets = [forward.params for forward in forwards]
    if not _same_constructor_parameter_shape(param_sets):
        return None
    for forward in forwards:
        own_names = {param.raw_name: index for index, param in enumerate(forward.params)}
        vector = _forward_entries(forward.forwarded or [], own_names)
        if vector is None or len(vector) != len(forward.params):
            return None
        if any(entry != position for position, entry in enumerate(vector)):
            return None
    impl_member = min(
        members,
        key=lambda member: _member_body_preference_score(member, cfg),
    )
    return _emit_merged_constructor(
        members,
        impl_member=impl_member,
        signature_params=_merged_constructor_parameters(param_sets),
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
        extra_params=extra_params,
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        nested_class_names=nested_class_names,
        implementation_reason="translated superclass-delegating constructor overload",
        merged_reason="translated superclass-delegating constructor overload",
    )


def _same_constructor_parameter_shape(param_sets: list[list[ParameterInfo]]) -> bool:
    if len({len(params) for params in param_sets}) != 1:
        return False
    if not param_sets or not param_sets[0]:
        return False
    raw_names = [param.raw_name for param in param_sets[0]]
    return all(
        [param.raw_name for param in params] == raw_names
        and [param.is_spread for param in params] == [param.is_spread for param in param_sets[0]]
        for params in param_sets
    )


def _merged_constructor_parameters(
    param_sets: list[list[ParameterInfo]],
) -> list[ParameterInfo]:
    return [
        ParameterInfo(
            raw_name=param_sets[0][index].raw_name,
            py_name=param_sets[0][index].py_name,
            py_type=_union_types(params[index].py_type for params in param_sets),
            java_type=param_sets[0][index].java_type,
            is_spread=param_sets[0][index].is_spread,
        )
        for index in range(len(param_sets[0]))
    ]


def _emit_merged_constructor(
    members: list[JavaNode],
    *,
    impl_member: JavaNode,
    signature_params: list[ParameterInfo],
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
    pre_body_lines: list[str],
    extra_params: list[ParameterInfo],
    class_state: ClassTranslationState | None,
    docstring_lines: list[str] | None,
    inner_class_names_requiring_outer: set[str] | None,
    nested_class_names: set[str] | None,
    implementation_reason: str,
    merged_reason: str,
) -> list[str]:
    for member in members:
        diagnostics.record(
            member,
            supported=True,
            reason=implementation_reason if member is impl_member else merged_reason,
        )

    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_methods=class_methods,
        class_static_methods=class_static_methods,
        enclosing_static_dispatch=enclosing_static_dispatch,
        static_field_aliases=dict(static_field_aliases),
        static_method_imports=dict(static_method_imports),
        name_resolver=name_resolver,
        allow_local_helpers=True,
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
        containing_class_name=containing_class_name,
        nested_class_names=nested_class_names or set(),
    )
    ctx.class_field_types = dict(class_field_types)
    ctx.class_field_java_types = dict(class_field_java_types)
    ctx.declared_type_fields = dict(declared_type_fields)
    ctx.declared_type_java_fields = dict(declared_type_java_fields)
    ctx.class_method_return_types = dict(class_method_return_types)
    ctx.in_instance_method = True
    for param in extra_params:
        register_param(ctx, param)
    for param in signature_params:
        register_param(ctx, param)

    signature_params = [
        param
        for param in extra_params
        if param.raw_name not in {item.raw_name for item in signature_params}
    ] + signature_params
    if cfg.emit_type_hints:
        for param in signature_params:
            diagnostics.imports.need_type_annotation(param.py_type)

    lines = _overload_stubs(members, cfg, diagnostics)
    signature = render_method_signature(
        "__init__",
        signature_params,
        return_type="None",
        include_self=True,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    body = method_body(impl_member)
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    if docstring_lines:
        lines.extend(docstring_lines)
        if pre_body_lines or body_lines != ["        pass"]:
            lines.append("")
    lines.extend(pre_body_lines)
    if ctx.pending_local_helpers:
        for helper in ctx.pending_local_helpers:
            lines.append("")
            lines.extend(helper)
    lines.extend(body_lines)
    return lines


def _merged_forwarding_method_overload(
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
    static_member_bindings: dict[str, JavaMemberBinding] | None,
    name_resolver: NameResolver,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
    python_name_override: str | None = None,
) -> list[str] | None:
    """Merge builder-style overloads where shorter ones forward to the longest one."""
    if any(member.type != "method_declaration" for member in members):
        return None
    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None

    forwards = [
        _OverloadForward(member, parameter_infos(member, cfg), _method_forward_args(member))
        for member in members
    ]
    merged = _resolve_overload_defaults(
        forwards,
        cfg,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
        static_member_bindings=static_member_bindings,
        name_resolver=name_resolver,
    )
    pass_through_forwarding = False
    if merged is None:
        impl = _resolve_pass_through_forwarding(forwards)
        if impl is None:
            return None
        defaults_by_position: dict[int, _MergedDefault] = {}
        throwaway_diagnostics = TranslationDiagnostics()
        pass_through_forwarding = True
    else:
        impl, defaults_by_position, throwaway_diagnostics = merged
    if method_body(impl.member) is None:
        return None
    diagnostics.handled.extend(throwaway_diagnostics.handled)
    diagnostics.unhandled.extend(throwaway_diagnostics.unhandled)
    diagnostics.warnings.extend(throwaway_diagnostics.warnings)

    diagnostics.record(
        impl.member,
        supported=True,
        reason="translated overloaded method implementation",
    )
    for forward in forwards:
        if forward is not impl:
            diagnostics.record(
                forward.member,
                supported=True,
                reason=(
                    "translated pass-through forwarding method overload"
                    if pass_through_forwarding
                    else "translated forwarding method overload"
                ),
            )

    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_methods=class_methods,
        class_static_methods=class_static_methods,
        enclosing_static_dispatch=enclosing_static_dispatch,
        static_field_aliases=dict(static_field_aliases),
        static_method_imports=dict(static_method_imports),
        static_member_bindings=dict(static_member_bindings or {}),
        name_resolver=name_resolver,
        allow_local_helpers=True,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
        containing_class_name=containing_class_name,
        nested_class_names=nested_class_names or set(),
    )
    ctx.class_field_types = dict(class_field_types)
    ctx.class_field_java_types = dict(class_field_java_types)
    ctx.declared_type_fields = dict(declared_type_fields)
    ctx.declared_type_java_fields = dict(declared_type_java_fields)
    ctx.class_method_return_types = dict(class_method_return_types)
    ctx.in_instance_method = not is_static
    for param in impl.params:
        register_param(ctx, param)

    signature_params, defaults, sentinel_lines = _defaulted_parameters(
        impl.params,
        defaults_by_position,
    )
    return_type = _union_types(method_return_type(member, cfg) for member in members)

    diagnostics.imports.update(throwaway_diagnostics.imports)

    lines = _overload_stubs(
        members,
        cfg,
        diagnostics,
        python_name_for_member=(
            _constant_python_name(python_name_override)
            if python_name_override is not None
            else None
        ),
    )
    if is_static:
        lines.append("    @staticmethod")
    signature = render_method_signature(
        python_name_override or member_python_name(impl.member),
        signature_params,
        return_type=return_type,
        include_self=not is_static,
        defaults=defaults,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    body = method_body(impl.member)
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    if docstring_lines:
        lines.extend(docstring_lines)
        if sentinel_lines or body_lines != ["        pass"]:
            lines.append("")
    lines.extend(sentinel_lines)

    # Flush block-lambda helpers for the merged method implementation.
    if ctx.pending_local_helpers:
        for helper in ctx.pending_local_helpers:
            lines.append("")
            lines.extend(helper)

    lines.extend(body_lines)
    return lines


def _resolve_overload_defaults(
    forwards: list[_OverloadForward],
    cfg: TranslationConfig,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    static_member_bindings: dict[str, JavaMemberBinding] | None,
    name_resolver: NameResolver,
) -> tuple[_OverloadForward, dict[int, _MergedDefault], TranslationDiagnostics] | None:
    """Resolve forwarding chains into per-position defaults on the implementation.

    Returns None unless the group has exactly one non-forwarding implementation,
    pairwise-distinct arities, and every other overload passes its own parameters
    through positionally and forwards only closed expressions for the rest.
    """
    implementations = [forward for forward in forwards if forward.forwarded is None]
    if len(implementations) != 1:
        return None
    impl = implementations[0]
    if not impl.params:
        return None

    arities = [len(forward.params) for forward in forwards]
    if len(set(arities)) != len(arities):
        return None
    by_arity = {len(forward.params): forward for forward in forwards}

    defaults_by_position: dict[int, _MergedDefault] = {}
    throwaway_diagnostics = TranslationDiagnostics()
    throwaway = TranslationContext(
        cfg=cfg,
        diagnostics=throwaway_diagnostics,
        static_field_aliases=dict(static_field_aliases),
        static_method_imports=dict(static_method_imports),
        static_member_bindings=dict(static_member_bindings or {}),
        name_resolver=name_resolver,
    )
    for forward in forwards:
        if forward is impl:
            continue
        vector = _resolve_forward_chain(forward, by_arity, impl)
        if vector is None or len(vector) != len(impl.params):
            return None
        prefix = len(forward.params)
        for position, entry in enumerate(vector):
            if position < prefix:
                if entry != position:
                    return None
                continue
            if isinstance(entry, int):
                return None
            default = _MergedDefault(
                text=translate_expression(entry, throwaway),
                is_literal=_is_immutable_literal(entry),
            )
            existing = defaults_by_position.get(position)
            if existing is not None and existing != default:
                return None
            defaults_by_position[position] = default

    if not defaults_by_position:
        return None
    return impl, defaults_by_position, throwaway_diagnostics


def _resolve_pass_through_forwarding(forwards: list[_OverloadForward]) -> _OverloadForward | None:
    """Resolve same-arity forwarding overloads that pass every parameter through."""
    if any(forward.member.type != "method_declaration" for forward in forwards):
        return None
    implementations = [forward for forward in forwards if forward.forwarded is None]
    if len(implementations) != 1:
        return None
    impl = implementations[0]
    if not impl.params:
        return None

    for forward in forwards:
        if forward is impl:
            continue
        if (
            forward.forwarded is None
            or len(forward.params) != len(impl.params)
            or len(forward.forwarded) != len(impl.params)
        ):
            return None
        own_names = {param.raw_name: index for index, param in enumerate(forward.params)}
        vector = _forward_entries(forward.forwarded, own_names)
        if vector is None or len(vector) != len(impl.params):
            return None
        for position, entry in enumerate(vector):
            if entry != position:
                return None
    return impl


def _resolve_forward_chain(
    start: _OverloadForward,
    by_arity: dict[int, _OverloadForward],
    impl: _OverloadForward,
) -> list[int | JavaNode] | None:
    """Follow this(...)/method forwarding hops down to the implementation arity.

    Vector entries are either an index into ``start``'s parameters (pass-through)
    or a closed expression node contributed somewhere along the chain.
    """
    assert start.forwarded is not None
    own_names = {param.raw_name: index for index, param in enumerate(start.params)}
    vector = _forward_entries(start.forwarded, own_names)
    if vector is None:
        return None

    visited = {len(start.params)}
    while True:
        arity = len(vector)
        if arity in visited:
            return None
        visited.add(arity)
        target = by_arity.get(arity)
        if target is None:
            return None
        if target is impl:
            return vector
        if target.forwarded is None:
            return None
        target_names = {param.raw_name: index for index, param in enumerate(target.params)}
        next_vector: list[int | JavaNode] = []
        for arg in target.forwarded:
            if arg.type == "identifier" and arg.text in target_names:
                next_vector.append(vector[target_names[arg.text]])
            elif _references_names(arg, set(target_names)):
                return None
            else:
                next_vector.append(arg)
        vector = next_vector


def _forward_entries(
    args: list[JavaNode],
    own_names: dict[str, int],
) -> list[int | JavaNode] | None:
    entries: list[int | JavaNode] = []
    for arg in args:
        pass_through = _pass_through_argument(arg, own_names)
        if pass_through is not None:
            entries.append(pass_through)
        elif _references_names(arg, set(own_names)):
            return None
        else:
            entries.append(arg)
    return entries


_BOXED_PRIMITIVE_VALUE_OF_RECEIVERS = frozenset(
    {
        "Boolean",
        "Byte",
        "Short",
        "Integer",
        "Long",
        "Float",
        "Double",
        "Character",
    }
)


def _pass_through_argument(arg: JavaNode, own_names: dict[str, int]) -> int | None:
    arg = _unwrap_pass_through_argument(arg)
    if arg.type == "identifier" and arg.text in own_names:
        return own_names[arg.text]
    if arg.type != "method_invocation":
        return None
    name = arg.child_by_field("name")
    receiver = arg.child_by_field("object")
    args_node = first_child_by_type(arg, "argument_list")
    if (
        name is None
        or receiver is None
        or args_node is None
        or name.text != "valueOf"
        or receiver.text not in _BOXED_PRIMITIVE_VALUE_OF_RECEIVERS
    ):
        return None
    arg_nodes = list(args_node.named_children)
    if len(arg_nodes) != 1 or arg_nodes[0].type != "identifier":
        return None
    return own_names.get(arg_nodes[0].text)


def _unwrap_pass_through_argument(arg: JavaNode) -> JavaNode:
    while arg.type in {"cast_expression", "parenthesized_expression"} and arg.named_children:
        arg = arg.named_children[-1]
    return arg


def _references_names(node: JavaNode, names: set[str]) -> bool:
    return any(child.type == "identifier" and child.text in names for child in node.walk())


def _is_immutable_literal(node: JavaNode) -> bool:
    if node.type in _IMMUTABLE_LITERAL_NODES:
        return True
    if node.type == "unary_expression":
        children = node.named_children
        return len(children) == 1 and children[0].type in _IMMUTABLE_LITERAL_NODES
    return False


def _defaulted_parameters(
    params: list[ParameterInfo],
    defaults_by_position: dict[int, _MergedDefault],
) -> tuple[list[ParameterInfo], dict[str, str], list[str]]:
    """Apply merged defaults to the implementation parameters.

    Immutable literals become plain Python default values. Anything else uses a
    None sentinel plus a normalization line so mutable defaults are not shared.
    """
    signature_params: list[ParameterInfo] = []
    defaults: dict[str, str] = {}
    sentinel_lines: list[str] = []
    for position, param in enumerate(params):
        default = defaults_by_position.get(position)
        if default is None:
            signature_params.append(param)
            continue
        if default.is_literal:
            signature_params.append(param)
            defaults[param.py_name] = default.text
            continue
        annotation = (
            param.py_type if param.py_type.endswith("| None") else f"{param.py_type} | None"
        )
        signature_params.append(
            ParameterInfo(
                raw_name=param.raw_name,
                py_name=param.py_name,
                py_type=annotation,
                java_type=param.java_type,
            ),
        )
        defaults[param.py_name] = "None"
        sentinel_lines.append(f"        if {param.py_name} is None:")
        sentinel_lines.append(f"            {param.py_name} = {default.text}")
    return signature_params, defaults, sentinel_lines


def _merged_method_overload(
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
    static_member_bindings: dict[str, JavaMemberBinding] | None,
    name_resolver: NameResolver,
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
    python_name_override: str | None = None,
) -> list[str] | None:
    if any(member.type != "method_declaration" for member in members):
        return None
    body_keys = {_member_body_equivalence_key(member, cfg) for member in members}
    if len(body_keys) != 1:
        return None
    if all(_comparison_body_form(member, cfg) is not None for member in members):
        return None

    param_sets = [parameter_infos(member, cfg) for member in members]
    if len({len(params) for params in param_sets}) != 1:
        return None
    if len(param_sets[0]) == 0:
        return None

    raw_names = [param.raw_name for param in param_sets[0]]
    if any([param.raw_name for param in params] != raw_names for params in param_sets):
        return None

    name = python_name_override or member_python_name(members[0])
    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None
    impl_member = min(members, key=lambda member: _member_body_preference_score(member, cfg))

    merged_params = [
        ParameterInfo(
            raw_name=param_sets[0][index].raw_name,
            py_name=param_sets[0][index].py_name,
            py_type=_union_types(params[index].py_type for params in param_sets),
            java_type=param_sets[0][index].java_type,
            is_spread=param_sets[0][index].is_spread,
        )
        for index in range(len(param_sets[0]))
    ]
    return_type = _union_types(method_return_type(member, cfg) for member in members)

    for member in members:
        diagnostics.record(member, supported=True, reason="translated overloaded method")

    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_methods=class_methods,
        class_static_methods=class_static_methods,
        enclosing_static_dispatch=enclosing_static_dispatch,
        static_field_aliases=dict(static_field_aliases),
        static_method_imports=dict(static_method_imports),
        static_member_bindings=dict(static_member_bindings or {}),
        name_resolver=name_resolver,
        allow_local_helpers=True,
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
        containing_class_name=containing_class_name,
        nested_class_names=nested_class_names or set(),
    )
    ctx.class_field_types = dict(class_field_types)
    ctx.class_field_java_types = dict(class_field_java_types)
    ctx.declared_type_fields = dict(declared_type_fields)
    ctx.declared_type_java_fields = dict(declared_type_java_fields)
    ctx.class_method_return_types = dict(class_method_return_types)
    ctx.in_instance_method = not is_static
    for param in merged_params:
        register_param(ctx, param)

    lines = _overload_stubs(
        members,
        cfg,
        diagnostics,
        python_name_for_member=(
            _constant_python_name(python_name_override)
            if python_name_override is not None
            else None
        ),
    )
    if is_static:
        lines.append("    @staticmethod")
    signature = render_method_signature(
        name,
        merged_params,
        return_type=return_type,
        include_self=not is_static,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    body = method_body(impl_member)
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    if docstring_lines:
        lines.extend(docstring_lines)
        if body_lines != ["        pass"]:
            lines.append("")

    # Flush block-lambda helpers for this merged method implementation.
    if ctx.pending_local_helpers:
        for helper in ctx.pending_local_helpers:
            lines.append("")
            lines.extend(helper)

    lines.extend(body_lines)
    return lines


def _constructor_forward_args(member: JavaNode) -> list[JavaNode] | None:
    """Return the argument nodes of a pure this(...) delegating constructor."""
    return _explicit_constructor_args(member, target_type="this")


def _constructor_super_forward_args(member: JavaNode) -> list[JavaNode] | None:
    """Return the argument nodes of a pure super(...) delegating constructor."""
    return _explicit_constructor_args(member, target_type="super")


def _explicit_constructor_args(member: JavaNode, *, target_type: str) -> list[JavaNode] | None:
    body = method_body(member)
    if body is None:
        return None
    children = body.named_children
    if len(children) != 1 or children[0].type != "explicit_constructor_invocation":
        return None
    invocation = children[0]
    target = invocation.named_children[0] if invocation.named_children else None
    if target is None or target.type != target_type:
        return None
    args_node = first_child_by_type(invocation, "argument_list")
    return [] if args_node is None else list(args_node.named_children)


def _method_forward_args(member: JavaNode) -> list[JavaNode] | None:
    """Return the argument nodes of a pure same-name forwarding method overload."""
    name_node = member.child_by_field("name")
    if name_node is None:
        return None
    body = method_body(member)
    if body is None:
        return None
    children = body.named_children
    if len(children) != 1:
        return None
    statement = children[0]
    if statement.type in {"return_statement", "expression_statement"}:
        inner = statement.named_children
        if len(inner) != 1:
            return None
        invocation = inner[0]
    else:
        return None
    if invocation.type != "method_invocation":
        return None
    invoked_name = invocation.child_by_field("name")
    if invoked_name is None or invoked_name.text != name_node.text:
        return None
    receiver = invocation.child_by_field("object")
    if receiver is not None and receiver.type != "this":
        return None
    args_node = first_child_by_type(invocation, "argument_list")
    return [] if args_node is None else list(args_node.named_children)

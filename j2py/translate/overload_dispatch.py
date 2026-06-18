"""Runtime and value-dispatch overload translation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_members import member_python_name
from j2py.translate.class_methods import (
    method_body,
    parameter_infos,
    register_param,
    translate_method,
)
from j2py.translate.class_methods import return_type as method_return_type
from j2py.translate.class_methods import signature as render_method_signature
from j2py.translate.class_model import ParameterInfo, _modifiers
from j2py.translate.diagnostics import (
    ClassTranslationState,
    TranslationContext,
    TranslationDiagnostics,
)
from j2py.translate.member_resolution import JavaMemberBinding
from j2py.translate.name_resolution import NameResolver
from j2py.translate.overload_equivalence import (
    _collapse_equivalent_arity_guard_members,
)
from j2py.translate.overload_guards import (
    _dispatch_guard_for_parameter,
    _DispatchGuard,
    _member_dispatch_key,
    _value_dispatch_assignments,
    _value_dispatch_branch_order_key,
    _value_dispatch_condition,
    _varargs_value_guards_checkable,
)
from j2py.translate.overload_signatures import (
    _erased_overload_signature,
    _has_this_delegation,
    _union_types,
)
from j2py.translate.statements import translate_body


@dataclass(frozen=True)
class _ValueDispatchBranches:
    members: list[JavaNode]
    params_by_member: list[list[ParameterInfo]]
    guards_by_member: list[list[_DispatchGuard]]


def _value_dispatch_overload(
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
    static_member_bindings: dict[str, JavaMemberBinding] | None = None,
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
    python_name_override: str | None = None,
    static_instance_static_aliases: dict[str, str] | None = None,
) -> list[str] | None:
    """Emit ``@overload`` stubs plus one runtime value dispatcher.

    This tier covers overload families that Python can distinguish by arity and
    runtime-checkable value type, including erased collisions such as
    ``char``/``String``. When two Java signatures collapse to the same guard key
    (for example ``int``/``long`` or ``List<String>``/``List<Integer>``), the
    dispatcher would be ambiguous, so the caller keeps trying later tiers.
    """
    preconditions = _value_dispatch_preconditions(
        members,
        python_name_override=python_name_override,
    )
    if preconditions is None:
        return None
    name, is_static = preconditions

    params_by_member = [parameter_infos(member, cfg) for member in members]
    has_varargs = any(any(param.is_spread for param in params) for params in params_by_member)

    guards_by_member = _value_dispatch_guards(params_by_member)
    if guards_by_member is None:
        return None

    branches = _value_dispatch_branches(
        members,
        params_by_member,
        guards_by_member,
        has_varargs=has_varargs,
        cfg=cfg,
    )
    if branches is None:
        return None

    _record_value_dispatch_diagnostics(
        members,
        branch_members=branches.members,
        is_static=is_static,
        diagnostics=diagnostics,
    )

    lines = _value_dispatch_overload_stubs(
        members,
        cfg,
        diagnostics,
        containing_class_name=containing_class_name,
        is_static=is_static,
        python_name_override=python_name_override,
    )
    if is_static:
        lines.append("    @staticmethod  # type: ignore[misc]")
    dispatch_return = _value_dispatch_return_type(
        members,
        cfg,
        diagnostics,
        containing_class_name=containing_class_name,
        is_static=is_static,
    )
    signature = render_method_signature(
        name,
        [
            ParameterInfo(
                raw_name="args",
                py_name="args",
                py_type="object",
                java_type="Object",
                is_spread=True,
            ),
        ],
        return_type=dispatch_return,
        include_self=not is_static,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    if docstring_lines:
        lines.extend(docstring_lines)
        lines.append("")

    ordered = sorted(
        enumerate(
            zip(
                branches.members,
                branches.params_by_member,
                branches.guards_by_member,
                strict=True,
            )
        ),
        key=lambda item: (*_value_dispatch_branch_order_key(item[1]), item[0]),
    )
    for _, (member, params, guards) in ordered:
        condition = _value_dispatch_condition(guards, params)
        lines.append(f"        if {condition}:")
        lines.extend(_value_dispatch_assignments(params, member=member, indent="            "))
        branch_lines = (
            _translate_static_overload_branch_body if is_static else _translate_overload_branch_body
        )(
            member,
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
            class_state=class_state,
            inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
            nested_class_names=nested_class_names or set(),
            indent="            ",
            static_instance_static_aliases=static_instance_static_aliases or {},
        )
        lines.extend(branch_lines)

    lines.append(f'        raise TypeError("{name} overload dispatch failed")')
    return lines


def _value_dispatch_preconditions(
    members: list[JavaNode],
    *,
    python_name_override: str | None,
) -> tuple[str, bool] | None:
    if len(members) < 2:
        return None
    if any(member.type != "method_declaration" for member in members):
        return None
    name = python_name_override or member_python_name(members[0])
    if python_name_override is None and any(
        member_python_name(member) != name for member in members
    ):
        return None

    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None
    return name, is_static


def _value_dispatch_guards(
    params_by_member: list[list[ParameterInfo]],
) -> list[list[_DispatchGuard]] | None:
    guards_by_member: list[list[_DispatchGuard]] = []
    for params in params_by_member:
        guards: list[_DispatchGuard] = []
        for param in params:
            guard = _dispatch_guard_for_parameter(param)
            if guard is None:
                return None
            guards.append(guard)
        guards_by_member.append(guards)
    return guards_by_member


def _value_dispatch_branches(
    members: list[JavaNode],
    params_by_member: list[list[ParameterInfo]],
    guards_by_member: list[list[_DispatchGuard]],
    *,
    has_varargs: bool,
    cfg: TranslationConfig,
) -> _ValueDispatchBranches | None:
    if has_varargs:
        return _value_dispatch_varargs_branches(members, params_by_member, guards_by_member)
    return _value_dispatch_fixed_branches(members, params_by_member, guards_by_member, cfg)


def _value_dispatch_varargs_branches(
    members: list[JavaNode],
    params_by_member: list[list[ParameterInfo]],
    guards_by_member: list[list[_DispatchGuard]],
) -> _ValueDispatchBranches | None:
    for params in params_by_member:
        spread_indices = [index for index, param in enumerate(params) if param.is_spread]
        if len(spread_indices) > 1:
            return None
        if spread_indices and spread_indices[0] != len(params) - 1:
            return None
    dispatch_keys = [
        _member_dispatch_key(params, guards)
        for params, guards in zip(params_by_member, guards_by_member, strict=True)
    ]
    if len(set(dispatch_keys)) != len(dispatch_keys):
        return None
    if not all(
        _varargs_value_guards_checkable(params, guards)
        for params, guards in zip(params_by_member, guards_by_member, strict=True)
    ):
        return None
    return _ValueDispatchBranches(members, params_by_member, guards_by_member)


def _value_dispatch_fixed_branches(
    members: list[JavaNode],
    params_by_member: list[list[ParameterInfo]],
    guards_by_member: list[list[_DispatchGuard]],
    cfg: TranslationConfig,
) -> _ValueDispatchBranches | None:
    guard_signatures = [
        tuple(guard.condition_template for guard in guards) for guards in guards_by_member
    ]
    if len(set(guard_signatures)) == len(guard_signatures):
        return _ValueDispatchBranches(members, params_by_member, guards_by_member)

    collapsed = _collapse_equivalent_arity_guard_members(members, cfg)
    if collapsed is None:
        return None
    collapsed_params = [parameter_infos(member, cfg) for member in collapsed]
    collapsed_guards = _value_dispatch_guards(collapsed_params)
    if collapsed_guards is None:
        return None
    return _ValueDispatchBranches(collapsed, collapsed_params, collapsed_guards)


def _record_value_dispatch_diagnostics(
    members: list[JavaNode],
    *,
    branch_members: list[JavaNode],
    is_static: bool,
    diagnostics: TranslationDiagnostics,
) -> None:
    collapsed_member_ids = {id(member) for member in branch_members}
    for member in members:
        reason = (
            "deduplicated equivalent arity/guard overload branch"
            if id(member) not in collapsed_member_ids
            else (
                "translated static overloaded method via value dispatch"
                if is_static
                else "translated overloaded method via value dispatch"
            )
        )
        diagnostics.record(member, supported=True, reason=reason)


def _value_dispatch_overload_stubs(
    members: list[JavaNode],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    containing_class_name: str,
    is_static: bool,
    python_name_override: str | None = None,
) -> list[str]:
    diagnostics.imports.need_typing("overload")
    lines: list[str] = []
    for member in members:
        if is_static:
            lines.append("    @staticmethod")
        lines.append("    @overload")
        params = parameter_infos(member, cfg)
        return_type = _value_dispatch_member_return_type(
            member,
            cfg,
            diagnostics,
            containing_class_name=containing_class_name,
            is_static=is_static,
        )
        if cfg.emit_type_hints:
            for param in params:
                diagnostics.imports.need_type_annotation(param.py_type)
        signature = render_method_signature(
            python_name_override or member_python_name(member),
            params,
            return_type=return_type,
            include_self=not is_static,
            emit_type_hints=cfg.emit_type_hints,
        )
        lines.append(f"    {signature}: ...")
    return lines


def _value_dispatch_return_type(
    members: list[JavaNode],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    containing_class_name: str,
    is_static: bool,
) -> str:
    return_type = _union_types(
        _value_dispatch_member_return_type(
            member,
            cfg,
            diagnostics,
            containing_class_name=containing_class_name,
            is_static=is_static,
        )
        for member in members
    )
    if _uses_method_type_parameter(return_type, members):
        return_type = "object"
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(return_type)
    return return_type


def _value_dispatch_member_return_type(
    member: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    containing_class_name: str,
    is_static: bool,
) -> str:
    return_type = method_return_type(member, cfg)
    if not is_static and return_type == containing_class_name:
        diagnostics.imports.need_typing("Self")
        return "Self"
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(return_type)
    return return_type


def _uses_method_type_parameter(py_type: str, members: list[JavaNode]) -> bool:
    type_params = {name for member in members for name in _method_type_parameter_names(member)}
    return any(re.search(rf"\b{re.escape(name)}\b", py_type) for name in type_params)


def _method_type_parameter_names(member: JavaNode) -> list[str]:
    type_parameters = next(
        (child for child in member.named_children if child.type == "type_parameters"),
        None,
    )
    if type_parameters is None:
        return []
    names: list[str] = []
    for child in type_parameters.named_children:
        if child.type != "type_parameter":
            continue
        name_node = next(
            (
                grandchild
                for grandchild in child.named_children
                if grandchild.type in {"identifier", "type_identifier"}
            ),
            None,
        )
        if name_node is not None:
            names.append(name_node.text)
    return names


def _translate_static_overload_branch_body(
    member: JavaNode,
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
    class_state: ClassTranslationState | None,
    inner_class_names_requiring_outer: set[str],
    nested_class_names: set[str],
    indent: str,
    static_instance_static_aliases: dict[str, str] | None = None,
) -> list[str]:
    name_node = member.child_by_field("name")
    java_name = name_node.text if name_node is not None else ""
    ctx = _overload_member_context(
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
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        nested_class_names=nested_class_names,
        java_name=java_name,
        is_static=True,
        static_instance_static_aliases=static_instance_static_aliases,
    )
    return _translate_overload_member_body(member, cfg=cfg, ctx=ctx, indent=indent)


def _translate_overload_branch_body(
    member: JavaNode,
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
    class_state: ClassTranslationState | None,
    inner_class_names_requiring_outer: set[str],
    nested_class_names: set[str],
    indent: str,
    static_instance_static_aliases: dict[str, str] | None = None,
) -> list[str]:
    name_node = member.child_by_field("name")
    java_name = name_node.text if name_node is not None else ""
    ctx = _overload_member_context(
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
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        nested_class_names=nested_class_names,
        java_name=java_name,
        is_static=False,
        static_instance_static_aliases=static_instance_static_aliases,
    )
    return _translate_overload_member_body(member, cfg=cfg, ctx=ctx, indent=indent)


def _overload_member_context(
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
    class_state: ClassTranslationState | None,
    inner_class_names_requiring_outer: set[str],
    nested_class_names: set[str],
    java_name: str,
    is_static: bool,
    static_instance_static_aliases: dict[str, str] | None = None,
) -> TranslationContext:
    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_methods=class_methods,
        class_static_methods=class_static_methods,
        enclosing_static_dispatch=dict(enclosing_static_dispatch),
        class_field_types=dict(class_field_types),
        class_field_java_types=dict(class_field_java_types),
        declared_type_fields=dict(declared_type_fields),
        declared_type_java_fields=dict(declared_type_java_fields),
        class_method_return_types=dict(class_method_return_types),
        static_field_aliases=dict(static_field_aliases),
        static_method_imports=dict(static_method_imports),
        static_member_bindings=dict(static_member_bindings or {}),
        name_resolver=name_resolver,
        allow_local_helpers=True,
        self_dispatch_methods={java_name} if java_name and not is_static else set(),
        static_dispatch_methods={java_name} if java_name and is_static else set(),
        static_dispatch_class_name=containing_class_name if is_static else None,
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        containing_class_name=containing_class_name,
        nested_class_names=nested_class_names,
        static_instance_static_aliases=dict(static_instance_static_aliases or {}),
    )
    ctx.in_instance_method = not is_static
    return ctx


def _translate_overload_member_body(
    member: JavaNode,
    *,
    cfg: TranslationConfig,
    ctx: TranslationContext,
    indent: str,
) -> list[str]:
    for param in parameter_infos(member, cfg):
        register_param(ctx, param)
    body = method_body(member)
    ctx.in_method_body = True
    body_lines = translate_body(body, ctx, indent=indent) if body else [f"{indent}pass"]
    ctx.in_method_body = False
    return _body_lines_with_local_context(ctx, body_lines, indent=indent)


def _body_lines_with_local_context(
    ctx: TranslationContext,
    body_lines: list[str],
    *,
    indent: str,
) -> list[str]:
    local_import_lines = sorted(ctx.body_local_imports)
    if not ctx.pending_local_helpers:
        if not local_import_lines:
            return body_lines
        import_lines = [f"{indent}{imp}" for imp in local_import_lines]
        import_lines.append("")
        import_lines.extend(body_lines)
        return import_lines
    lines: list[str] = []
    if local_import_lines:
        for imp in local_import_lines:
            lines.append(f"{indent}{imp}")
        lines.append("")
    for helper in ctx.pending_local_helpers:
        lines.extend(helper)
        lines.append("")
    lines.extend(body_lines)
    return lines


def _dispatch_overload_members(
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
    static_member_bindings: dict[str, JavaMemberBinding] | None = None,
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
    python_name_override: str | None = None,
    static_instance_static_aliases: dict[str, str] | None = None,
) -> list[str] | None:
    """Emit each overload as a same-named def behind the vendored @overloaded dispatcher.

    This preserves every Java overload body 1:1. It only applies when the erased
    Python signatures stay pairwise distinct, so runtime dispatch has a chance of
    telling the overloads apart (see ADR 0009).
    """
    if any(
        member.type not in {"constructor_declaration", "method_declaration"} for member in members
    ):
        return None
    if any(member.type != members[0].type for member in members):
        return None
    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None
    if is_static and members[0].type != "method_declaration":
        return None

    erased = [_erased_overload_signature(member, cfg) for member in members]
    if len(set(erased)) != len(erased):
        return None

    is_constructor = members[0].type == "constructor_declaration"
    reason = (
        "translated overloaded constructor via runtime dispatch"
        if is_constructor
        else (
            "translated static overloaded method via runtime dispatch"
            if is_static
            else "translated overloaded method via runtime dispatch"
        )
    )

    name_node = members[0].child_by_field("name")
    java_name = name_node.text if name_node is not None and not is_constructor else ""
    lines: list[str] = []
    # A group reduced to one member (e.g. via _deduplicate_same_body_erased_sig) needs no
    # runtime dispatcher — emit it as a plain method. The @overloaded decorator only works
    # with two or more distinguishable registrations; on a lone method it would raise an
    # ambiguous-dispatch error at call time.
    single = len(members) == 1
    if not single:
        diagnostics.imports.need_overloaded()
    for index, member in enumerate(members):
        if index:
            lines.append("")
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=class_fields,
            class_methods=class_methods,
            class_static_methods=class_static_methods,
            enclosing_static_dispatch=dict(enclosing_static_dispatch),
            class_field_types=dict(class_field_types),
            class_field_java_types=dict(class_field_java_types),
            declared_type_fields=dict(declared_type_fields),
            declared_type_java_fields=dict(declared_type_java_fields),
            class_method_return_types=dict(class_method_return_types),
            static_field_aliases=dict(static_field_aliases),
            static_method_imports=dict(static_method_imports),
            static_member_bindings=dict(static_member_bindings or {}),
            name_resolver=name_resolver,
            allow_local_helpers=True,
            self_dispatch_methods={java_name} if java_name and not is_static else set(),
            static_dispatch_methods={java_name} if java_name and is_static else set(),
            static_dispatch_class_name=containing_class_name if is_static else None,
            class_state=class_state,
            inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
            containing_class_name=containing_class_name,
            nested_class_names=nested_class_names or set(),
            static_instance_static_aliases=dict(static_instance_static_aliases or {}),
        )
        member_pre_body = (
            pre_body_lines if is_constructor and not _has_this_delegation(member) else []
        )
        lines.extend(
            translate_method(
                member,
                ctx,
                pre_body_lines=member_pre_body,
                decorator_lines=[] if single else ["    @overloaded"],
                extra_params=extra_params if is_constructor else [],
                def_line_suffix=("" if index == 0 else "  # type: ignore[no-redef]  # noqa: F811"),
                supported_reason=reason,
                docstring_lines=docstring_lines if index == len(members) - 1 else None,
                python_name_override=python_name_override,
            ),
        )
    return lines

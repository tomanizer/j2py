"""Runtime and value-dispatch overload translation helpers."""

from __future__ import annotations

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
from j2py.translate.name_resolution import NameResolver
from j2py.translate.overload_signatures import (
    _erase_py_type,
    _erased_overload_signature,
    _has_this_delegation,
    _java_simple_type,
    _union_types,
)
from j2py.translate.statements import translate_body


@dataclass(frozen=True)
class _DispatchGuard:
    """A runtime-checkable guard for one overload parameter."""

    key: str
    specificity: int
    condition_template: str | None = None


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
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
) -> list[str] | None:
    """Emit ``@overload`` stubs plus one runtime value dispatcher.

    This tier covers overload families that Python can distinguish by arity and
    runtime-checkable value type, including erased collisions such as
    ``char``/``String``. When two Java signatures collapse to the same guard key
    (for example ``int``/``long`` or ``List<String>``/``List<Integer>``), the
    dispatcher would be ambiguous, so the caller keeps trying later tiers.
    """
    if len(members) < 2:
        return None
    if any(member.type != "method_declaration" for member in members):
        return None
    name = member_python_name(members[0])
    if any(member_python_name(member) != name for member in members):
        return None

    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None

    params_by_member = [parameter_infos(member, cfg) for member in members]
    has_varargs = any(any(param.is_spread for param in params) for params in params_by_member)

    guards_by_member: list[list[_DispatchGuard]] = []
    for params in params_by_member:
        guards: list[_DispatchGuard] = []
        for param in params:
            guard = _dispatch_guard_for_parameter(param)
            if guard is None:
                return None
            guards.append(guard)
        guards_by_member.append(guards)

    if has_varargs:
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
    else:
        guard_signatures = [
            tuple(guard.condition_template for guard in guards) for guards in guards_by_member
        ]
        if len(set(guard_signatures)) != len(guard_signatures):
            return None

    for member in members:
        diagnostics.record(
            member,
            supported=True,
            reason=(
                "translated static overloaded method via value dispatch"
                if is_static
                else "translated overloaded method via value dispatch"
            ),
        )

    lines = _value_dispatch_overload_stubs(
        members,
        cfg,
        diagnostics,
        containing_class_name=containing_class_name,
        is_static=is_static,
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
        enumerate(zip(members, params_by_member, guards_by_member, strict=True)),
        key=lambda item: (*_value_dispatch_branch_order_key(item[1]), item[0]),
    )
    for _, (member, params, guards) in ordered:
        condition = _value_dispatch_condition(guards, params)
        lines.append(f"        if {condition}:")
        lines.extend(_value_dispatch_assignments(params, indent="            "))
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
            name_resolver=name_resolver,
            class_state=class_state,
            inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
            nested_class_names=nested_class_names or set(),
            indent="            ",
        )
        lines.extend(branch_lines)

    lines.append(f'        raise TypeError("{name} overload dispatch failed")')
    return lines


def _value_dispatch_overload_stubs(
    members: list[JavaNode],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    containing_class_name: str,
    is_static: bool,
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
            member_python_name(member),
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


def _member_dispatch_key(
    params: list[ParameterInfo],
    guards: list[_DispatchGuard],
) -> tuple[str, ...]:
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return ("fixed", str(len(params))) + tuple(guard.key for guard in guards)
    if spread_index != len(params) - 1:
        return ("invalid",)
    return (
        ("varargs", str(spread_index))
        + tuple(guard.key for guard in guards[:spread_index])
        + (f"{guards[spread_index].key}:spread",)
    )


def _varargs_value_guards_checkable(
    params: list[ParameterInfo],
    guards: list[_DispatchGuard],
) -> bool:
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return all(guard.condition_template is not None for guard in guards)
    if len(guards) > 1 and spread_index != len(params) - 1:
        return False
    if not all(guard.condition_template is not None for guard in guards[:spread_index]):
        return False
    spread_guard = guards[spread_index]
    return spread_guard.condition_template is not None and spread_guard.specificity > 0


def _value_dispatch_branch_order_key(
    branch: tuple[JavaNode, list[ParameterInfo], list[_DispatchGuard]],
) -> tuple[int, int, int, int]:
    _, params, guards = branch
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return (0, -sum(guard.specificity for guard in guards), len(params), 0)
    return (1, -spread_index, -sum(guard.specificity for guard in guards), len(params))


def _value_dispatch_condition(guards: list[_DispatchGuard], params: list[ParameterInfo]) -> str:
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        parts = [f"len(args) == {len(guards)}"]
        for index, guard in enumerate(guards):
            if guard.condition_template is not None:
                parts.append(guard.condition_template.format(arg=f"args[{index}]"))
        return " and ".join(parts)

    parts = [f"len(args) >= {spread_index}"]
    for index in range(spread_index):
        guard = guards[index]
        if guard.condition_template is not None:
            parts.append(guard.condition_template.format(arg=f"args[{index}]"))
    spread_guard = guards[spread_index]
    if spread_guard.condition_template is not None and spread_guard.specificity > 0:
        element_check = spread_guard.condition_template.format(arg="value")
        parts.append(f"all({element_check} for value in args[{spread_index}:])")
    return " and ".join(parts)


def _value_dispatch_assignments(params: list[ParameterInfo], *, indent: str) -> list[str]:
    spread_index = next((index for index, param in enumerate(params) if param.is_spread), None)
    if spread_index is None:
        return [f"{indent}{param.py_name} = args[{index}]" for index, param in enumerate(params)]
    lines = [f"{indent}{params[index].py_name} = args[{index}]" for index in range(spread_index)]
    spread_param = params[spread_index]
    lines.append(f"{indent}{spread_param.py_name} = args[{spread_index}:]")
    return lines


def _dispatch_guard_for_parameter(param: ParameterInfo) -> _DispatchGuard | None:
    simple = _java_simple_type(param.java_type)
    if simple in {"char", "Character"}:
        return _DispatchGuard(
            "char",
            50,
            "isinstance({arg}, str) and len({arg}) == 1",
        )
    if simple in {"String", "CharSequence"}:
        return _DispatchGuard("str", 40, "isinstance({arg}, str)")

    erased = _erase_py_type(param.py_type).removeprefix("*")
    base = erased.split(".")[-1]
    if base == "bool":
        return _DispatchGuard("bool", 45, "isinstance({arg}, bool)")
    if base == "int":
        return _DispatchGuard(
            "int",
            36,
            "isinstance({arg}, int) and not isinstance({arg}, bool)",
        )
    if base == "float":
        return _DispatchGuard(
            "float",
            35,
            "isinstance({arg}, (int, float)) and not isinstance({arg}, bool)",
        )
    if base == "str":
        return _DispatchGuard("str", 40, "isinstance({arg}, str)")
    if base == "list":
        return _DispatchGuard("list", 35, "isinstance({arg}, list)")
    if base == "set":
        return _DispatchGuard("set", 35, "isinstance({arg}, set)")
    if base == "dict":
        return _DispatchGuard("dict", 35, "isinstance({arg}, dict)")
    if base == "type":
        return _DispatchGuard("type", 35, "isinstance({arg}, type)")
    if base in {"Callable", "callable"}:
        return _DispatchGuard("Callable", 35, "callable({arg})")
    if base in {"object", "Any"}:
        return _DispatchGuard("object", 0)
    return _DispatchGuard(f"opaque:{base}", 0)


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
    name_resolver: NameResolver,
    class_state: ClassTranslationState | None,
    inner_class_names_requiring_outer: set[str],
    nested_class_names: set[str],
    indent: str,
) -> list[str]:
    name_node = member.child_by_field("name")
    java_name = name_node.text if name_node is not None else ""
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
        name_resolver=name_resolver,
        allow_local_helpers=True,
        static_dispatch_methods={java_name} if java_name else set(),
        static_dispatch_class_name=containing_class_name,
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        containing_class_name=containing_class_name,
        nested_class_names=nested_class_names,
    )
    ctx.in_instance_method = False
    for param in parameter_infos(member, cfg):
        register_param(ctx, param)
    body = method_body(member)
    ctx.in_method_body = True
    body_lines = translate_body(body, ctx, indent=indent) if body else [f"{indent}pass"]
    ctx.in_method_body = False
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
    name_resolver: NameResolver,
    class_state: ClassTranslationState | None,
    inner_class_names_requiring_outer: set[str],
    nested_class_names: set[str],
    indent: str,
) -> list[str]:
    name_node = member.child_by_field("name")
    java_name = name_node.text if name_node is not None else ""
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
        name_resolver=name_resolver,
        allow_local_helpers=True,
        self_dispatch_methods={java_name} if java_name else set(),
        class_state=class_state,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer,
        containing_class_name=containing_class_name,
        nested_class_names=nested_class_names,
    )
    ctx.in_instance_method = True
    for param in parameter_infos(member, cfg):
        register_param(ctx, param)
    body = method_body(member)
    ctx.in_method_body = True
    body_lines = translate_body(body, ctx, indent=indent) if body else [f"{indent}pass"]
    ctx.in_method_body = False
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
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
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
            name_resolver=name_resolver,
            allow_local_helpers=True,
            self_dispatch_methods={java_name} if java_name and not is_static else set(),
            static_dispatch_methods={java_name} if java_name and is_static else set(),
            static_dispatch_class_name=containing_class_name if is_static else None,
            class_state=class_state,
            inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
            containing_class_name=containing_class_name,
            nested_class_names=nested_class_names or set(),
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
            ),
        )
    return lines


def _deduplicate_same_body_erased_sig(
    members: list[JavaNode],
    cfg: TranslationConfig,
) -> list[JavaNode] | None:
    """Reduce overloads that share an erased signature AND equivalent body to one member.

    When Java numeric-width variants (e.g. ``sort(int[])`` and ``sort(long[])``) map to
    the same Python erasure and have identical Java body text, only one representative is
    needed.

    Bodies that are not textually identical may still be *provably equivalent* under Python
    ``int`` semantics. The ``compare(byte/short/int/long)`` family is the motivating case:
    the narrow overloads return ``x - y`` while the wide ones return ``x < y ? -1 : 1``.
    Both honour the ``Comparator`` sign contract, and once the integral types erase to a
    single Python ``int`` the difference form cannot overflow, so the whole group collapses
    to one method. See :func:`_comparison_body_form`.

    Returns the reduced list when at least one deduplication occurs AND every same-erased-sig
    group is internally consistent (identical text or all recognised comparison forms over the
    same parameters). Returns None if deduplication is impossible or unnecessary.
    """
    erased = [_erased_overload_signature(member, cfg) for member in members]
    if len(set(erased)) == len(erased):
        return None  # already distinct — nothing to deduplicate

    # Per erased signature, the canonical body key and the index/form of the kept member.
    sig_to_key: dict[tuple[str, ...], str] = {}
    sig_to_repr_index: dict[tuple[str, ...], int] = {}
    sig_to_repr_form: dict[tuple[str, ...], str | None] = {}
    reduced: list[JavaNode] = []

    for member, sig in zip(members, erased, strict=True):
        form = _comparison_body_form(member, cfg)
        body = method_body(member)
        body_text = body.text.strip() if body is not None else ""
        # Recognised comparison bodies share one key so the diff/sign forms unify; everything
        # else falls back to exact text equality (the original behaviour).
        key = _COMPARISON_BODY_KEY if form is not None else body_text

        if sig not in sig_to_key:
            sig_to_key[sig] = key
            sig_to_repr_index[sig] = len(reduced)
            sig_to_repr_form[sig] = form
            reduced.append(member)
        elif sig_to_key[sig] == key:
            # Equivalent — drop the duplicate. For comparison groups prefer the explicit
            # sign form as the kept representative: it is value-identical to Java for the
            # wide integral overloads, while the difference form only matches the sign.
            if form == "sign" and sig_to_repr_form[sig] == "diff":
                reduced[sig_to_repr_index[sig]] = member
                sig_to_repr_form[sig] = "sign"
        else:
            return None  # same erased sig but inequivalent bodies → can't safely merge

    if len(reduced) == len(members):
        return None  # no deduplication actually happened
    return reduced


_COMPARISON_BODY_KEY = "<two-param-int-comparison>"


def _comparison_body_form(member: JavaNode, cfg: TranslationConfig) -> str | None:
    """Classify a two-argument integer comparison body, or return None.

    Recognises exactly the two shapes used by the JDK/Commons ``compare(T, T)`` contract,
    over the method's own two parameters ``(p0, p1)`` in order:

    * ``"diff"`` — ``return p0 - p1;``
    * ``"sign"`` — ``if (p0 == p1) { return 0; } return p0 < p1 ? -1 : 1;``

    Both return an ``int`` whose sign orders the two values. The match is deliberately exact
    (no near-miss normalisation) so unrelated methods that happen to share an erased signature
    are never collapsed.
    """
    type_node = member.child_by_field("type")
    if type_node is None or type_node.text.strip() != "int":
        return None
    params = parameter_infos(member, cfg)
    if len(params) != 2 or any(p.is_spread for p in params):
        return None
    p0, p1 = params[0].raw_name, params[1].raw_name
    body = method_body(member)
    if body is None or body.type != "block":
        return None
    stmts = _code_children(body)

    if len(stmts) == 1 and stmts[0].type == "return_statement":
        expr = _return_value(stmts[0])
        if _is_param_binary(expr, "-", p0, p1):
            return "diff"
        return None

    if (
        len(stmts) == 2
        and stmts[0].type == "if_statement"
        and stmts[1].type == "return_statement"
        and _is_zero_guard(stmts[0], p0, p1)
        and _is_sign_ternary(_return_value(stmts[1]), p0, p1)
    ):
        return "sign"
    return None


_COMMENT_NODE_TYPES = frozenset({"line_comment", "block_comment"})


def _code_children(node: JavaNode) -> list[JavaNode]:
    """Named children with tree-sitter comment nodes removed.

    tree-sitter-java keeps ``line_comment`` / ``block_comment`` as named children, so a
    comment inside a body or block would otherwise inflate the statement count and defeat
    the exact shape match.
    """
    return [child for child in node.named_children if child.type not in _COMMENT_NODE_TYPES]


def _unwrap_parens(node: JavaNode | None) -> JavaNode | None:
    """Strip any ``(...)`` wrappers so the inner expression can be matched directly."""
    while node is not None and node.type == "parenthesized_expression":
        children = _code_children(node)
        node = children[0] if children else None
    return node


def _return_value(return_stmt: JavaNode) -> JavaNode | None:
    children = _code_children(return_stmt)
    return children[0] if children else None


def _single_return(node: JavaNode | None) -> JavaNode | None:
    """The lone return of a consequence — a bare ``return ...;`` or a block with one."""
    if node is None:
        return None
    if node.type == "return_statement":
        return node
    if node.type == "block":
        body = _code_children(node)
        if len(body) == 1 and body[0].type == "return_statement":
            return body[0]
    return None


def _is_param_identifier(node: JavaNode | None, name: str) -> bool:
    return node is not None and node.type == "identifier" and node.text == name


def _is_param_binary(node: JavaNode | None, operator: str, left: str, right: str) -> bool:
    """True when ``node`` is ``left <operator> right`` over the two named parameters."""
    node = _unwrap_parens(node)
    if node is None or node.type != "binary_expression":
        return False
    op = node.child_by_field("operator")
    if op is None or op.text != operator:
        return False
    return _is_param_identifier(node.child_by_field("left"), left) and _is_param_identifier(
        node.child_by_field("right"), right
    )


def _is_zero_guard(if_stmt: JavaNode, p0: str, p1: str) -> bool:
    """True for ``if (p0 == p1) return 0;`` — braced or not, ``==`` symmetric, no else."""
    if if_stmt.child_by_field("alternative") is not None:
        return False
    condition = if_stmt.child_by_field("condition")
    if not (_is_param_binary(condition, "==", p0, p1) or _is_param_binary(condition, "==", p1, p0)):
        return False
    return_stmt = _single_return(if_stmt.child_by_field("consequence"))
    if return_stmt is None:
        return False
    value = _return_value(return_stmt)
    return value is not None and value.text.strip() == "0"


def _is_sign_ternary(node: JavaNode | None, p0: str, p1: str) -> bool:
    """True for ``p0 < p1 ? -1 : 1``."""
    node = _unwrap_parens(node)
    if node is None or node.type != "ternary_expression":
        return False
    if not _is_param_binary(node.child_by_field("condition"), "<", p0, p1):
        return False
    consequence = node.child_by_field("consequence")
    alternative = node.child_by_field("alternative")
    return (
        consequence is not None
        and alternative is not None
        and consequence.text.strip() == "-1"
        and alternative.text.strip() == "1"
    )

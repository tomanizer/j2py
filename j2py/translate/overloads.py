"""Overload translation helpers for class emission."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import record_annotation_diagnostics
from j2py.translate.class_members import member_python_name
from j2py.translate.class_methods import (
    _IMMUTABLE_LITERAL_NODES,
    method_body,
    parameter_infos,
    register_param,
    translate_method,
)
from j2py.translate.class_methods import (
    return_type as method_return_type,
)
from j2py.translate.class_methods import (
    signature as render_method_signature,
)
from j2py.translate.class_model import ParameterInfo, _modifiers
from j2py.translate.diagnostics import (
    ClassTranslationState,
    TranslationContext,
    TranslationDiagnostics,
)
from j2py.translate.expressions import translate_expression
from j2py.translate.name_resolution import NameResolver
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.statements import translate_body


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


@dataclass(frozen=True)
class _DispatchGuard:
    """A runtime-checkable guard for one overload parameter."""

    key: str
    specificity: int
    condition_template: str | None = None


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
    name_resolver: NameResolver,
    pre_body_lines: list[str],
    extra_params: list[ParameterInfo],
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
) -> list[str] | None:
    forwards = [
        _OverloadForward(member, parameter_infos(member, cfg), _constructor_forward_args(member))
        for member in members
    ]
    merged = _resolve_overload_defaults(
        forwards,
        cfg,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
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
    name_resolver: NameResolver,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
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

    lines = _overload_stubs(members, cfg, diagnostics)
    if is_static:
        lines.append("    @staticmethod")
    signature = render_method_signature(
        member_python_name(impl.member),
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
    implementations = [forward for forward in forwards if forward.forwarded is None]
    if len(implementations) != 1:
        return None
    impl = implementations[0]
    if not impl.params:
        return None

    for forward in forwards:
        if forward is impl:
            continue
        if forward.forwarded is None or len(forward.forwarded) != len(impl.params):
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
    name_resolver: NameResolver,
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
    nested_class_names: set[str] | None = None,
) -> list[str] | None:
    if any(member.type != "method_declaration" for member in members):
        return None
    body_texts: set[str] = set()
    for member in members:
        body = method_body(member)
        body_texts.add(body.text if body is not None else "")
    if len(body_texts) != 1:
        return None

    param_sets = [parameter_infos(member, cfg) for member in members]
    if len({len(params) for params in param_sets}) != 1:
        return None
    if len(param_sets[0]) == 0:
        return None

    raw_names = [param.raw_name for param in param_sets[0]]
    if any([param.raw_name for param in params] != raw_names for params in param_sets):
        return None

    name = member_python_name(members[0])
    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None

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

    lines = _overload_stubs(members, cfg, diagnostics)
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
    body = method_body(members[0])
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
    body = method_body(member)
    if body is None:
        return None
    children = body.named_children
    if len(children) != 1 or children[0].type != "explicit_constructor_invocation":
        return None
    invocation = children[0]
    target = invocation.named_children[0] if invocation.named_children else None
    if target is None or target.type != "this":
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
    if any(any(param.is_spread for param in params) for params in params_by_member):
        return None

    guards_by_member: list[list[_DispatchGuard]] = []
    for params in params_by_member:
        guards: list[_DispatchGuard] = []
        for param in params:
            guard = _dispatch_guard_for_parameter(param)
            if guard is None:
                return None
            guards.append(guard)
        guards_by_member.append(guards)

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
        key=lambda item: (-sum(guard.specificity for guard in item[1][2]), item[0]),
    )
    for _, (member, params, guards) in ordered:
        condition = _value_dispatch_condition(guards)
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


def _value_dispatch_condition(guards: list[_DispatchGuard]) -> str:
    parts = [f"len(args) == {len(guards)}"]
    for index, guard in enumerate(guards):
        if guard.condition_template is not None:
            parts.append(guard.condition_template.format(arg=f"args[{index}]"))
    return " and ".join(parts)


def _value_dispatch_assignments(params: list[ParameterInfo], *, indent: str) -> list[str]:
    return [f"{indent}{param.py_name} = args[{index}]" for index, param in enumerate(params)]


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


def _java_simple_type(java_type: str) -> str:
    base = java_type.strip()
    while base.startswith("@"):
        _, _, base = base.partition(" ")
        base = base.strip()
    base = base.split("<", 1)[0].strip()
    while base.endswith("[]"):
        base = base[:-2].strip()
    return base.rsplit(".", 1)[-1]


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


def _erased_overload_signature(member: JavaNode, cfg: TranslationConfig) -> tuple[str, ...]:
    return tuple(
        ("*" if param.is_spread else "") + _erase_py_type(param.py_type)
        for param in parameter_infos(member, cfg)
    )


def _erase_py_type(py_type: str) -> str:
    """Reduce a Python annotation to the part isinstance dispatch can see."""
    text = py_type.strip()
    prefix = ""
    if text.startswith("*"):
        prefix, text = "*", text[1:].strip()
    parts = _split_top_level_union(text)
    if len(parts) > 1:
        return prefix + " | ".join(sorted({_erase_py_type(part) for part in parts}))
    base = text.split("[", 1)[0].strip()
    if base in {"Callable", "typing.Callable", "collections.abc.Callable"}:
        base = "Callable"
    return prefix + base


def _split_top_level_union(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "|" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _union_types(types: Iterable[str]) -> str:
    unique: list[str] = []
    for py_type in types:
        if py_type not in unique:
            unique.append(py_type)
    return " | ".join(unique)


def _readable_signature(member: JavaNode, cfg: TranslationConfig) -> str:
    params = ", ".join(
        f"{'*' if param.is_spread else ''}{param.py_name}: {param.py_type}"
        for param in parameter_infos(member, cfg)
    )
    return f"{member_python_name(member)}({params})"


def _has_this_delegation(member: JavaNode) -> bool:
    body = method_body(member)
    if body is None:
        return False
    for invocation in body.find_all("explicit_constructor_invocation"):
        target = invocation.named_children[0] if invocation.named_children else None
        if target is not None and target.type == "this":
            return True
    return False


def _overload_stubs(
    members: list[JavaNode],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.imports.need_typing("overload")
    lines: list[str] = []
    for member in members:
        is_static = "static" in _modifiers(member)
        if is_static:
            lines.append("    @staticmethod")
        lines.append("    @overload")
        params = parameter_infos(member, cfg)
        return_type = (
            "None" if member.type == "constructor_declaration" else method_return_type(member, cfg)
        )
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(return_type)
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

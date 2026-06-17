"""Interface (Protocol) declaration emission for class translation."""

from __future__ import annotations

import re
from dataclasses import dataclass

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
    node_key,
    sealed_type_alias_lines,
    type_metadata_comment_lines,
)
from j2py.translate.class_methods import (
    class_method_return_types,
    method_body,
    parameter_infos,
    register_param,
    return_type,
    signature,
    translate_method,
)
from j2py.translate.class_model import TYPE_DECLARATION_NODES, ParameterInfo, _modifiers
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.framework_dispatch import resolve_class, resolve_method
from j2py.translate.name_resolution import NameResolver
from j2py.translate.rules.naming import translate_class_name
from j2py.translate.rules.types import _map_type_vars, translate_type
from j2py.translate.statements import translate_body

_NodeKey = tuple[int, int, int, int, str]
_BUILTIN_BOUND_TYPES = frozenset(
    {
        "Any",
        "bool",
        "bytes",
        "float",
        "int",
        "object",
        "str",
        "type",
    },
)


@dataclass(frozen=True)
class InterfaceTypeVarPlan:
    declaration_lines: list[str]
    interface_type_var_maps: dict[_NodeKey, dict[str, str]]


@dataclass(frozen=True)
class TypeParameter:
    name: str
    bound: str | None


def interface_type_var_plan(
    root: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> InterfaceTypeVarPlan:
    """Return module-level TypeVars and per-interface generic name mappings."""
    declarations: dict[str, tuple[str, str | None]] = {}
    interface_type_var_maps: dict[_NodeKey, dict[str, str]] = {}
    interface_occurrences: dict[str, list[tuple[JavaNode, str, str]]] = {}
    declared_type_names = _declared_type_names(root)
    methods = _method_declarations(root)

    for interface in _interface_declarations(root):
        class_name = _interface_class_name(interface)
        variances = _interface_type_param_variances(interface, cfg)
        for type_param in _type_parameter_names(interface):
            interface_occurrences.setdefault(type_param, []).append(
                (interface, class_name, variances.get(type_param, "covariant")),
            )

    method_type_params = {
        type_param.name for method in methods for type_param in _type_parameters(method, cfg)
    }

    conflicting_names = {
        name
        for name, occurrences in interface_occurrences.items()
        if len(
            {variance for _, _, variance in occurrences}
            | _method_variance(name, method_type_params)
        )
        > 1
    }
    used_symbols = set(method_type_params) | {
        name for name in interface_occurrences if name not in conflicting_names
    }

    for name, occurrences in interface_occurrences.items():
        for interface, class_name, variance in occurrences:
            type_var_map = interface_type_var_maps.setdefault(node_key(interface), {})
            if name in conflicting_names:
                symbol = _unique_type_var_symbol(class_name, name, used_symbols)
                type_var_map[name] = symbol
                _register_type_var(declarations, symbol, variance)
            else:
                type_var_map[name] = name
                _register_type_var(declarations, name, variance)

    for method in methods:
        for method_type_param in _type_parameters(method, cfg):
            _register_type_var(
                declarations,
                method_type_param.name,
                "invariant",
                bound=method_type_param.bound,
            )

    if declarations:
        diagnostics.imports.need_typing("TypeVar")
    protocol_lines = _bound_protocol_lines(declarations, declared_type_names, diagnostics)
    return InterfaceTypeVarPlan(
        declaration_lines=[
            *protocol_lines,
            *(
                _type_var_declaration_line(name, variance, bound=bound)
                for name, (variance, bound) in declarations.items()
            ),
        ],
        interface_type_var_maps=interface_type_var_maps,
    )


def translate_interface(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    docstring_lines: list[str] | None = None,
    interface_type_var_maps: dict[_NodeKey, dict[str, str]] | None = None,
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
    interface_type_params = _type_parameter_names(node)
    type_var_map = (interface_type_var_maps or {}).get(node_key(node), {})
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
        interface_type_var_maps=interface_type_var_maps,
    )
    sealed_alias_lines = sealed_type_alias_lines(node, body, class_name, indent="    ")

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
    protocol_type_params = [
        _map_type_vars(type_param, type_var_map) for type_param in interface_type_params
    ]
    protocol_base = (
        f"Protocol[{', '.join(protocol_type_params)}]" if protocol_type_params else "Protocol"
    )
    bases = [*class_transform.base_classes, protocol_base]
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
        method_type_var_map = _method_type_var_map(method, type_var_map)
        method_body_node = method_body(method)
        if method_body_node is not None:
            reason = (
                "translated interface static method"
                if "static" in _modifiers(method)
                else "translated interface default method"
            )
            adapter_lines = None
            if "static" in _modifiers(method):
                adapter_lines = _static_interface_factory_adapter_lines(
                    method,
                    methods=methods,
                    cfg=cfg,
                    diagnostics=diagnostics,
                    class_name=class_name,
                    interface_type_params=interface_type_params,
                    class_method_names=class_method_names,
                    class_static_method_names=class_static_method_names,
                    method_return_types=method_return_types,
                    static_field_aliases=static_field_aliases,
                    static_method_imports=static_method_imports,
                    name_resolver=name_resolver,
                )
            if adapter_lines is not None:
                diagnostics.record(
                    method,
                    supported=True,
                    reason="translated interface static factory adapter",
                )
                lines.extend(adapter_lines)
                wrote_member = True
                continue
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
            lines.extend(
                translate_method(
                    method,
                    ctx,
                    supported_reason=reason,
                    type_var_map=method_type_var_map,
                ),
            )
            wrote_member = True
            continue

        diagnostics.record(method, supported=True, reason="translated abstract interface method")
        py_name = member_python_name(method)
        raw_name_node = method.child_by_field("name")
        raw_name = raw_name_node.text if raw_name_node is not None else py_name
        method_transform = resolve_method(
            method,
            cfg,
            diagnostics,
            java_name=raw_name,
            py_name=py_name,
            indent="    ",
        )
        if not method_transform.handled:
            record_annotation_diagnostics(
                method,
                cfg,
                diagnostics,
                target_kind="method",
                target_name=py_name,
            )
            lines.extend(annotation_comment_lines(method, cfg, indent="    "))
        lines.extend(method_transform.prefix_lines)
        params = [
            _map_parameter_type(param, method_type_var_map)
            for param in parameter_infos(method, cfg)
        ]
        method_return_type = _map_type_vars(return_type(method, cfg), method_type_var_map)
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


def _static_interface_factory_adapter_lines(
    method: JavaNode,
    *,
    methods: list[JavaNode],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_name: str,
    interface_type_params: list[str],
    class_method_names: set[str],
    class_static_method_names: set[str],
    method_return_types: dict[str, str],
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
) -> list[str] | None:
    method_return_type = return_type(method, cfg)
    if _type_base(method_return_type) != class_name:
        return None
    lambda_node = _returned_lambda(method)
    if lambda_node is None:
        return None
    abstract_methods = [
        candidate
        for candidate in methods
        if "static" not in _modifiers(candidate) and method_body(candidate) is None
    ]
    if len(abstract_methods) != 1:
        return None

    type_var_map = _interface_type_var_map(
        interface_type_params,
        method_return_type,
        class_name=class_name,
    )
    raw_method_name_node = method.child_by_field("name")
    raw_method_name = raw_method_name_node.text if raw_method_name_node is not None else "Factory"
    py_method_name = member_python_name(method)
    adapter_class_name = f"_{_adapter_name_part(raw_method_name)}{class_name}Adapter"

    params = parameter_infos(method, cfg)
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(method_return_type)
        for param in params:
            diagnostics.imports.need_type_annotation(param.py_type)
    diagnostics.imports.need_typing("cast")

    lines: list[str] = []
    method_transform = resolve_method(
        method,
        cfg,
        diagnostics,
        java_name=raw_method_name,
        py_name=py_method_name,
        indent="    ",
    )
    if not method_transform.handled:
        record_annotation_diagnostics(
            method,
            cfg,
            diagnostics,
            target_kind="method",
            target_name=py_method_name,
        )
        lines.extend(annotation_comment_lines(method, cfg, indent="    "))
    lines.extend(method_transform.prefix_lines)
    lines.append("    @staticmethod")
    lines.append(
        "    "
        + signature(
            member_python_name(method),
            params,
            return_type=method_return_type,
            include_self=False,
            emit_type_hints=cfg.emit_type_hints,
        )
        + ":",
    )
    lines.append(f"        class {adapter_class_name}:")

    adapter_methods: list[list[str]] = []
    abstract_method = abstract_methods[0]
    adapter_methods.append(
        _adapter_method_lines(
            abstract_method,
            cfg=cfg,
            diagnostics=diagnostics,
            class_name=class_name,
            class_method_names=class_method_names,
            class_static_method_names=class_static_method_names,
            method_return_types=method_return_types,
            static_field_aliases=static_field_aliases,
            static_method_imports=static_method_imports,
            name_resolver=name_resolver,
            type_var_map=type_var_map,
            lambda_node=lambda_node,
            indent="            ",
        ),
    )
    for default_method in methods:
        if (
            default_method is abstract_method
            or "static" in _modifiers(default_method)
            or method_body(default_method) is None
        ):
            continue
        adapter_methods.append(
            _adapter_method_lines(
                default_method,
                cfg=cfg,
                diagnostics=diagnostics,
                class_name=class_name,
                class_method_names=class_method_names,
                class_static_method_names=class_static_method_names,
                method_return_types=method_return_types,
                static_field_aliases=static_field_aliases,
                static_method_imports=static_method_imports,
                name_resolver=name_resolver,
                type_var_map=type_var_map,
                lambda_node=None,
                indent="            ",
            ),
        )

    for index, method_lines in enumerate(adapter_methods):
        if index:
            lines.append("")
        lines.extend(method_lines)
    return_line = f"        return cast({method_return_type}, {adapter_class_name}())"
    if len(return_line) <= 88:
        lines.append(return_line)
    else:
        lines.extend(
            [
                "        return cast(",
                f"            {method_return_type},",
                f"            {adapter_class_name}(),",
                "        )",
            ],
        )
    return lines


def _adapter_method_lines(
    method: JavaNode,
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_name: str,
    class_method_names: set[str],
    class_static_method_names: set[str],
    method_return_types: dict[str, str],
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    type_var_map: dict[str, str],
    lambda_node: JavaNode | None,
    indent: str,
) -> list[str]:
    params = [_map_parameter_type(param, type_var_map) for param in parameter_infos(method, cfg)]
    method_return_type = _map_type_vars(return_type(method, cfg), type_var_map)
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(method_return_type)
        for param in params:
            diagnostics.imports.need_type_annotation(param.py_type)
    lines = [
        f"{indent}"
        + signature(
            member_python_name(method),
            params,
            return_type=method_return_type,
            include_self=True,
            emit_type_hints=cfg.emit_type_hints,
        )
        + ":",
    ]
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
    ctx.in_instance_method = True
    for param in params:
        register_param(ctx, param)

    body = method_body(method)
    if lambda_node is not None:
        lambda_param_names = _lambda_param_names(lambda_node)
        for raw_name, param in zip(lambda_param_names, params, strict=False):
            ctx.expression_aliases[raw_name] = param.py_name
        body = _lambda_body(lambda_node)
    body_lines = (
        translate_body(body, ctx, indent=indent + "    ") if body else [indent + "    pass"]
    )
    if ctx.pending_local_helpers:
        for helper in ctx.pending_local_helpers:
            lines.append("")
            lines.extend(helper)
    lines.extend(body_lines)
    return lines


def _type_parameter_names(node: JavaNode) -> list[str]:
    return [type_param.name for type_param in _type_parameters(node, None)]


def _type_parameters(node: JavaNode, cfg: TranslationConfig | None) -> list[TypeParameter]:
    type_parameters = next(
        (child for child in node.named_children if child.type == "type_parameters"),
        None,
    )
    if type_parameters is None:
        return []
    params: list[TypeParameter] = []
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
        if name_node is None:
            continue
        bound = _type_parameter_bound(child, cfg)
        params.append(TypeParameter(name=name_node.text, bound=bound))
    return params


def _type_parameter_bound(node: JavaNode, cfg: TranslationConfig | None) -> str | None:
    if cfg is None:
        return None
    bound_node = next(
        (child for child in node.named_children if child.type == "type_bound"),
        None,
    )
    if bound_node is None:
        return None
    bounds = [
        child
        for child in bound_node.named_children
        if child.type
        in {
            "array_type",
            "generic_type",
            "scoped_type_identifier",
            "type_identifier",
        }
    ]
    if not bounds:
        return None
    bound = translate_type(bounds[0].text, cfg)
    if not re.fullmatch(r"[A-Za-z_]\w*", bound):
        return None
    return bound


def _declared_type_names(root: JavaNode) -> set[str]:
    names: set[str] = set()
    for node in root.walk():
        if node.type not in TYPE_DECLARATION_NODES:
            continue
        name_node = node.child_by_field("name")
        if name_node is not None:
            names.add(translate_class_name(name_node.text))
    return names


def _interface_declarations(root: JavaNode) -> list[JavaNode]:
    declarations: list[JavaNode] = []
    if root.type == "interface_declaration":
        declarations.append(root)
    declarations.extend(root.find_all("interface_declaration"))
    return declarations


def _interface_methods(node: JavaNode) -> list[JavaNode]:
    body = node.child_by_field("body")
    if body is None:
        return []
    return [child for child in body.named_children if child.type == "method_declaration"]


def _method_declarations(root: JavaNode) -> list[JavaNode]:
    methods = []
    if root.type == "method_declaration":
        methods.append(root)
    methods.extend(root.find_all("method_declaration"))
    return methods


def _interface_class_name(node: JavaNode) -> str:
    name_node = node.child_by_field("name")
    return translate_class_name(name_node.text if name_node is not None else "Unknown")


def _interface_type_param_variances(
    node: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, str]:
    type_params = _type_parameter_names(node)
    usages: dict[str, set[str]] = {type_param: set() for type_param in type_params}
    if not usages:
        return {}

    for method in _interface_methods(node):
        if "static" in _modifiers(method):
            continue
        method_usages = {
            name: positions
            for name, positions in usages.items()
            if name not in set(_type_parameter_names(method))
        }
        _record_type_var_usages(return_type(method, cfg), method_usages, position="return")
        for param in parameter_infos(method, cfg):
            _record_type_var_usages(param.py_type, method_usages, position="parameter")

    return {name: _variance_for_usages(usages[name]) for name in type_params}


def _record_type_var_usages(
    py_type: str,
    usages: dict[str, set[str]],
    *,
    position: str,
) -> None:
    stripped = py_type.strip()
    for type_param in usages:
        if not re.search(rf"\b{re.escape(type_param)}\b", stripped):
            continue
        if stripped == type_param or _is_optional_type_var(stripped, type_param):
            usages[type_param].add(position)
        else:
            usages[type_param].add("invariant")


def _variance_for_usages(usages: set[str]) -> str:
    if not usages:
        return "covariant"
    if "invariant" in usages or len(usages) != 1:
        return "invariant"
    if "return" in usages:
        return "covariant"
    if "parameter" in usages:
        return "contravariant"
    return "invariant"


def _is_optional_type_var(py_type: str, type_param: str) -> bool:
    parts = _split_python_union(py_type)
    if len(parts) != 2 or "None" not in parts:
        return False
    return next(part for part in parts if part != "None") == type_param


def _split_python_union(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        if char == "|" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _register_type_var(
    declarations: dict[str, tuple[str, str | None]],
    name: str,
    variance: str,
    *,
    bound: str | None = None,
) -> None:
    existing = declarations.get(name)
    if existing is None:
        declarations[name] = (variance, bound)
        return

    existing_variance, existing_bound = existing
    resolved_variance = variance if existing_variance == variance else "invariant"
    if existing_bound is None:
        resolved_bound = bound
    elif bound is None:
        resolved_bound = existing_bound
    else:
        resolved_bound = existing_bound if existing_bound == bound else None
    declarations[name] = (resolved_variance, resolved_bound)


def _method_variance(name: str, method_type_params: set[str]) -> set[str]:
    return {"invariant"} if name in method_type_params else set()


def _method_type_var_map(method: JavaNode, type_var_map: dict[str, str]) -> dict[str, str]:
    method_type_params = set(_type_parameter_names(method))
    if not method_type_params:
        return type_var_map
    return {
        source: target
        for source, target in type_var_map.items()
        if source not in method_type_params
    }


def _unique_type_var_symbol(
    class_name: str,
    type_param: str,
    used_symbols: set[str],
) -> str:
    base = f"{class_name}{type_param}"
    candidate = base
    index = 2
    while candidate in used_symbols:
        candidate = f"{base}{index}"
        index += 1
    used_symbols.add(candidate)
    return candidate


def _type_var_declaration_line(name: str, variance: str, *, bound: str | None = None) -> str:
    options: list[str] = []
    if bound is not None:
        options.append(f"bound={bound}")
    if variance == "covariant":
        options.append("covariant=True")
    elif variance == "contravariant":
        options.append("contravariant=True")
    if options:
        return f'{name} = TypeVar("{name}", {", ".join(options)})'
    return f'{name} = TypeVar("{name}")'


def _bound_protocol_lines(
    declarations: dict[str, tuple[str, str | None]],
    declared_type_names: set[str],
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    custom_bounds = [
        bound
        for _, bound in declarations.values()
        if bound is not None
        and bound not in _BUILTIN_BOUND_TYPES
        and bound not in declared_type_names
    ]
    unique_bounds = list(dict.fromkeys(custom_bounds))
    if not unique_bounds:
        return []

    diagnostics.imports.need_typing("Protocol")
    lines: list[str] = []
    for index, bound in enumerate(unique_bounds):
        if index:
            lines.append("")
        lines.append(f"class {bound}(Protocol):")
        lines.append("    pass")
    if lines:
        lines.append("")
    return lines


def _returned_lambda(method: JavaNode) -> JavaNode | None:
    body = method_body(method)
    if body is None:
        return None
    statements = body.named_children
    if len(statements) != 1 or statements[0].type != "return_statement":
        return None
    return next(
        (child for child in statements[0].named_children if child.type == "lambda_expression"),
        None,
    )


def _lambda_param_names(lambda_node: JavaNode) -> list[str]:
    first = lambda_node.named_children[0] if lambda_node.named_children else None
    if first is None:
        return []
    if first.type == "identifier":
        return [first.text]
    return [
        child.text
        for child in first.named_children
        if child.type in {"identifier", "type_identifier"}
    ]


def _lambda_body(lambda_node: JavaNode) -> JavaNode | None:
    return next((child for child in lambda_node.named_children if child.type == "block"), None)


def _interface_type_var_map(
    interface_type_params: list[str],
    method_return_type: str,
    *,
    class_name: str,
) -> dict[str, str]:
    if not interface_type_params:
        return {}
    prefix = f"{class_name}["
    if not method_return_type.startswith(prefix) or not method_return_type.endswith("]"):
        return {}
    args = _split_python_type_args(method_return_type[len(prefix) : -1])
    if len(args) != len(interface_type_params):
        return {}
    return dict(zip(interface_type_params, args, strict=True))


def _split_python_type_args(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _type_base(py_type: str) -> str:
    return py_type.split("[", 1)[0].strip()


def _adapter_name_part(raw_method_name: str) -> str:
    if not raw_method_name:
        return "Factory"
    return translate_class_name(raw_method_name[:1].upper() + raw_method_name[1:])


def _map_parameter_type(param: ParameterInfo, type_var_map: dict[str, str]) -> ParameterInfo:
    return ParameterInfo(
        raw_name=param.raw_name,
        py_name=param.py_name,
        py_type=_map_type_vars(param.py_type, type_var_map),
        java_type=param.java_type,
        is_spread=param.is_spread,
    )

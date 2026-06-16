"""Interface (Protocol) declaration emission for class translation."""

from __future__ import annotations

import re

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
from j2py.translate.class_model import ParameterInfo, _modifiers
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.framework_annotations import (
    class_annotation_mapping,
    method_annotation_decorator_lines,
)
from j2py.translate.name_resolution import NameResolver
from j2py.translate.rules.naming import translate_class_name
from j2py.translate.statements import translate_body


def interface_conflicted_type_var_names(root: JavaNode, cfg: TranslationConfig) -> frozenset[str]:
    """Return Java type parameter names whose required variance conflicts across interfaces."""
    by_name: dict[str, set[str]] = {}
    for interface in _interface_declarations(root):
        variances = _interface_type_param_variances(interface, cfg)
        for type_param in _type_parameter_names(interface):
            by_name.setdefault(type_param, set()).add(variances.get(type_param, "invariant"))
        for method in _interface_methods(interface):
            for type_param in _type_parameter_names(method):
                by_name.setdefault(type_param, set()).add("invariant")
    return frozenset(name for name, vs in by_name.items() if len(vs) > 1)


def _type_var_py_name(java_name: str, variance: str, conflicted: frozenset[str]) -> str:
    """Return the Python TypeVar name, adding a variance suffix when the name is conflicted."""
    if java_name not in conflicted:
        return java_name
    if variance == "covariant":
        return f"{java_name}_co"
    if variance == "contravariant":
        return f"{java_name}_contra"
    return java_name


def interface_type_var_declaration_lines(
    root: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    """Return module-level TypeVar declarations needed by translated interfaces."""
    conflicted = interface_conflicted_type_var_names(root, cfg)
    declarations: dict[str, str] = {}
    for interface in _interface_declarations(root):
        variances = _interface_type_param_variances(interface, cfg)
        for type_param in _type_parameter_names(interface):
            variance = variances.get(type_param, "invariant")
            py_name = _type_var_py_name(type_param, variance, conflicted)
            declarations.setdefault(py_name, variance)
        for method in _interface_methods(interface):
            for type_param in _type_parameter_names(method):
                py_name = _type_var_py_name(type_param, "invariant", conflicted)
                declarations.setdefault(py_name, "invariant")

    if declarations:
        diagnostics.imports.need_typing("TypeVar")
    return [_type_var_declaration_line(name, variance) for name, variance in declarations.items()]


def translate_interface(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    docstring_lines: list[str] | None = None,
    conflicted_type_vars: frozenset[str] | None = None,
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
    conflicted = conflicted_type_vars or frozenset()
    if interface_type_params and conflicted:
        own_variances = _interface_type_param_variances(node, cfg)
        _typevar_rename: dict[str, str] = {
            p: _type_var_py_name(p, own_variances.get(p, "invariant"), conflicted)
            for p in interface_type_params
        }
    else:
        _typevar_rename = {}
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
    )
    sealed_alias_lines = sealed_type_alias_lines(node, body, class_name, indent="    ")

    record_annotation_diagnostics(
        node,
        cfg,
        diagnostics,
        target_kind="class",
        target_name=class_name,
    )
    class_mapping = class_annotation_mapping(node, cfg, diagnostics)
    lines: list[str] = []
    lines.extend(annotation_comment_lines(node, cfg))
    lines.extend(class_mapping.decorators)
    py_type_params = [_typevar_rename.get(p, p) for p in interface_type_params]
    protocol_base = f"Protocol[{', '.join(py_type_params)}]" if py_type_params else "Protocol"
    bases = [*class_mapping.bases, protocol_base]
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
            lines.extend(translate_method(method, ctx, supported_reason=reason))
            wrote_member = True
            continue

        diagnostics.record(method, supported=True, reason="translated abstract interface method")
        py_name = member_python_name(method)
        record_annotation_diagnostics(
            method,
            cfg,
            diagnostics,
            target_kind="method",
            target_name=py_name,
        )
        lines.extend(annotation_comment_lines(method, cfg, indent="    "))
        lines.extend(method_annotation_decorator_lines(method, cfg, diagnostics, indent="    "))
        params = parameter_infos(method, cfg)
        method_return_type = return_type(method, cfg)
        if _typevar_rename:
            params = [_map_parameter_type(p, _typevar_rename) for p in params]
            method_return_type = _map_type_vars(method_return_type, _typevar_rename)
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
    adapter_class_name = f"_{_adapter_name_part(raw_method_name)}{class_name}Adapter"

    params = parameter_infos(method, cfg)
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(method_return_type)
        for param in params:
            diagnostics.imports.need_type_annotation(param.py_type)
    diagnostics.imports.need_typing("cast")

    lines: list[str] = []
    lines.extend(annotation_comment_lines(method, cfg, indent="    "))
    lines.extend(method_annotation_decorator_lines(method, cfg, diagnostics, indent="    "))
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
    type_parameters = next(
        (child for child in node.named_children if child.type == "type_parameters"),
        None,
    )
    if type_parameters is None:
        return []
    names: list[str] = []
    for child in type_parameters.named_children:
        if child.type != "type_parameter":
            continue
        name = child.text.split(" ", 1)[0].strip()
        if name:
            names.append(name)
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
        _record_type_var_usages(return_type(method, cfg), usages, position="return")
        for param in parameter_infos(method, cfg):
            _record_type_var_usages(param.py_type, usages, position="parameter")

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
        if stripped == type_param:
            usages[type_param].add(position)
        else:
            usages[type_param].add("invariant")


def _variance_for_usages(usages: set[str]) -> str:
    if "invariant" in usages or len(usages) != 1:
        return "invariant"
    if "return" in usages:
        return "covariant"
    if "parameter" in usages:
        return "contravariant"
    return "invariant"


def _register_type_var(
    declarations: dict[str, str],
    name: str,
    variance: str,
) -> None:
    existing = declarations.get(name)
    if existing is None:
        declarations[name] = variance
    elif existing != variance:
        declarations[name] = "invariant"


def _type_var_declaration_line(name: str, variance: str) -> str:
    if variance == "covariant":
        return f'{name} = TypeVar("{name}", covariant=True)'
    if variance == "contravariant":
        return f'{name} = TypeVar("{name}", contravariant=True)'
    return f'{name} = TypeVar("{name}")'


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


def _map_type_vars(py_type: str, type_var_map: dict[str, str]) -> str:
    result = py_type
    for source, target in type_var_map.items():
        result = re.sub(rf"\b{re.escape(source)}\b", target, result)
    return result

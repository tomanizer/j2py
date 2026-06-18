"""Method and constructor emission for class translation."""

from __future__ import annotations

from collections.abc import Iterable

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import (
    annotation_comment_lines,
    record_annotation_diagnostics,
)
from j2py.translate.class_members import raw_member_name
from j2py.translate.class_model import TYPE_DECLARATION_NODES, ParameterInfo, _modifiers
from j2py.translate.comments import is_comment
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.framework_annotations import parameter_annotation_metadata
from j2py.translate.framework_dispatch import resolve_method
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_field_name, translate_method_name
from j2py.translate.rules.types import _map_type_vars, translate_type
from j2py.translate.statements import translate_body

# Java literal node types that are safe as Python default parameter values.
# Anything else (constructor calls, collection literals, ...) must become a
# None sentinel so the default is not shared across calls.
_IMMUTABLE_LITERAL_NODES = {
    "decimal_integer_literal",
    "hex_integer_literal",
    "octal_integer_literal",
    "binary_integer_literal",
    "decimal_floating_point_literal",
    "string_literal",
    "character_literal",
    "true",
    "false",
    "null_literal",
}

_PARAMETER_TYPE_NODE_TYPES = {
    "array_type",
    "boolean_type",
    "floating_point_type",
    "generic_type",
    "integral_type",
    "scoped_type_identifier",
    "type_identifier",
}


def class_method_return_types(
    members: Iterable[JavaNode],
    cfg: TranslationConfig,
) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for member in members:
        if member.type != "method_declaration":
            continue
        raw_name = raw_member_name(member)
        if raw_name == "__init__":
            continue
        grouped.setdefault(raw_name, []).append(return_type(member, cfg))
    result: dict[str, str] = {}
    for name, return_types in grouped.items():
        unique = list(dict.fromkeys(return_types))
        result[name] = unique[0] if len(unique) == 1 else " | ".join(unique)
    return result


def collect_declared_type_method_return_types(
    class_node: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    """Map each declared type to its Java method return types."""
    by_type: dict[str, dict[str, str]] = {}

    def add_type(type_node: JavaNode) -> None:
        name_node = type_node.child_by_field("name")
        if name_node is None:
            return
        body = type_node.child_by_field("body")
        members = (
            []
            if body is None
            else [
                child
                for child in body.named_children
                if child.type in {"constructor_declaration", "method_declaration"}
            ]
        )
        by_type[name_node.text] = class_method_return_types(members, cfg)
        if body is None:
            return
        for child in body.named_children:
            if child.type in TYPE_DECLARATION_NODES:
                add_type(child)

    add_type(class_node)
    return by_type


def translate_method(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    unsupported_reason: str | None = None,
    pre_body_lines: list[str] | None = None,
    decorator_lines: list[str] | None = None,
    extra_params: list[ParameterInfo] | None = None,
    def_line_suffix: str = "",
    supported_reason: str | None = None,
    docstring_lines: list[str] | None = None,
    python_name_override: str | None = None,
    type_var_map: dict[str, str] | None = None,
) -> list[str]:
    name_node = node.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = (
        python_name_override
        if python_name_override is not None
        else (
            "__init__"
            if node.type == "constructor_declaration"
            else translate_method_name(raw_name, snake_case=ctx.cfg.snake_case_methods)
        )
    )
    target_kind = "constructor" if node.type == "constructor_declaration" else "method"
    method_transform = resolve_method(
        node,
        ctx.cfg,
        ctx.diagnostics,
        java_name=raw_name,
        py_name=py_name,
        indent="    ",
    )
    if not method_transform.handled:
        record_annotation_diagnostics(
            node,
            ctx.cfg,
            ctx.diagnostics,
            target_kind=target_kind,
            target_name=py_name,
        )
    supported = node.type in {"constructor_declaration", "method_declaration"}
    ctx.diagnostics.record(
        node,
        supported=supported and unsupported_reason is None,
        reason=unsupported_reason or supported_reason or "translated method declaration",
    )

    is_constructor = node.type == "constructor_declaration"
    modifiers = _modifiers(node)
    is_static = "static" in modifiers
    is_abstract = "abstract" in modifiers
    previous_in_instance_method = ctx.in_instance_method
    previous_in_method = ctx.in_method
    previous_in_method_body = ctx.in_method_body
    previous_body_local_imports = set(ctx.body_local_imports)
    ctx.in_instance_method = not is_static
    ctx.in_method = True
    try:
        method_return_type = "None" if is_constructor else return_type(node, ctx.cfg)
        if type_var_map:
            method_return_type = _map_type_vars(method_return_type, type_var_map)
        if ctx.cfg.emit_type_hints:
            ctx.diagnostics.imports.need_type_annotation(method_return_type)
        params = params_for_method(node, ctx, type_var_map=type_var_map)
        injected_params = _render_extra_params(ctx, extra_params or [])
        params = injected_params + params
        if not is_static:
            params.insert(0, "self")

        if unsupported_reason is not None:
            return [f"    # TODO(j2py): {unsupported_reason}", "    pass"]

        lines: list[str] = []
        if not method_transform.handled:
            lines.extend(annotation_comment_lines(node, ctx.cfg, indent="    "))
        lines.extend(method_transform.prefix_lines)
        if is_static:
            lines.append("    @staticmethod")
        lines.extend(decorator_lines or [])
        if is_abstract:
            ctx.diagnostics.imports.need_abc()
            lines.append("    @abstractmethod")
        returns = f" -> {method_return_type}" if ctx.cfg.emit_type_hints else ""
        lines.append(f"    def {py_name}({', '.join(params)}){returns}:{def_line_suffix}")

        if is_abstract:
            if docstring_lines:
                lines.extend(docstring_lines)
            lines.append("        ...")
            return lines

        body = node.child_by_field("body")
        if body is None:
            body = first_child_by_type(node, "block", "constructor_body")

        ctx.allow_local_helpers = True
        ctx.body_local_imports.clear()
        ctx.in_method_body = True
        body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
        ctx.in_method_body = False
        local_import_lines = sorted(ctx.body_local_imports)
        ctx.body_local_imports.clear()

        if docstring_lines:
            lines.extend(docstring_lines)
            if local_import_lines or pre_body_lines or body_lines != ["        pass"]:
                lines.append("")

        if local_import_lines:
            for imp in local_import_lines:
                lines.append(f"        {imp}")
            lines.append("")

        lines.extend(pre_body_lines or [])

        if ctx.pending_local_helpers:
            for helper in ctx.pending_local_helpers:
                lines.append("")
                lines.extend(helper)

        lines.extend(body_lines)
        return lines
    finally:
        ctx.in_instance_method = previous_in_instance_method
        ctx.in_method = previous_in_method
        ctx.in_method_body = previous_in_method_body
        ctx.body_local_imports = previous_body_local_imports


def signature(
    name: str,
    params: list[ParameterInfo],
    *,
    return_type: str,
    include_self: bool,
    defaults: dict[str, str] | None = None,
    emit_type_hints: bool = True,
) -> str:
    defaults = defaults or {}
    rendered = ["self"] if include_self else []
    for param in params:
        prefix = "*" if param.is_spread else ""
        text = (
            f"{prefix}{param.py_name}: {param.py_type}"
            if emit_type_hints
            else f"{prefix}{param.py_name}"
        )
        if param.py_name in defaults and not param.is_spread:
            text += f" = {defaults[param.py_name]}"
        rendered.append(text)
    returns = f" -> {return_type}" if emit_type_hints else ""
    return f"def {name}({', '.join(rendered)}){returns}"


def method_body(node: JavaNode) -> JavaNode | None:
    return node.child_by_field("body") or first_child_by_type(node, "block", "constructor_body")


def return_type(node: JavaNode, cfg: TranslationConfig) -> str:
    type_node = node.child_by_field("type")
    if type_node is None:
        return "None"
    return translate_type(type_node.text, cfg)


def parameter_infos(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics | None = None,
) -> list[ParameterInfo]:
    params_node = node.child_by_field("parameters")
    if params_node is None:
        return []

    infos: list[ParameterInfo] = []
    for param in params_node.named_children:
        if param.type == "ERROR":
            recovered = _recover_error_parameter_info(param, cfg)
            if recovered is not None:
                infos.append(recovered)
            continue
        if param.type not in {"formal_parameter", "spread_parameter"}:
            continue
        is_spread = param.type == "spread_parameter"
        type_node = param.child_by_field("type")
        name_node = param.child_by_field("name")
        if is_spread:
            declarator = first_child_by_type(param, "variable_declarator")
            if declarator is not None:
                name_node = declarator.child_by_field("name") or name_node
            if type_node is None:
                type_node = next(
                    (
                        child
                        for child in param.named_children
                        if child.type not in {"variable_declarator", "modifiers"}
                        and not is_comment(child)
                    ),
                    None,
                )
        raw_name = name_node.text if name_node is not None else "_"
        java_type = type_node.text if type_node is not None else "Object"
        py_type = translate_type(java_type, cfg)
        py_annotations = (
            tuple(parameter_annotation_metadata(param, cfg, diagnostics))
            if diagnostics is not None
            else ()
        )
        infos.append(
            ParameterInfo(
                raw_name=raw_name,
                py_name=translate_field_name(raw_name, snake_case=cfg.snake_case_fields),
                py_type=py_type.removeprefix("*"),
                java_type=java_type,
                is_spread=is_spread,
                py_annotations=py_annotations,
            ),
        )
    return infos


def _recover_error_parameter_info(node: JavaNode, cfg: TranslationConfig) -> ParameterInfo | None:
    """Recover annotated varargs that tree-sitter-java nests under ERROR nodes."""
    if "..." not in node.text:
        return None
    type_node = next(
        (child for child in node.named_children if child.type in _PARAMETER_TYPE_NODE_TYPES),
        None,
    )
    identifiers = [child for child in node.walk() if child.type == "identifier"]
    name_node = identifiers[-1] if identifiers else None
    if type_node is None or name_node is None:
        return None
    raw_name = name_node.text
    java_type = type_node.text
    py_type = translate_type(java_type, cfg)
    return ParameterInfo(
        raw_name=raw_name,
        py_name=translate_field_name(raw_name, snake_case=cfg.snake_case_fields),
        py_type=py_type.removeprefix("*"),
        java_type=java_type,
        is_spread=True,
    )


def params_for_method(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    type_var_map: dict[str, str] | None = None,
) -> list[str]:
    params: list[str] = []
    for param in parameter_infos(node, ctx.cfg, ctx.diagnostics):
        if type_var_map:
            param = ParameterInfo(
                raw_name=param.raw_name,
                py_name=param.py_name,
                py_type=_map_type_vars(param.py_type, type_var_map),
                java_type=param.java_type,
                is_spread=param.is_spread,
                py_annotations=param.py_annotations,
            )
        register_param(ctx, param)
        prefix = "*" if param.is_spread else ""
        py_type = _render_parameter_type(param, ctx)
        if ctx.cfg.emit_type_hints:
            ctx.diagnostics.imports.need_type_annotation(py_type)
            params.append(f"{prefix}{param.py_name}: {py_type}")
        else:
            params.append(f"{prefix}{param.py_name}")
    return params


def register_param(ctx: TranslationContext, param: ParameterInfo) -> None:
    ctx.param_names.add(param.raw_name)
    ctx.variable_types[param.raw_name] = (
        f"list[{param.py_type}]" if param.is_spread else param.py_type
    )
    ctx.variable_java_types[param.raw_name] = param.java_type


def _render_extra_params(ctx: TranslationContext, params: list[ParameterInfo]) -> list[str]:
    rendered: list[str] = []
    for param in params:
        if param.raw_name in ctx.param_names or param.py_name in ctx.param_names:
            continue
        register_param(ctx, param)
        if ctx.cfg.emit_type_hints:
            py_type = _render_parameter_type(param, ctx)
            ctx.diagnostics.imports.need_type_annotation(py_type)
            rendered.append(f"{param.py_name}: {py_type}")
        else:
            rendered.append(param.py_name)
    return rendered


def _render_parameter_type(param: ParameterInfo, ctx: TranslationContext) -> str:
    annotations = list(param.py_annotations)
    if not annotations:
        return param.py_type
    ctx.diagnostics.imports.need_typing("Annotated")
    return f"Annotated[{param.py_type}, {', '.join(annotations)}]"

"""Class and method emission for the rule-based skeleton translator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import (
    ClassTranslationState,
    TranslationContext,
    TranslationDiagnostics,
)
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import class_body_needs_pass, first_child_by_type
from j2py.translate.rules.literals import translate_literal, translate_string_literal
from j2py.translate.rules.naming import (
    translate_class_name,
    translate_field_name,
    translate_method_name,
)
from j2py.translate.rules.types import java_default_value, translate_type
from j2py.translate.statements import (
    class_uses_synchronized_this,
    instance_lock_init_line,
    translate_body,
)

TYPE_DECLARATION_NODES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}

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


@dataclass(frozen=True)
class FieldInfo:
    node: JavaNode
    name: str
    py_name: str
    java_type: str
    py_type: str
    is_static: bool
    initializer: JavaNode | None


@dataclass(frozen=True)
class ParameterInfo:
    raw_name: str
    py_name: str
    py_type: str
    is_spread: bool = False


def top_level_classes(root: JavaNode) -> list[JavaNode]:
    return [child for child in root.named_children if child.type in TYPE_DECLARATION_NODES]


def translate_class(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    inherited_class_field_types: dict[str, str] | None = None,
    inherited_declared_type_fields: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    if node.type == "interface_declaration":
        return _translate_interface(node, cfg, diagnostics)
    if node.type == "enum_declaration":
        return _translate_enum(node, cfg, diagnostics)
    if node.type == "record_declaration":
        return _translate_record(node, cfg, diagnostics)
    if node.type == "annotation_type_declaration":
        return _translate_annotation_declaration(node, cfg, diagnostics)

    is_supported_class = node.type == "class_declaration"
    diagnostics.record(
        node,
        supported=is_supported_class,
        reason=(
            "translated class declaration"
            if is_supported_class
            else f"unsupported top-level declaration {node.type}"
        ),
    )

    name_node = node.child_by_field("name")
    if name_node is None:
        diagnostics.record(node, supported=False, reason="class declaration without a name")
        return ["class Unknown:", "    # TODO(j2py): class declaration without a name", "    pass"]

    class_name = translate_class_name(name_node.text)
    if not is_supported_class:
        return [
            f"class {class_name}:",
            f"    # TODO(j2py): unsupported top-level declaration {node.type}",
            "    pass",
        ]

    fields = _class_fields(node, cfg)
    instance_field_names = _instance_field_names(fields)
    class_field_types = {
        **(inherited_class_field_types or {}),
        **_class_field_types(fields),
    }
    declared_type_fields = {
        **(inherited_declared_type_fields or {}),
        **_collect_declared_type_fields(node, cfg),
    }
    assigned_fields = _constructor_assigned_fields(node)
    body = node.child_by_field("body")
    members = (
        []
        if body is None
        else [
            child
            for child in body.named_children
            if child.type in {"constructor_declaration", "method_declaration"}
        ]
    )
    class_method_names = _member_method_names(members, cfg)
    class_state = ClassTranslationState(needs_instance_lock=class_uses_synchronized_this(node))
    lock_init_lines = [instance_lock_init_line()] if class_state.needs_instance_lock else []

    lines = [f"class {class_name}{_base_suffix(node)}:"]
    static_field_lines, instance_init_lines = _translate_fields(
        node,
        fields,
        assigned_fields,
        instance_field_names,
        cfg,
        diagnostics,
        declared_type_fields=declared_type_fields,
    )
    nested_type_lines = _nested_type_lines(
        body,
        cfg,
        diagnostics,
        inherited_class_field_types=class_field_types,
        inherited_declared_type_fields=declared_type_fields,
    )
    has_constructor = any(member.type == "constructor_declaration" for member in members)
    needs_synthetic_init = (
        (bool(instance_init_lines) or class_state.needs_instance_lock) and not has_constructor
    )

    if not members and not static_field_lines and not instance_init_lines and not nested_type_lines:
        lines.append("    pass")
        return lines

    lines.extend(static_field_lines)

    if needs_synthetic_init:
        if static_field_lines:
            lines.append("")
        lines.append("    def __init__(self) -> None:")
        lines.extend(lock_init_lines)
        lines.extend(instance_init_lines)

    if nested_type_lines:
        if static_field_lines or needs_synthetic_init:
            lines.append("")
        lines.extend(nested_type_lines)

    for group in _member_groups(members):
        lines.append("")
        if len(group) > 1:
            lines.extend(
                _translate_overloaded_members(
                    group,
                    cfg=cfg,
                    diagnostics=diagnostics,
                    class_fields=instance_field_names,
                    class_field_types=class_field_types,
                    declared_type_fields=declared_type_fields,
                    class_methods=class_method_names,
                    pre_body_lines=(
                        lock_init_lines + instance_init_lines
                        if group[0].type == "constructor_declaration"
                        else []
                    ),
                    class_state=class_state,
                ),
            )
            continue

        member = group[0]
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
            class_field_types=class_field_types,
            declared_type_fields=declared_type_fields,
            class_methods=class_method_names,
            allow_local_helpers=True,
            class_state=class_state,
        )
        pre_body_lines = (
            lock_init_lines + instance_init_lines
            if member.type == "constructor_declaration"
            else []
        )
        lines.extend(_translate_method(member, ctx, pre_body_lines=pre_body_lines))

    if class_body_needs_pass(lines):
        lines.append("    pass")

    return lines


def _translate_interface(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated interface declaration")
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    body = node.child_by_field("body")
    methods = [] if body is None else list(body.find_all("method_declaration"))
    class_method_names = _member_method_names(methods, cfg)

    lines = [f"class {class_name}(Protocol):"]
    wrote_member = False
    for method in methods:
        _record_annotation_diagnostics(method, cfg, diagnostics)
        method_body = _method_body(method)
        if method_body is not None:
            reason = (
                "translated interface static method"
                if "static" in _modifiers(method)
                else "translated interface default method"
            )
            diagnostics.record(method, supported=True, reason=reason)
            ctx = TranslationContext(
                cfg=cfg,
                diagnostics=diagnostics,
                class_fields=set(),
                class_field_types={},
                class_methods=class_method_names,
                allow_local_helpers=True,
            )
            lines.extend(_translate_method(method, ctx, supported_reason=reason))
            wrote_member = True
            continue

        diagnostics.record(method, supported=True, reason="translated abstract interface method")
        signature = _signature(
            _member_python_name(method),
            _parameter_infos(method, cfg),
            return_type=_return_type(method, cfg),
            include_self="static" not in _modifiers(method),
            emit_type_hints=cfg.emit_type_hints,
        )
        lines.append(f"    {signature}: ...")
        wrote_member = True

    if not wrote_member:
        lines.append("    pass")
    return lines


def _translate_enum(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated enum declaration")
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    body = node.child_by_field("body")
    constants = (
        []
        if body is None
        else [child for child in body.named_children if child.type == "enum_constant"]
    )
    fields = _enum_fields(node, cfg)
    instance_field_names = _instance_field_names(fields)
    class_field_types = _class_field_types(fields)
    declared_type_fields = _collect_declared_type_fields(node, cfg)
    declarations = [] if body is None else body.children_by_type("enum_body_declarations")
    members = [
        child
        for declaration in declarations
        for child in declaration.named_children
        if child.type in {"constructor_declaration", "method_declaration"}
    ]

    interfaces = _enum_interface_names(node)
    lines = [f"class {class_name}(Enum):"]
    if interfaces:
        diagnostics.warn(
            node,
            reason="enum interface implementation emitted as comment; verify Protocol conformance",
        )
        lines.append(f"    # implements {', '.join(interfaces)}")
    if not constants and not fields and not members:
        lines.append("    pass")
        return lines
    for constant in constants:
        lines.extend(_translate_enum_constant(constant, cfg, diagnostics))

    for field in fields:
        diagnostics.record(field.node, supported=True, reason="translated enum field declaration")
        lines.append(f"    {_field_assignment(field.py_name, field.py_type, cfg)}")

    for group in _member_groups(members):
        lines.append("")
        if len(group) > 1:
            lines.extend(
                _translate_overloaded_members(
                    group,
                    cfg=cfg,
                    diagnostics=diagnostics,
                    class_fields=instance_field_names,
                    class_field_types=class_field_types,
                    declared_type_fields=declared_type_fields,
                    pre_body_lines=[],
                ),
            )
            continue
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
            class_field_types=class_field_types,
            declared_type_fields=declared_type_fields,
            allow_local_helpers=True,
        )
        lines.extend(_translate_method(group[0], ctx))
    return lines


def _enum_interface_names(node: JavaNode) -> list[str]:
    interfaces = node.child_by_field("interfaces") or first_child_by_type(
        node,
        "super_interfaces",
    )
    if interfaces is None:
        return []

    names: list[str] = []

    def collect_types(candidate: JavaNode) -> None:
        if candidate.type == "type_arguments":
            return
        if candidate.type in {"type_identifier", "scoped_type_identifier"}:
            names.append(translate_class_name(candidate.text))
            return
        for child in candidate.named_children:
            collect_types(child)

    collect_types(interfaces)
    return names


def _translate_enum_constant(
    constant: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(constant, supported=True, reason="translated enum constant")
    name_node = constant.child_by_field("name") or first_child_by_type(constant, "identifier")
    constant_name = name_node.text if name_node is not None else constant.text.split("(", 1)[0]
    body = first_child_by_type(constant, "class_body")
    if body is not None:
        diagnostics.record(
            body,
            supported=False,
            reason="enum constant class body requires manual translation",
        )
    args_node = first_child_by_type(constant, "argument_list")
    if args_node is None or not args_node.named_children:
        return [f"    {constant_name} = {constant_name!r}"]

    arg_ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics)
    args = [translate_expression(arg, arg_ctx) for arg in args_node.named_children]
    value = f"({', '.join(args)})" if len(args) > 1 else args[0]
    return [f"    {constant_name} = {value}"]


def _enum_fields(enum_node: JavaNode, cfg: TranslationConfig) -> list[FieldInfo]:
    body = enum_node.child_by_field("body")
    if body is None:
        return []

    fields: list[FieldInfo] = []
    for declaration in body.children_by_type("enum_body_declarations"):
        for child in declaration.named_children:
            if child.type != "field_declaration":
                continue
            type_node = child.child_by_field("type")
            java_type = type_node.text if type_node is not None else "Object"
            modifiers = _modifiers(child)
            for declarator in child.find_all("variable_declarator"):
                name_node = declarator.child_by_field("name")
                if name_node is None:
                    continue
                fields.append(
                    FieldInfo(
                        node=child,
                        name=name_node.text,
                        py_name=translate_field_name(
                            name_node.text,
                            snake_case=cfg.snake_case_fields,
                        ),
                        java_type=java_type,
                        py_type=translate_type(java_type, cfg),
                        is_static="static" in modifiers,
                        initializer=declarator.child_by_field("value"),
                    ),
                )
    return fields


def _translate_record(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated record declaration")
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    params = _parameter_infos(node, cfg)

    lines = ["@dataclass(frozen=True)", f"class {class_name}:"]
    if not params:
        lines.append("    pass")
        return lines
    for param in params:
        lines.append(f"    {param.py_name}: {param.py_type}")
    return lines


_ANNOTATION_META_NAMES = frozenset(
    {"Target", "Retention", "Documented", "Inherited", "Repeatable", "Native"}
)
_ANNOTATION_ELEMENT_TYPE_NODES = frozenset(
    {
        "type_identifier",
        "scoped_type_identifier",
        "generic_type",
        "array_type",
        "integral_type",
        "floating_point_type",
        "boolean_type",
        "void_type",
    }
)


def _translate_annotation_declaration(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    lines: list[str] = []

    for modifiers in node.children_by_type("modifiers"):
        for annotation in modifiers.named_children:
            if annotation.type not in {"annotation", "marker_annotation"}:
                continue
            name = _annotation_node_name(annotation)
            if name is None:
                continue
            if name in _ANNOTATION_META_NAMES:
                diagnostics.warn(
                    annotation,
                    reason=f"preserved meta-annotation @{name}",
                )
                if cfg.emit_line_comments:
                    lines.append(f"# {annotation.text.strip()}")
                continue
            diagnostics.warn(annotation, reason=f"preserved annotation @{name}")
            if cfg.emit_line_comments:
                lines.append(f"# {annotation.text.strip()}")

    lines.extend(["@dataclass(frozen=True)", f"class {class_name}:"])

    body = node.child_by_field("body")
    member_lines: list[str] = []
    if body is not None:
        for member in body.named_children:
            if member.type == "annotation_type_element_declaration":
                member_lines.append(_translate_annotation_element(member, cfg, diagnostics))
                continue
            if is_comment(member):
                diagnostics.warn(member, reason="preserved comment")
                if cfg.emit_line_comments:
                    member_lines.extend(translate_comment(member, indent="    "))
                continue
            diagnostics.record(
                member,
                supported=False,
                reason=f"unsupported annotation member {member.type}",
            )
            member_lines.append(f"    # TODO(j2py): unsupported annotation member {member.type}")

    if not member_lines:
        lines.append("    pass")
    else:
        lines.extend(member_lines)

    diagnostics.record(node, supported=True, reason="translated annotation type declaration")
    return lines


def _annotation_node_name(annotation: JavaNode) -> str | None:
    name_node = annotation.child_by_field("name")
    if name_node is None:
        name_node = first_child_by_type(annotation, "identifier", "scoped_identifier")
    return name_node.text if name_node is not None else None


def _translate_annotation_element(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> str:
    type_node = _annotation_element_type_node(node)
    name_node = _annotation_element_name_node(node)
    if type_node is None or name_node is None:
        diagnostics.record(node, supported=False, reason="malformed annotation element")
        return "    # TODO(j2py): malformed annotation element"

    _record_annotation_element_modifiers(node, diagnostics)

    py_name = translate_field_name(name_node.text, snake_case=cfg.snake_case_fields)
    py_type = _annotation_element_py_type(type_node, cfg)
    default_node = _annotation_element_default_node(node)
    if default_node is None:
        diagnostics.record(node, supported=True, reason="translated annotation element")
        if cfg.emit_type_hints:
            return f"    {py_name}: {py_type}"
        return f"    {py_name}"

    default_value = _annotation_element_default(default_node, cfg, diagnostics)
    if default_value is None:
        diagnostics.record(
            node,
            supported=False,
            reason="unsupported annotation element default",
        )
        if cfg.emit_type_hints:
            return (
                f"    {py_name}: {py_type} | None = None"
                f"  # TODO(j2py): unsupported default"
            )
        return f"    {py_name} = None  # TODO(j2py): unsupported default"

    diagnostics.record(node, supported=True, reason="translated annotation element")
    if cfg.emit_type_hints:
        return f"    {py_name}: {py_type} = {default_value}"
    return f"    {py_name} = {default_value}"


def _record_annotation_element_modifiers(
    node: JavaNode,
    diagnostics: TranslationDiagnostics,
) -> None:
    for modifiers in node.children_by_type("modifiers"):
        for annotation in modifiers.named_children:
            if annotation.type not in {"annotation", "marker_annotation"}:
                continue
            name = _annotation_node_name(annotation)
            if name is None:
                continue
            diagnostics.warn(
                annotation,
                reason=f"preserved annotation element @{name}",
            )


def _annotation_element_default_node(node: JavaNode) -> JavaNode | None:
    saw_default = False
    for child in node.children:
        if not saw_default:
            if child.type == "default" or child.text == "default":
                saw_default = True
            continue
        if child.text == ";" or child.type == ";":
            break
        if child.type in {"(", ")"}:
            continue
        if is_comment(child):
            continue
        return child
    return None


def _annotation_element_type_node(node: JavaNode) -> JavaNode | None:
    for child in node.named_children:
        if child.type in _ANNOTATION_ELEMENT_TYPE_NODES:
            return child
    return None


def _annotation_element_name_node(node: JavaNode) -> JavaNode | None:
    name_node = node.child_by_field("name")
    if name_node is not None:
        return name_node
    for child in node.named_children:
        if child.type == "identifier":
            return child
    return None


def _annotation_element_py_type(type_node: JavaNode, cfg: TranslationConfig) -> str:
    if type_node.type == "array_type":
        element_type = next(
            (child for child in type_node.named_children if child.type != "dimensions"),
            None,
        )
        inner_py = translate_type(element_type.text if element_type is not None else "Object", cfg)
        return f"tuple[{inner_py}, ...]"
    java_type = type_node.text
    if java_type.endswith("[]"):
        inner_py = translate_type(java_type[:-2], cfg)
        return f"tuple[{inner_py}, ...]"
    return translate_type(java_type, cfg)


def _annotation_element_default(
    default_node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> str | None:
    if default_node.type == "element_value_array_initializer":
        values: list[str] = []
        for child in default_node.named_children:
            scalar = _annotation_scalar_default(child, cfg, diagnostics)
            if scalar is None:
                return None
            values.append(scalar)
        if not values:
            return "()"
        if len(values) == 1:
            return f"({values[0]},)"
        return f"({', '.join(values)})"

    return _annotation_scalar_default(default_node, cfg, diagnostics)


def _annotation_scalar_default(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> str | None:
    if node.type in _IMMUTABLE_LITERAL_NODES:
        if node.type == "string_literal":
            return translate_string_literal(node.text)
        return translate_literal(node.text, cfg)

    if node.type == "class_literal":
        type_node = node.named_children[0] if node.named_children else None
        if type_node is None:
            return None
        diagnostics.warn(node, reason="annotation class literal default requires manual review")
        mapped = translate_class_name(type_node.text)
        if mapped == "Object":
            return "object"
        return mapped

    if node.type == "unary_expression":
        ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics)
        translated = translate_expression(node, ctx)
        if translated.startswith("__j2py_todo__"):
            return None
        return translated

    ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics)
    translated = translate_expression(node, ctx)
    if translated.startswith("__j2py_todo__"):
        return None
    return translated


def _nested_type_lines(
    body: JavaNode | None,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    inherited_class_field_types: dict[str, str],
    inherited_declared_type_fields: dict[str, dict[str, str]],
) -> list[str]:
    if body is None:
        return []

    lines: list[str] = []
    for child in body.named_children:
        if child.type not in TYPE_DECLARATION_NODES:
            continue
        if lines:
            lines.append("")
        child_lines = translate_class(
            child,
            cfg,
            diagnostics,
            inherited_class_field_types=inherited_class_field_types,
            inherited_declared_type_fields=inherited_declared_type_fields,
        )
        lines.extend(f"    {line}" if line else line for line in child_lines)
    return lines


def _base_suffix(node: JavaNode) -> str:
    superclass = node.child_by_field("superclass")
    if superclass is None:
        return ""
    type_node = first_child_by_type(superclass, "type_identifier", "scoped_type_identifier")
    if type_node is None:
        return ""
    return f"({translate_class_name(type_node.text)})"


def _class_fields(class_node: JavaNode, cfg: TranslationConfig) -> list[FieldInfo]:
    body = class_node.child_by_field("body")
    if body is None:
        return []

    fields: list[FieldInfo] = []
    for child in body.named_children:
        if child.type != "field_declaration":
            continue
        type_node = child.child_by_field("type")
        java_type = type_node.text if type_node is not None else "Object"
        modifiers = _modifiers(child)
        for declarator in child.find_all("variable_declarator"):
            name_node = declarator.child_by_field("name")
            if name_node is None:
                continue
            fields.append(
                FieldInfo(
                    node=child,
                    name=name_node.text,
                    py_name=translate_field_name(
                        name_node.text,
                        snake_case=cfg.snake_case_fields,
                    ),
                    java_type=java_type,
                    py_type=translate_type(java_type, cfg),
                    is_static="static" in modifiers,
                    initializer=declarator.child_by_field("value"),
                ),
            )
    return fields


def field_infos_from_declaration(node: JavaNode, cfg: TranslationConfig) -> list[FieldInfo]:
    """Extract field metadata from a single ``field_declaration`` node."""
    if node.type != "field_declaration":
        return []

    type_node = node.child_by_field("type")
    java_type = type_node.text if type_node is not None else "Object"
    modifiers = _modifiers(node)
    fields: list[FieldInfo] = []
    for declarator in node.find_all("variable_declarator"):
        name_node = declarator.child_by_field("name")
        if name_node is None:
            continue
        fields.append(
            FieldInfo(
                node=node,
                name=name_node.text,
                py_name=translate_field_name(
                    name_node.text,
                    snake_case=cfg.snake_case_fields,
                ),
                java_type=java_type,
                py_type=translate_type(java_type, cfg),
                is_static="static" in modifiers,
                initializer=declarator.child_by_field("value"),
            ),
        )
    return fields


def _constructor_assigned_fields(class_node: JavaNode) -> set[str]:
    body = class_node.child_by_field("body")
    if body is None:
        return set()

    assigned: set[str] = set()
    for member in body.named_children:
        if member.type != "constructor_declaration":
            continue
        constructor_body = member.child_by_field("body") or first_child_by_type(
            member,
            "constructor_body",
        )
        if constructor_body is None:
            continue
        for assignment in constructor_body.find_all("assignment_expression"):
            children = assignment.named_children
            if not children:
                continue
            field_name = _this_field_name(children[0])
            if field_name is not None:
                assigned.add(field_name)
    return assigned


def _this_field_name(node: JavaNode) -> str | None:
    if node.type != "field_access":
        return None
    children = node.named_children
    if len(children) != 2 or children[0].type != "this":
        return None
    return children[1].text


def _instance_field_names(fields: list[FieldInfo]) -> set[str]:
    return {field.name for field in fields if not field.is_static}


def _instance_field_types(fields: list[FieldInfo]) -> dict[str, str]:
    return {field.name: field.py_type for field in fields if not field.is_static}


def _class_field_types(fields: list[FieldInfo]) -> dict[str, str]:
    return {field.name: field.py_type for field in fields}


def _collect_declared_type_fields(
    class_node: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    by_type: dict[str, dict[str, str]] = {}

    def add_type(type_node: JavaNode) -> None:
        name_node = type_node.child_by_field("name")
        if name_node is None:
            return
        by_type[name_node.text] = {
            field.name: field.py_type for field in _class_fields(type_node, cfg)
        }
        body = type_node.child_by_field("body")
        if body is None:
            return
        for child in body.named_children:
            if child.type in TYPE_DECLARATION_NODES:
                add_type(child)

    add_type(class_node)
    return by_type


def _member_method_names(members: Iterable[JavaNode], cfg: TranslationConfig) -> set[str]:
    return {
        translate_method_name(_raw_member_name(member), snake_case=cfg.snake_case_methods)
        for member in members
    }


def _raw_member_name(member: JavaNode) -> str:
    if member.type == "constructor_declaration":
        return "__init__"
    name_node = member.child_by_field("name")
    return name_node.text if name_node is not None else "unknown"


def _translate_fields(
    class_node: JavaNode,
    fields: list[FieldInfo],
    assigned_fields: set[str],
    instance_field_names: set[str],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    declared_type_fields: dict[str, dict[str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    body = class_node.child_by_field("body")
    if body is None:
        return [], []

    static_lines: list[str] = []
    instance_init_lines: list[str] = []
    type_fields = declared_type_fields or {}
    static_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
        class_field_types=_class_field_types(fields),
        declared_type_fields=type_fields,
    )
    instance_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
        class_field_types=_class_field_types(fields),
        declared_type_fields=type_fields,
        in_instance_method=True,
    )

    for field in fields:
        if field.is_static:
            static_lines.extend(_translate_static_field(field, static_ctx, diagnostics))
            continue

        if field.initializer is not None:
            diagnostics.record(
                field.node,
                supported=True,
                reason="translated instance field initializer",
            )
            instance_init_lines.append(
                f"        {_field_assignment(f'self.{field.py_name}', field.py_type, cfg)} = "
                f"{translate_expression(field.initializer, instance_ctx)}",
            )
            continue

        if field.name in assigned_fields:
            diagnostics.record(
                field.node,
                supported=True,
                reason="represented field declaration via constructor assignment",
            )
            continue

        diagnostics.record(
            field.node,
            supported=True,
            reason="translated Java default value for instance field",
        )
        default_value = java_default_value(field.java_type)
        annotation = field.py_type if default_value != "None" else f"{field.py_type} | None"
        target = _field_assignment(f"self.{field.py_name}", annotation, cfg)
        instance_init_lines.append(f"        {target} = {default_value}")

    supported_members = {
        "field_declaration",
        "constructor_declaration",
        "method_declaration",
        "static_initializer",
        *TYPE_DECLARATION_NODES,
    }
    for child in body.named_children:
        if child.type == "static_initializer":
            diagnostics.record(child, supported=True, reason="translated static initializer")
            static_body = first_child_by_type(child, "block")
            static_lines.extend(
                translate_body(
                    static_body,
                    static_ctx,
                    indent="    ",
                )
                if static_body is not None
                else ["    pass"]
            )
            continue
        if child.type in supported_members:
            continue
        if is_comment(child):
            diagnostics.warn(child, reason="preserved comment")
            if not cfg.emit_line_comments:
                continue
            static_lines.extend(translate_comment(child, indent="    "))
            continue
        diagnostics.record(child, supported=False, reason=f"unsupported class member {child.type}")
        static_lines.append(f"    # TODO(j2py): unsupported class member {child.type}")

    return static_lines, instance_init_lines


def _translate_static_field(
    field: FieldInfo,
    ctx: TranslationContext,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    if field.initializer is None:
        diagnostics.record(
            field.node,
            supported=True,
            reason="translated Java default value for static field",
        )
        default_value = java_default_value(field.java_type)
        annotation = field.py_type if default_value != "None" else f"{field.py_type} | None"
        return [
            f"    {_field_assignment(field.py_name, annotation, ctx.cfg)} = {default_value}",
        ]

    diagnostics.record(field.node, supported=True, reason="translated static field declaration")
    return [
        f"    {_field_assignment(field.py_name, field.py_type, ctx.cfg)} = "
        f"{translate_expression(field.initializer, ctx)}",
    ]


def _member_groups(members: list[JavaNode]) -> list[list[JavaNode]]:
    order: list[str] = []
    groups: dict[str, list[JavaNode]] = {}
    for member in members:
        name = _member_python_name(member)
        if name not in groups:
            order.append(name)
            groups[name] = []
        groups[name].append(member)
    return [groups[name] for name in order]


def _member_python_name(member: JavaNode) -> str:
    if member.type == "constructor_declaration":
        return "__init__"
    name_node = member.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    return translate_method_name(raw_name)


def _translate_method(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    unsupported_reason: str | None = None,
    pre_body_lines: list[str] | None = None,
    decorator_lines: list[str] | None = None,
    def_line_suffix: str = "",
    supported_reason: str | None = None,
) -> list[str]:
    _record_annotation_diagnostics(node, ctx.cfg, ctx.diagnostics)
    supported = node.type in {"constructor_declaration", "method_declaration"}
    ctx.diagnostics.record(
        node,
        supported=supported and unsupported_reason is None,
        reason=unsupported_reason or supported_reason or "translated method declaration",
    )

    is_constructor = node.type == "constructor_declaration"
    is_static = "static" in _modifiers(node)
    ctx.in_instance_method = not is_static

    name_node = node.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = (
        "__init__"
        if is_constructor
        else translate_method_name(raw_name, snake_case=ctx.cfg.snake_case_methods)
    )
    return_type = "None" if is_constructor else _return_type(node, ctx.cfg)
    params = _params(node, ctx)
    if not is_static:
        params.insert(0, "self")

    if unsupported_reason is not None:
        return [f"    # TODO(j2py): {unsupported_reason}", "    pass"]

    lines: list[str] = list(decorator_lines or [])
    if is_static:
        lines.append("    @staticmethod")
    returns = f" -> {return_type}" if ctx.cfg.emit_type_hints else ""
    lines.append(f"    def {py_name}({', '.join(params)}){returns}:{def_line_suffix}")

    body = node.child_by_field("body")
    if body is None:
        body = first_child_by_type(node, "block", "constructor_body")

    ctx.allow_local_helpers = True
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    lines.extend(pre_body_lines or [])

    # Flush any helpers generated for block lambdas encountered while walking
    # the body (including deep inside expressions). They are placed after any
    # pre-body initialization but before the original statements so the names
    # are defined for the whole method and grouped for review.
    if ctx.pending_local_helpers:
        for helper in ctx.pending_local_helpers:
            lines.append("")
            lines.extend(helper)

    lines.extend(body_lines)
    return lines


def _translate_overloaded_members(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_fields: set[str],
    class_field_types: dict[str, str] | None = None,
    declared_type_fields: dict[str, dict[str, str]] | None = None,
    class_methods: set[str] | None = None,
    pre_body_lines: list[str],
    class_state: ClassTranslationState | None = None,
) -> list[str]:
    name = _member_python_name(members[0])
    for member in members:
        _record_annotation_diagnostics(member, cfg, diagnostics)

    field_types = class_field_types or {f: "object" for f in class_fields}
    nested_type_fields = declared_type_fields or {}

    if members[0].type == "constructor_declaration":
        merged_constructor = _merged_constructor_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=class_fields,
            class_field_types=field_types,
            declared_type_fields=nested_type_fields,
            class_methods=class_methods or set(),
            pre_body_lines=pre_body_lines,
            class_state=class_state,
        )
        if merged_constructor is not None:
            return merged_constructor
    else:
        merged_method = _merged_method_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=class_fields,
            class_field_types=field_types,
            declared_type_fields=nested_type_fields,
            class_methods=class_methods or set(),
            class_state=class_state,
        )
        if merged_method is not None:
            return merged_method

        forwarded_method = _merged_forwarding_method_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=class_fields,
            class_field_types=field_types,
            declared_type_fields=nested_type_fields,
        )
        if forwarded_method is not None:
            return forwarded_method

    dispatched = _dispatch_overload_members(
        members,
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_field_types=field_types,
        declared_type_fields=nested_type_fields,
        pre_body_lines=pre_body_lines,
        class_state=class_state,
    )
    if dispatched is not None:
        return dispatched

    for member in members:
        diagnostics.record(
            member,
            supported=False,
            reason=f"overloaded method {name} requires manual dispatch",
        )
    lines = _overload_stubs(members, cfg)
    fallback_return = "None" if members[0].type == "constructor_declaration" else "object"
    is_static = "static" in _modifiers(members[0])
    if is_static:
        lines.append("    @staticmethod")
    fallback_params = "*args: object" if is_static else "self, *args: object"
    lines.append(f"    def {name}({fallback_params}) -> {fallback_return}:")
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


def _merged_constructor_overload(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_fields: set[str],
    class_field_types: dict[str, str],
    declared_type_fields: dict[str, dict[str, str]],
    class_methods: set[str],
    pre_body_lines: list[str],
    class_state: ClassTranslationState | None = None,
) -> list[str] | None:
    forwards = [
        _OverloadForward(member, _parameter_infos(member, cfg), _constructor_forward_args(member))
        for member in members
    ]
    merged = _resolve_overload_defaults(forwards, cfg)
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
        allow_local_helpers=True,
        class_state=class_state,
    )
    ctx.class_field_types = dict(class_field_types)
    ctx.declared_type_fields = dict(declared_type_fields)
    ctx.in_instance_method = True
    for param in impl.params:
        _register_param(ctx, param)

    signature_params, defaults, sentinel_lines = _defaulted_parameters(
        impl.params,
        defaults_by_position,
    )

    lines = _overload_stubs(members, cfg)
    signature = _signature(
        "__init__",
        signature_params,
        return_type="None",
        include_self=True,
        defaults=defaults,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    body = _method_body(impl.member)
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
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
    class_fields: set[str],
    class_field_types: dict[str, str],
    declared_type_fields: dict[str, dict[str, str]],
) -> list[str] | None:
    """Merge builder-style overloads where shorter ones forward to the longest one."""
    if any(member.type != "method_declaration" for member in members):
        return None
    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None

    forwards = [
        _OverloadForward(member, _parameter_infos(member, cfg), _method_forward_args(member))
        for member in members
    ]
    merged = _resolve_overload_defaults(forwards, cfg)
    if merged is None:
        return None
    impl, defaults_by_position, throwaway_diagnostics = merged
    if _method_body(impl.member) is None:
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
                reason="translated forwarding method overload",
            )

    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        allow_local_helpers=True,
    )
    ctx.class_field_types = dict(class_field_types)
    ctx.declared_type_fields = dict(declared_type_fields)
    ctx.in_instance_method = not is_static
    for param in impl.params:
        _register_param(ctx, param)

    signature_params, defaults, sentinel_lines = _defaulted_parameters(
        impl.params,
        defaults_by_position,
    )
    return_type = _union_types(_return_type(member, cfg) for member in members)

    lines = _overload_stubs(members, cfg)
    if is_static:
        lines.append("    @staticmethod")
    signature = _signature(
        _member_python_name(impl.member),
        signature_params,
        return_type=return_type,
        include_self=not is_static,
        defaults=defaults,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    body = _method_body(impl.member)
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
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
    throwaway = TranslationContext(cfg=cfg, diagnostics=throwaway_diagnostics)
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
        if arg.type == "identifier" and arg.text in own_names:
            entries.append(own_names[arg.text])
        elif _references_names(arg, set(own_names)):
            return None
        else:
            entries.append(arg)
    return entries


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
            ParameterInfo(raw_name=param.raw_name, py_name=param.py_name, py_type=annotation),
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
    class_fields: set[str],
    class_field_types: dict[str, str],
    declared_type_fields: dict[str, dict[str, str]],
    class_methods: set[str],
    class_state: ClassTranslationState | None = None,
) -> list[str] | None:
    if any(member.type != "method_declaration" for member in members):
        return None
    body_texts: set[str] = set()
    for member in members:
        body = _method_body(member)
        body_texts.add(body.text if body is not None else "")
    if len(body_texts) != 1:
        return None

    param_sets = [_parameter_infos(member, cfg) for member in members]
    if len({len(params) for params in param_sets}) != 1:
        return None
    if len(param_sets[0]) == 0:
        return None

    raw_names = [param.raw_name for param in param_sets[0]]
    if any([param.raw_name for param in params] != raw_names for params in param_sets):
        return None

    name = _member_python_name(members[0])
    is_static = "static" in _modifiers(members[0])
    if any(("static" in _modifiers(member)) != is_static for member in members):
        return None

    merged_params = [
        ParameterInfo(
            raw_name=param_sets[0][index].raw_name,
            py_name=param_sets[0][index].py_name,
            py_type=_union_types(params[index].py_type for params in param_sets),
            is_spread=param_sets[0][index].is_spread,
        )
        for index in range(len(param_sets[0]))
    ]
    return_type = _union_types(_return_type(member, cfg) for member in members)

    for member in members:
        diagnostics.record(member, supported=True, reason="translated overloaded method")

    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_methods=class_methods,
        allow_local_helpers=True,
        class_state=class_state,
    )
    ctx.class_field_types = dict(class_field_types)
    ctx.declared_type_fields = dict(declared_type_fields)
    ctx.in_instance_method = not is_static
    for param in merged_params:
        _register_param(ctx, param)

    lines = _overload_stubs(members, cfg)
    if is_static:
        lines.append("    @staticmethod")
    signature = _signature(
        name,
        merged_params,
        return_type=return_type,
        include_self=not is_static,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    body = _method_body(members[0])
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]

    # Flush block-lambda helpers for this merged method implementation.
    if ctx.pending_local_helpers:
        for helper in ctx.pending_local_helpers:
            lines.append("")
            lines.extend(helper)

    lines.extend(body_lines)
    return lines


def _constructor_forward_args(member: JavaNode) -> list[JavaNode] | None:
    """Return the argument nodes of a pure this(...) delegating constructor."""
    body = _method_body(member)
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
    body = _method_body(member)
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


def _dispatch_overload_members(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_fields: set[str],
    class_field_types: dict[str, str],
    declared_type_fields: dict[str, dict[str, str]],
    pre_body_lines: list[str],
    class_state: ClassTranslationState | None = None,
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
    if any("static" in _modifiers(member) for member in members):
        return None

    erased = [_erased_overload_signature(member, cfg) for member in members]
    if len(set(erased)) != len(erased):
        return None

    is_constructor = members[0].type == "constructor_declaration"
    reason = (
        "translated overloaded constructor via runtime dispatch"
        if is_constructor
        else "translated overloaded method via runtime dispatch"
    )

    name_node = members[0].child_by_field("name")
    java_name = name_node.text if name_node is not None and not is_constructor else ""
    lines: list[str] = []
    for index, member in enumerate(members):
        if index:
            lines.append("")
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=class_fields,
            class_field_types=dict(class_field_types),
            declared_type_fields=dict(declared_type_fields),
            allow_local_helpers=True,
            self_dispatch_methods={java_name} if java_name else set(),
            class_state=class_state,
        )
        member_pre_body = (
            pre_body_lines if is_constructor and not _has_this_delegation(member) else []
        )
        lines.extend(
            _translate_method(
                member,
                ctx,
                pre_body_lines=member_pre_body,
                decorator_lines=["    @overloaded"],
                def_line_suffix=("" if index == 0 else "  # type: ignore[no-redef]  # noqa: F811"),
                supported_reason=reason,
            ),
        )
    return lines


def _erased_overload_signature(member: JavaNode, cfg: TranslationConfig) -> tuple[str, ...]:
    return tuple(
        ("*" if param.is_spread else "") + _erase_py_type(param.py_type)
        for param in _parameter_infos(member, cfg)
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


def _has_this_delegation(member: JavaNode) -> bool:
    body = _method_body(member)
    if body is None:
        return False
    for invocation in body.find_all("explicit_constructor_invocation"):
        target = invocation.named_children[0] if invocation.named_children else None
        if target is not None and target.type == "this":
            return True
    return False


def _overload_stubs(members: list[JavaNode], cfg: TranslationConfig) -> list[str]:
    lines: list[str] = []
    for member in members:
        is_static = "static" in _modifiers(member)
        if is_static:
            lines.append("    @staticmethod")
        lines.append("    @overload")
        signature = _signature(
            _member_python_name(member),
            _parameter_infos(member, cfg),
            return_type=(
                "None" if member.type == "constructor_declaration" else _return_type(member, cfg)
            ),
            include_self=not is_static,
            emit_type_hints=cfg.emit_type_hints,
        )
        lines.append(f"    {signature}: ...")
    return lines


def _signature(
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


def _union_types(types: Iterable[str]) -> str:
    unique: list[str] = []
    for py_type in types:
        if py_type not in unique:
            unique.append(py_type)
    return " | ".join(unique)


def _readable_signature(member: JavaNode, cfg: TranslationConfig) -> str:
    params = ", ".join(
        f"{'*' if param.is_spread else ''}{param.py_name}: {param.py_type}"
        for param in _parameter_infos(member, cfg)
    )
    return f"{_member_python_name(member)}({params})"


def _method_body(node: JavaNode) -> JavaNode | None:
    return node.child_by_field("body") or first_child_by_type(node, "block", "constructor_body")


def _modifiers(node: JavaNode) -> set[str]:
    modifiers: set[str] = set()
    for modifier_node in node.children_by_type("modifiers"):
        modifiers.update(modifier_node.text.split())
    return modifiers


def _record_annotation_diagnostics(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> None:
    for annotation_name in _annotation_names(node):
        if annotation_name in cfg.drop_annotations:
            diagnostics.warn(node, reason=f"dropped annotation @{annotation_name}")
        else:
            diagnostics.warn(node, reason=f"unsupported annotation @{annotation_name}")


def _annotation_names(node: JavaNode) -> list[str]:
    names: list[str] = []
    for modifiers in node.children_by_type("modifiers"):
        for annotation in modifiers.named_children:
            if annotation.type not in {"annotation", "marker_annotation"}:
                continue
            name_node = annotation.child_by_field("name")
            if name_node is None:
                name_node = first_child_by_type(annotation, "identifier", "scoped_identifier")
            if name_node is not None:
                names.append(name_node.text)
    return names


def _return_type(node: JavaNode, cfg: TranslationConfig) -> str:
    type_node = node.child_by_field("type")
    if type_node is None:
        return "None"
    return translate_type(type_node.text, cfg)


def _parameter_infos(node: JavaNode, cfg: TranslationConfig) -> list[ParameterInfo]:
    params_node = node.child_by_field("parameters")
    if params_node is None:
        return []

    infos: list[ParameterInfo] = []
    for param in params_node.find_all("formal_parameter", "spread_parameter"):
        is_spread = param.type == "spread_parameter"
        type_node = param.child_by_field("type")
        name_node = param.child_by_field("name")
        if is_spread:
            # spread_parameter has no name/type fields: the name lives in a
            # nested variable_declarator and the element type is the first
            # non-declarator named child.
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
        py_type = translate_type(type_node.text if type_node is not None else "Object", cfg)
        infos.append(
            ParameterInfo(
                raw_name=raw_name,
                py_name=translate_field_name(raw_name, snake_case=cfg.snake_case_fields),
                py_type=py_type.removeprefix("*"),
                is_spread=is_spread,
            ),
        )
    return infos


def _params(node: JavaNode, ctx: TranslationContext) -> list[str]:
    params: list[str] = []
    for param in _parameter_infos(node, ctx.cfg):
        _register_param(ctx, param)
        prefix = "*" if param.is_spread else ""
        if ctx.cfg.emit_type_hints:
            params.append(f"{prefix}{param.py_name}: {param.py_type}")
        else:
            params.append(f"{prefix}{param.py_name}")
    return params


def _register_param(ctx: TranslationContext, param: ParameterInfo) -> None:
    ctx.param_names.add(param.raw_name)
    # A Java varargs parameter is a tuple of elements at runtime; the list type
    # keeps collection heuristics (len, indexing, iteration) working.
    ctx.variable_types[param.raw_name] = (
        f"list[{param.py_type}]" if param.is_spread else param.py_type
    )


def _field_assignment(name: str, py_type: str, cfg: TranslationConfig) -> str:
    if not cfg.emit_type_hints:
        return name
    return f"{name}: {py_type}"

"""Class and method emission for the rule-based skeleton translator."""

from __future__ import annotations

from collections.abc import Iterable

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_fields import (
    _class_field_java_types,
    _class_field_types,
    _class_fields,
    _collect_declared_type_fields,
    _collect_declared_type_java_fields,
    _constructor_assigned_fields,
    _field_assignment,
    _instance_field_names,
    _translate_fields,
    field_infos_from_declaration,
)
from j2py.translate.class_fields import (
    _instance_field_types as _instance_field_types,
)
from j2py.translate.class_model import (
    TYPE_DECLARATION_NODES,
    FieldInfo,
    ParameterInfo,
    _modifiers,
)
from j2py.translate.comments import (
    is_comment,
    is_javadoc_comment,
    translate_comment,
    translate_javadoc_docstring,
)
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
from j2py.translate.rules.types import translate_type
from j2py.translate.statements import (
    class_uses_synchronized_this,
    instance_lock_init_line,
    translate_body,
)

__all__ = [
    "FieldInfo",
    "ParameterInfo",
    "field_infos_from_declaration",
    "top_level_classes",
    "translate_class",
]

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


def top_level_classes(root: JavaNode) -> list[JavaNode]:
    return [child for child in root.named_children if child.type in TYPE_DECLARATION_NODES]


def translate_class(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    inherited_class_field_types: dict[str, str] | None = None,
    inherited_class_field_java_types: dict[str, str] | None = None,
    inherited_declared_type_fields: dict[str, dict[str, str]] | None = None,
    inherited_declared_type_java_fields: dict[str, dict[str, str]] | None = None,
    static_field_aliases: dict[str, str] | None = None,
    static_method_imports: dict[str, str] | None = None,
    docstring_lines: list[str] | None = None,
    outer_self_alias: str | None = None,
    requires_outer_self: bool = False,
) -> list[str]:
    if node.type == "interface_declaration":
        return _translate_interface(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            docstring_lines=docstring_lines,
        )
    if node.type == "enum_declaration":
        return _translate_enum(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
        )
    if node.type == "record_declaration":
        return _translate_record(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            docstring_lines=docstring_lines,
        )
    if node.type == "annotation_type_declaration":
        return _translate_annotation_declaration(
            node,
            cfg,
            diagnostics,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            docstring_lines=docstring_lines,
        )

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
    class_field_java_types = {
        **(inherited_class_field_java_types or {}),
        **_class_field_java_types(fields),
    }
    declared_type_fields = {
        **(inherited_declared_type_fields or {}),
        **_collect_declared_type_fields(node, cfg),
    }
    declared_type_java_fields = {
        **(inherited_declared_type_java_fields or {}),
        **_collect_declared_type_java_fields(node, cfg),
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
    if class_state.needs_instance_lock:
        diagnostics.imports.need_threading()
    modifiers = _modifiers(node)
    if "abstract" in modifiers:
        diagnostics.imports.need_abc()
    lock_init_lines = [instance_lock_init_line()] if class_state.needs_instance_lock else []

    metadata_lines = _type_metadata_comment_lines(node, indent="    ")
    lines = [f"class {class_name}{_base_suffix(node)}:"]
    if docstring_lines:
        lines.extend(docstring_lines)
    lines.extend(metadata_lines)
    static_field_lines, instance_init_lines = _translate_fields(
        node,
        fields,
        assigned_fields,
        instance_field_names,
        cfg,
        diagnostics,
        declared_type_fields=declared_type_fields,
        declared_type_java_fields=declared_type_java_fields,
    )
    nested_outer_capture_names = _nested_type_names_using_qualified_this(body)
    nested_type_lines = _nested_type_lines(
        body,
        cfg,
        diagnostics,
        inherited_class_field_types=class_field_types,
        inherited_class_field_java_types=class_field_java_types,
        inherited_declared_type_fields=declared_type_fields,
        inherited_declared_type_java_fields=declared_type_java_fields,
        static_field_aliases=static_field_aliases or {},
        static_method_imports=static_method_imports or {},
        outer_capture_names=nested_outer_capture_names,
    )
    has_constructor = any(member.type == "constructor_declaration" for member in members)
    needs_synthetic_init = (
        (bool(instance_init_lines) or class_state.needs_instance_lock or requires_outer_self)
        and not has_constructor
    )

    if (
        not members
        and not static_field_lines
        and not instance_init_lines
        and not nested_type_lines
        and not needs_synthetic_init
    ):
        if not docstring_lines and not metadata_lines:
            lines.append("    pass")
        return lines

    if static_field_lines:
        if docstring_lines or metadata_lines:
            lines.append("")
        lines.extend(static_field_lines)

    if needs_synthetic_init:
        if static_field_lines or docstring_lines or metadata_lines:
            lines.append("")
        init_params = "self, _outer_self: object" if requires_outer_self else "self"
        lines.append(f"    def __init__({init_params}) -> None:")
        if requires_outer_self:
            lines.append("        self._outer_self = _outer_self")
        lines.extend(lock_init_lines)
        lines.extend(instance_init_lines)

    if nested_type_lines:
        if static_field_lines or needs_synthetic_init or docstring_lines or metadata_lines:
            lines.append("")
        lines.extend(nested_type_lines)

    member_docstrings = _member_docstrings(body, cfg)
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
                    class_field_java_types=class_field_java_types,
                    declared_type_fields=declared_type_fields,
                    declared_type_java_fields=declared_type_java_fields,
                    class_methods=class_method_names,
                    static_field_aliases=static_field_aliases or {},
                    static_method_imports=static_method_imports or {},
                    pre_body_lines=(
                        lock_init_lines + instance_init_lines
                        if group[0].type == "constructor_declaration"
                        else []
                    ),
                    class_state=class_state,
                    docstring_lines=_docstring_for_group(group, member_docstrings),
                    inner_class_names_requiring_outer=nested_outer_capture_names,
                ),
            )
            continue

        member = group[0]
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
            class_field_types=class_field_types,
            class_field_java_types=class_field_java_types,
            declared_type_fields=declared_type_fields,
            declared_type_java_fields=declared_type_java_fields,
            class_methods=class_method_names,
            static_field_aliases=static_field_aliases or {},
            static_method_imports=static_method_imports or {},
            allow_local_helpers=True,
            class_state=class_state,
            outer_self_alias=outer_self_alias,
            inner_class_names_requiring_outer=nested_outer_capture_names,
        )
        pre_body_lines = (
            lock_init_lines + instance_init_lines
            if member.type == "constructor_declaration"
            else []
        )
        lines.extend(
            _translate_method(
                member,
                ctx,
                pre_body_lines=pre_body_lines,
                docstring_lines=member_docstrings.get(_node_key(member)),
            )
        )

    if class_body_needs_pass(lines):
        lines.append("    pass")

    return lines


def _translate_interface(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    docstring_lines: list[str] | None = None,
) -> list[str]:
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
    class_method_names = _member_method_names(methods, cfg)
    nested_type_lines = _nested_type_lines(
        body,
        cfg,
        diagnostics,
        inherited_class_field_types={},
        inherited_class_field_java_types={},
        inherited_declared_type_fields={},
        inherited_declared_type_java_fields={},
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
    )
    sealed_alias_lines = _sealed_type_alias_lines(node, body, class_name, indent="    ")

    lines = [f"class {class_name}(Protocol):"]
    if docstring_lines:
        lines.extend(docstring_lines)
    metadata_lines = _type_metadata_comment_lines(node, indent="    ")
    lines.extend(metadata_lines)
    wrote_member = bool(docstring_lines or metadata_lines)
    if nested_type_lines:
        if wrote_member:
            lines.append("")
        lines.extend(nested_type_lines)
        wrote_member = True
    if sealed_alias_lines:
        if wrote_member:
            lines.append("")
        lines.extend(sealed_alias_lines)
        wrote_member = True
    for method in methods:
        if wrote_member:
            lines.append("")
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
                class_field_java_types={},
                class_methods=class_method_names,
                static_field_aliases=static_field_aliases,
                static_method_imports=static_method_imports,
                allow_local_helpers=True,
            )
            lines.extend(_translate_method(method, ctx, supported_reason=reason))
            wrote_member = True
            continue

        diagnostics.record(method, supported=True, reason="translated abstract interface method")
        params = _parameter_infos(method, cfg)
        return_type = _return_type(method, cfg)
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(return_type)
            for param in params:
                diagnostics.imports.need_type_annotation(param.py_type)
        signature = _signature(
            _member_python_name(method),
            params,
            return_type=return_type,
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
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated enum declaration")
    diagnostics.imports.need_enum()
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
    class_field_java_types = _class_field_java_types(fields)
    declared_type_fields = _collect_declared_type_fields(node, cfg)
    declared_type_java_fields = _collect_declared_type_java_fields(node, cfg)
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
        lines.extend(
            _translate_enum_constant(
                constant,
                cfg,
                diagnostics,
                static_field_aliases=static_field_aliases,
                static_method_imports=static_method_imports,
            )
        )

    for field in fields:
        diagnostics.record(field.node, supported=True, reason="translated enum field declaration")
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(field.py_type)
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
                    class_field_java_types=class_field_java_types,
                    declared_type_fields=declared_type_fields,
                    declared_type_java_fields=declared_type_java_fields,
                    static_field_aliases=static_field_aliases,
                    static_method_imports=static_method_imports,
                    pre_body_lines=[],
                ),
            )
            continue
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
            class_field_types=class_field_types,
            class_field_java_types=class_field_java_types,
            declared_type_fields=declared_type_fields,
            declared_type_java_fields=declared_type_java_fields,
            static_field_aliases=static_field_aliases,
            static_method_imports=static_method_imports,
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
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
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
    arg_ctx.static_field_aliases = dict(static_field_aliases)
    arg_ctx.static_method_imports = dict(static_method_imports)
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
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    docstring_lines: list[str] | None = None,
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated record declaration")
    diagnostics.imports.need_dataclass()
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    params = _parameter_infos(node, cfg)
    for param in params:
        diagnostics.imports.need_type_annotation(param.py_type)

    lines = ["@dataclass(frozen=True)", f"class {class_name}:"]
    if docstring_lines:
        lines.extend(docstring_lines)
    metadata_lines = _type_metadata_comment_lines(node, indent="    ")
    lines.extend(metadata_lines)
    if not params:
        if not docstring_lines and not metadata_lines:
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
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    docstring_lines: list[str] | None = None,
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

    diagnostics.imports.need_dataclass()
    lines.extend(["@dataclass(frozen=True)", f"class {class_name}:"])
    if docstring_lines:
        lines.extend(docstring_lines)

    body = node.child_by_field("body")
    member_lines: list[str] = []
    if body is not None:
        for member in body.named_children:
            if member.type == "annotation_type_element_declaration":
                member_lines.append(
                    _translate_annotation_element(
                        member,
                        cfg,
                        diagnostics,
                        static_field_aliases=static_field_aliases,
                        static_method_imports=static_method_imports,
                    )
                )
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
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
) -> str:
    type_node = _annotation_element_type_node(node)
    name_node = _annotation_element_name_node(node)
    if type_node is None or name_node is None:
        diagnostics.record(node, supported=False, reason="malformed annotation element")
        return "    # TODO(j2py): malformed annotation element"

    _record_annotation_element_modifiers(node, diagnostics)

    py_name = translate_field_name(name_node.text, snake_case=cfg.snake_case_fields)
    py_type = _annotation_element_py_type(type_node, cfg)
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(py_type)
    default_node = _annotation_element_default_node(node)
    if default_node is None:
        diagnostics.record(node, supported=True, reason="translated annotation element")
        if cfg.emit_type_hints:
            return f"    {py_name}: {py_type}"
        return f"    {py_name}"

    default_value = _annotation_element_default(
        default_node,
        cfg,
        diagnostics,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
    )
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
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
) -> str | None:
    if default_node.type == "element_value_array_initializer":
        values: list[str] = []
        for child in default_node.named_children:
            scalar = _annotation_scalar_default(
                child,
                cfg,
                diagnostics,
                static_field_aliases=static_field_aliases,
                static_method_imports=static_method_imports,
            )
            if scalar is None:
                return None
            values.append(scalar)
        if not values:
            return "()"
        if len(values) == 1:
            return f"({values[0]},)"
        return f"({', '.join(values)})"

    return _annotation_scalar_default(
        default_node,
        cfg,
        diagnostics,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
    )


def _annotation_scalar_default(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
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
        ctx.static_field_aliases = dict(static_field_aliases)
        ctx.static_method_imports = dict(static_method_imports)
        translated = translate_expression(node, ctx)
        if translated.startswith("__j2py_todo__"):
            return None
        return translated

    ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics)
    ctx.static_field_aliases = dict(static_field_aliases)
    ctx.static_method_imports = dict(static_method_imports)
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
    inherited_class_field_java_types: dict[str, str],
    inherited_declared_type_fields: dict[str, dict[str, str]],
    inherited_declared_type_java_fields: dict[str, dict[str, str]],
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    outer_capture_names: set[str] | None = None,
) -> list[str]:
    if body is None:
        return []

    lines: list[str] = []
    pending_docstring: list[str] | None = None
    capture_names = outer_capture_names or set()
    for child in body.named_children:
        if is_javadoc_comment(child):
            pending_docstring = _javadoc_docstring(child, cfg, indent="    ")
            continue
        if child.type not in TYPE_DECLARATION_NODES:
            if not is_comment(child):
                pending_docstring = None
            continue
        if lines:
            lines.append("")
        child_lines = translate_class(
            child,
            cfg,
            diagnostics,
            inherited_class_field_types=inherited_class_field_types,
            inherited_class_field_java_types=inherited_class_field_java_types,
            inherited_declared_type_fields=inherited_declared_type_fields,
            inherited_declared_type_java_fields=inherited_declared_type_java_fields,
            static_field_aliases=static_field_aliases,
            static_method_imports=static_method_imports,
            docstring_lines=pending_docstring,
            outer_self_alias=(
                "self._outer_self"
                if _type_name(child) in capture_names and child.type == "class_declaration"
                else None
            ),
            requires_outer_self=(
                _type_name(child) in capture_names and child.type == "class_declaration"
            ),
        )
        pending_docstring = None
        lines.extend(f"    {line}" if line else line for line in child_lines)
    return lines


def _type_metadata_comment_lines(node: JavaNode, *, indent: str) -> list[str]:
    modifiers = _modifiers(node)
    lines: list[str] = []
    permits = _permits_names(node)
    if "sealed" in modifiers:
        if permits:
            lines.append(f"{indent}# sealed: permits {', '.join(permits)}")
        else:
            lines.append(f"{indent}# sealed")
    if "non-sealed" in modifiers:
        lines.append(f"{indent}# non-sealed")
    if "final" in modifiers and node.type == "class_declaration":
        lines.append(f"{indent}# final")
    return lines


def _sealed_type_alias_lines(
    node: JavaNode,
    body: JavaNode | None,
    class_name: str,
    *,
    indent: str,
) -> list[str]:
    permits = _permits_names(node)
    if not permits or body is None:
        return []
    nested_names = _direct_nested_type_names(body)
    if any(name not in nested_names for name in permits):
        return []
    alias = f"{class_name}Permitted"
    return [f"{indent}{alias} = {' | '.join(permits)}  # sealed permitted subclasses"]


def _permits_names(node: JavaNode) -> list[str]:
    permits_node = first_child_by_type(node, "permits")
    if permits_node is None:
        return []
    names: list[str] = []
    for child in permits_node.walk():
        if child.type in {"type_identifier", "scoped_type_identifier", "identifier"}:
            names.append(translate_class_name(child.text))
    return names


def _direct_nested_type_names(body: JavaNode) -> set[str]:
    names: set[str] = set()
    for child in body.named_children:
        if child.type not in TYPE_DECLARATION_NODES:
            continue
        type_name = _type_name(child)
        if type_name is not None:
            names.add(type_name)
    return names


def _nested_type_names_using_qualified_this(body: JavaNode | None) -> set[str]:
    if body is None:
        return set()
    names: set[str] = set()
    for child in body.named_children:
        if child.type != "class_declaration":
            continue
        type_name = _type_name(child)
        if type_name is not None and _uses_qualified_this(child):
            names.add(type_name)
    return names


def _type_name(node: JavaNode) -> str | None:
    name_node = node.child_by_field("name")
    if name_node is None:
        return None
    return translate_class_name(name_node.text)


def _uses_qualified_this(node: JavaNode) -> bool:
    if node.type == "field_access":
        children = node.named_children
        if (
            len(children) == 2
            and children[0].type
            in {"identifier", "type_identifier", "scoped_identifier", "scoped_type_identifier"}
            and children[1].type == "this"
        ):
            return True
    return any(_uses_qualified_this(child) for child in node.named_children)


def _base_suffix(node: JavaNode) -> str:
    bases: list[str] = []
    superclass = node.child_by_field("superclass")
    if superclass is not None:
        type_node = first_child_by_type(superclass, "type_identifier", "scoped_type_identifier")
        if type_node is not None:
            bases.append(translate_class_name(type_node.text))
    if "abstract" in _modifiers(node):
        bases.append("ABC")
    if not bases:
        return ""
    return f"({', '.join(bases)})"


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


_NodeKey = tuple[int, int, int, int, str]


def _node_key(node: JavaNode) -> _NodeKey:
    location = node.location
    return (
        location.line,
        location.column,
        location.end_line,
        location.end_column,
        node.type,
    )


def _member_docstrings(body: JavaNode | None, cfg: TranslationConfig) -> dict[_NodeKey, list[str]]:
    if body is None:
        return {}
    docstrings: dict[_NodeKey, list[str]] = {}
    pending: list[str] | None = None
    for child in body.named_children:
        if is_javadoc_comment(child):
            pending = _javadoc_docstring(child, cfg, indent="        ")
            continue
        if child.type in {"constructor_declaration", "method_declaration"}:
            if pending:
                docstrings[_node_key(child)] = pending
            pending = None
            continue
        if not is_comment(child):
            pending = None
    return docstrings


def _docstring_for_group(
    group: list[JavaNode],
    docstrings: dict[_NodeKey, list[str]],
) -> list[str] | None:
    for member in reversed(group):
        docstring = docstrings.get(_node_key(member))
        if docstring:
            return docstring
    return None


def _javadoc_docstring(
    node: JavaNode,
    cfg: TranslationConfig,
    *,
    indent: str,
) -> list[str] | None:
    if not cfg.emit_line_comments:
        return None
    if not cfg.emit_docstrings:
        return translate_comment(node, indent=indent)
    return translate_javadoc_docstring(node, indent=indent)


def _translate_method(
    node: JavaNode,
    ctx: TranslationContext,
    *,
    unsupported_reason: str | None = None,
    pre_body_lines: list[str] | None = None,
    decorator_lines: list[str] | None = None,
    def_line_suffix: str = "",
    supported_reason: str | None = None,
    docstring_lines: list[str] | None = None,
) -> list[str]:
    _record_annotation_diagnostics(node, ctx.cfg, ctx.diagnostics)
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
    ctx.in_instance_method = not is_static

    name_node = node.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = (
        "__init__"
        if is_constructor
        else translate_method_name(raw_name, snake_case=ctx.cfg.snake_case_methods)
    )
    return_type = "None" if is_constructor else _return_type(node, ctx.cfg)
    if ctx.cfg.emit_type_hints:
        ctx.diagnostics.imports.need_type_annotation(return_type)
    params = _params(node, ctx)
    if not is_static:
        params.insert(0, "self")

    if unsupported_reason is not None:
        return [f"    # TODO(j2py): {unsupported_reason}", "    pass"]

    lines: list[str] = list(decorator_lines or [])
    if is_static:
        lines.append("    @staticmethod")
    if is_abstract:
        ctx.diagnostics.imports.need_abc()
        lines.append("    @abstractmethod")
    returns = f" -> {return_type}" if ctx.cfg.emit_type_hints else ""
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
    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    if docstring_lines:
        lines.extend(docstring_lines)
        if pre_body_lines or body_lines != ["        pass"]:
            lines.append("")
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
    class_field_java_types: dict[str, str] | None = None,
    declared_type_fields: dict[str, dict[str, str]] | None = None,
    declared_type_java_fields: dict[str, dict[str, str]] | None = None,
    class_methods: set[str] | None = None,
    static_field_aliases: dict[str, str] | None = None,
    static_method_imports: dict[str, str] | None = None,
    pre_body_lines: list[str],
    class_state: ClassTranslationState | None = None,
    docstring_lines: list[str] | None = None,
    inner_class_names_requiring_outer: set[str] | None = None,
) -> list[str]:
    from j2py.translate.overloads import translate_overloaded_members

    return translate_overloaded_members(
        members,
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_field_types=class_field_types,
        class_field_java_types=class_field_java_types,
        declared_type_fields=declared_type_fields,
        declared_type_java_fields=declared_type_java_fields,
        class_methods=class_methods,
        static_field_aliases=static_field_aliases,
        static_method_imports=static_method_imports,
        pre_body_lines=pre_body_lines,
        class_state=class_state,
        docstring_lines=docstring_lines,
        inner_class_names_requiring_outer=inner_class_names_requiring_outer or set(),
    )


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


def _method_body(node: JavaNode) -> JavaNode | None:
    return node.child_by_field("body") or first_child_by_type(node, "block", "constructor_body")


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
        java_type = type_node.text if type_node is not None else "Object"
        py_type = translate_type(java_type, cfg)
        infos.append(
            ParameterInfo(
                raw_name=raw_name,
                py_name=translate_field_name(raw_name, snake_case=cfg.snake_case_fields),
                py_type=py_type.removeprefix("*"),
                java_type=java_type,
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
            ctx.diagnostics.imports.need_type_annotation(param.py_type)
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
    ctx.variable_java_types[param.raw_name] = param.java_type

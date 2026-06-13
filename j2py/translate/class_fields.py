"""Field extraction and field-initializer emission for class translation."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_model import TYPE_DECLARATION_NODES, FieldInfo, _modifiers
from j2py.translate.comments import is_comment, is_javadoc_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import java_default_value, translate_type
from j2py.translate.statements import translate_body


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


def _class_field_java_types(fields: list[FieldInfo]) -> dict[str, str]:
    return {field.name: field.java_type for field in fields}


def _collect_declared_type_fields(
    class_node: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    return {
        type_name: {name: field.py_type for name, field in fields.items()}
        for type_name, fields in _collect_declared_type_field_maps(class_node, cfg).items()
    }


def _collect_declared_type_java_fields(
    class_node: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, dict[str, str]]:
    return {
        type_name: {name: field.java_type for name, field in fields.items()}
        for type_name, fields in _collect_declared_type_field_maps(class_node, cfg).items()
    }


def _collect_declared_type_field_maps(
    class_node: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, dict[str, FieldInfo]]:
    by_type: dict[str, dict[str, FieldInfo]] = {}

    def add_type(type_node: JavaNode) -> None:
        name_node = type_node.child_by_field("name")
        if name_node is None:
            return
        by_type[name_node.text] = {
            field.name: field for field in _class_fields(type_node, cfg)
        }
        body = type_node.child_by_field("body")
        if body is None:
            return
        for child in body.named_children:
            if child.type in TYPE_DECLARATION_NODES:
                add_type(child)

    add_type(class_node)
    return by_type


def _translate_fields(
    class_node: JavaNode,
    fields: list[FieldInfo],
    assigned_fields: set[str],
    instance_field_names: set[str],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    declared_type_fields: dict[str, dict[str, str]] | None = None,
    declared_type_java_fields: dict[str, dict[str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    body = class_node.child_by_field("body")
    if body is None:
        return [], []

    static_lines: list[str] = []
    instance_init_lines: list[str] = []
    type_fields = declared_type_fields or {}
    type_java_fields = declared_type_java_fields or {}
    static_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
        class_field_types=_class_field_types(fields),
        class_field_java_types=_class_field_java_types(fields),
        declared_type_fields=type_fields,
        declared_type_java_fields=type_java_fields,
    )
    instance_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
        class_field_types=_class_field_types(fields),
        class_field_java_types=_class_field_java_types(fields),
        declared_type_fields=type_fields,
        declared_type_java_fields=type_java_fields,
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
            if cfg.emit_type_hints:
                diagnostics.imports.need_type_annotation(field.py_type)
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
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(annotation)
        target = _field_assignment(f"self.{field.py_name}", annotation, cfg)
        instance_init_lines.append(f"        {target} = {default_value}")

    supported_members = {
        "field_declaration",
        "constructor_declaration",
        "method_declaration",
        "static_initializer",
        *TYPE_DECLARATION_NODES,
    }
    body_children = body.named_children
    for index, child in enumerate(body_children):
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
            if is_javadoc_comment(child) and _javadoc_is_consumed_by_declaration(
                body_children,
                index,
            ):
                continue
            if not cfg.emit_line_comments:
                continue
            static_lines.extend(translate_comment(child, indent="    "))
            continue
        diagnostics.record(child, supported=False, reason=f"unsupported class member {child.type}")
        static_lines.append(f"    # TODO(j2py): unsupported class member {child.type}")

    return static_lines, instance_init_lines


def _javadoc_is_consumed_by_declaration(children: list[JavaNode], index: int) -> bool:
    for child in children[index + 1:]:
        if is_comment(child):
            continue
        return child.type in {
            "constructor_declaration",
            "method_declaration",
            *TYPE_DECLARATION_NODES,
        }
    return False


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
        if ctx.cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(annotation)
        return [
            f"    {_field_assignment(field.py_name, annotation, ctx.cfg)} = {default_value}",
        ]

    diagnostics.record(field.node, supported=True, reason="translated static field declaration")
    if ctx.cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(field.py_type)
    return [
        f"    {_field_assignment(field.py_name, field.py_type, ctx.cfg)} = "
        f"{translate_expression(field.initializer, ctx)}",
    ]


def _field_assignment(name: str, py_type: str, cfg: TranslationConfig) -> str:
    if not cfg.emit_type_hints:
        return name
    return f"{name}: {py_type}"

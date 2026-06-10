"""Class and method emission for the rule-based skeleton translator."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import class_body_needs_pass, first_child_by_type
from j2py.translate.rules.naming import (
    translate_class_name,
    translate_field_name,
    translate_method_name,
)
from j2py.translate.rules.types import translate_type
from j2py.translate.statements import translate_body


@dataclass(frozen=True)
class FieldInfo:
    node: JavaNode
    name: str
    py_name: str
    py_type: str
    is_static: bool
    initializer: JavaNode | None


def top_level_classes(root: JavaNode) -> list[JavaNode]:
    return [
        child
        for child in root.named_children
        if child.type in {"class_declaration", "interface_declaration", "enum_declaration"}
    ]


def translate_class(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
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

    lines = [f"class {class_name}:"]
    static_field_lines, instance_init_lines = _translate_fields(
        node,
        fields,
        assigned_fields,
        instance_field_names,
        cfg,
        diagnostics,
    )
    overloaded_names = _overloaded_member_names(members)
    has_constructor = any(member.type == "constructor_declaration" for member in members)
    needs_synthetic_init = bool(instance_init_lines) and not has_constructor

    if not members and not static_field_lines and not instance_init_lines:
        lines.append("    pass")
        return lines

    lines.extend(static_field_lines)

    if needs_synthetic_init:
        if static_field_lines:
            lines.append("")
        lines.append("    def __init__(self) -> None:")
        lines.extend(instance_init_lines)

    for member in members:
        lines.append("")
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
        )
        overloaded_name = _member_python_name(member)
        unsupported_reason = (
            f"overloaded method {overloaded_name} requires LLM completion"
            if overloaded_name in overloaded_names
            else None
        )
        pre_body_lines = instance_init_lines if member.type == "constructor_declaration" else []
        lines.extend(
            _translate_method(
                member,
                ctx,
                unsupported_reason=unsupported_reason,
                pre_body_lines=pre_body_lines,
            ),
        )

    if class_body_needs_pass(lines):
        lines.append("    pass")

    return lines


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
                    py_name=translate_field_name(name_node.text),
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


def _translate_fields(
    class_node: JavaNode,
    fields: list[FieldInfo],
    assigned_fields: set[str],
    instance_field_names: set[str],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> tuple[list[str], list[str]]:
    body = class_node.child_by_field("body")
    if body is None:
        return [], []

    static_lines: list[str] = []
    instance_init_lines: list[str] = []
    static_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
    )
    instance_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
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
                f"        self.{field.py_name}: {field.py_type} = "
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
            supported=False,
            reason="instance field declaration without initializer needs default review",
        )
        instance_init_lines.append(
            f"        # TODO(j2py): verify default value for field {field.py_name}",
        )
        instance_init_lines.append(f"        self.{field.py_name}: {field.py_type} | None = None")

    supported_members = {"field_declaration", "constructor_declaration", "method_declaration"}
    for child in body.named_children:
        if child.type in supported_members:
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
            supported=False,
            reason="static field declaration without initializer needs default review",
        )
        return [
            f"    # TODO(j2py): verify default value for static field {field.py_name}",
            f"    {field.py_name}: {field.py_type} | None = None",
        ]

    diagnostics.record(field.node, supported=True, reason="translated static field declaration")
    return [
        f"    {field.py_name}: {field.py_type} = "
        f"{translate_expression(field.initializer, ctx)}",
    ]


def _overloaded_member_names(members: list[JavaNode]) -> set[str]:
    counts: dict[str, int] = {}
    for member in members:
        name = _member_python_name(member)
        counts[name] = counts.get(name, 0) + 1
    return {name for name, count in counts.items() if count > 1}


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
) -> list[str]:
    supported = node.type in {"constructor_declaration", "method_declaration"}
    ctx.diagnostics.record(
        node,
        supported=supported and unsupported_reason is None,
        reason=unsupported_reason or "translated method declaration",
    )

    is_constructor = node.type == "constructor_declaration"
    is_static = "static" in _modifiers(node)
    ctx.in_instance_method = not is_static

    name_node = node.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = "__init__" if is_constructor else translate_method_name(raw_name)
    return_type = "None" if is_constructor else _return_type(node, ctx.cfg)
    params = _params(node, ctx)
    if not is_static:
        params.insert(0, "self")

    if unsupported_reason is not None:
        return [f"    # TODO(j2py): {unsupported_reason}", "    pass"]

    lines: list[str] = []
    if is_static:
        lines.append("    @staticmethod")
    lines.append(f"    def {py_name}({', '.join(params)}) -> {return_type}:")

    body = node.child_by_field("body")
    if body is None:
        body = first_child_by_type(node, "block", "constructor_body")

    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    lines.extend(pre_body_lines or [])
    lines.extend(body_lines)
    return lines


def _modifiers(node: JavaNode) -> set[str]:
    modifiers: set[str] = set()
    for modifier_node in node.children_by_type("modifiers"):
        modifiers.update(modifier_node.text.split())
    return modifiers


def _return_type(node: JavaNode, cfg: TranslationConfig) -> str:
    type_node = node.child_by_field("type")
    if type_node is None:
        return "None"
    return translate_type(type_node.text, cfg)


def _params(node: JavaNode, ctx: TranslationContext) -> list[str]:
    params_node = node.child_by_field("parameters")
    if params_node is None:
        return []

    params: list[str] = []
    for param in params_node.find_all("formal_parameter", "spread_parameter"):
        type_node = param.child_by_field("type")
        name_node = param.child_by_field("name")
        raw_name = name_node.text if name_node is not None else "_"
        py_name = translate_field_name(raw_name)
        py_type = translate_type(type_node.text if type_node is not None else "Object", ctx.cfg)
        ctx.param_names.add(raw_name)
        params.append(f"{py_name}: {py_type}")
    return params

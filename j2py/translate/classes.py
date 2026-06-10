"""Class and method emission for the rule-based skeleton translator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment, translate_comment
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

TYPE_DECLARATION_NODES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}


@dataclass(frozen=True)
class FieldInfo:
    node: JavaNode
    name: str
    py_name: str
    py_type: str
    is_static: bool
    initializer: JavaNode | None


@dataclass(frozen=True)
class ParameterInfo:
    raw_name: str
    py_name: str
    py_type: str


def top_level_classes(root: JavaNode) -> list[JavaNode]:
    return [child for child in root.named_children if child.type in TYPE_DECLARATION_NODES]


def translate_class(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    if node.type == "interface_declaration":
        return _translate_interface(node, cfg, diagnostics)
    if node.type == "enum_declaration":
        return _translate_enum(node, diagnostics)
    if node.type == "record_declaration":
        return _translate_record(node, cfg, diagnostics)
    if node.type == "annotation_type_declaration":
        return _translate_annotation_placeholder(node, diagnostics)

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
    instance_field_types = _instance_field_types(fields)
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

    lines = [f"class {class_name}{_base_suffix(node)}:"]
    static_field_lines, instance_init_lines = _translate_fields(
        node,
        fields,
        assigned_fields,
        instance_field_names,
        cfg,
        diagnostics,
    )
    nested_type_lines = _nested_type_lines(body, cfg, diagnostics)
    has_constructor = any(member.type == "constructor_declaration" for member in members)
    needs_synthetic_init = bool(instance_init_lines) and not has_constructor

    if not members and not static_field_lines and not instance_init_lines and not nested_type_lines:
        lines.append("    pass")
        return lines

    lines.extend(static_field_lines)

    if needs_synthetic_init:
        if static_field_lines:
            lines.append("")
        lines.append("    def __init__(self) -> None:")
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
                    class_field_types=instance_field_types,
                    pre_body_lines=(
                        instance_init_lines if group[0].type == "constructor_declaration" else []
                    ),
                ),
            )
            continue

        member = group[0]
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
            class_field_types=instance_field_types,
        )
        pre_body_lines = instance_init_lines if member.type == "constructor_declaration" else []
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
    methods = [] if body is None else body.find_all("method_declaration")

    lines = [f"class {class_name}(Protocol):"]
    wrote_member = False
    for method in methods:
        _record_annotation_diagnostics(method, cfg, diagnostics)
        diagnostics.record(method, supported=True, reason="translated interface method")
        name = _member_python_name(method)
        params = _parameter_infos(method, cfg)
        return_type = _return_type(method, cfg)
        signature = _signature(
            name,
            params,
            return_type=return_type,
            include_self=True,
            emit_type_hints=cfg.emit_type_hints,
        )
        lines.append(f"    {signature}: ...")
        wrote_member = True

    if not wrote_member:
        lines.append("    pass")
    return lines


def _translate_enum(node: JavaNode, diagnostics: TranslationDiagnostics) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated enum declaration")
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    body = node.child_by_field("body")
    constants = (
        []
        if body is None
        else [child for child in body.named_children if child.type == "enum_constant"]
    )

    lines = [f"class {class_name}(Enum):"]
    if not constants:
        lines.append("    pass")
        return lines
    for constant in constants:
        diagnostics.record(constant, supported=True, reason="translated enum constant")
        lines.append(f"    {constant.text} = {constant.text!r}")
    return lines


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


def _translate_annotation_placeholder(
    node: JavaNode,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(
        node,
        supported=False,
        reason="annotation type declaration requires manual translation",
    )
    name_node = node.child_by_field("name")
    class_name = translate_class_name(name_node.text if name_node is not None else "Unknown")
    return [
        f"class {class_name}:",
        "    # TODO(j2py): unsupported annotation type declaration",
        "    pass",
    ]


def _nested_type_lines(
    body: JavaNode | None,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    if body is None:
        return []

    lines: list[str] = []
    for child in body.named_children:
        if child.type not in TYPE_DECLARATION_NODES:
            continue
        if lines:
            lines.append("")
        child_lines = translate_class(child, cfg, diagnostics)
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
        class_field_types=_instance_field_types(fields),
    )
    instance_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
        class_field_types=_instance_field_types(fields),
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
            supported=False,
            reason="instance field declaration without initializer needs default review",
        )
        instance_init_lines.append(
            f"        # TODO(j2py): verify default value for field {field.py_name}",
        )
        target = _field_assignment(f"self.{field.py_name}", f"{field.py_type} | None", cfg)
        instance_init_lines.append(f"        {target} = None")

    supported_members = {
        "field_declaration",
        "constructor_declaration",
        "method_declaration",
        *TYPE_DECLARATION_NODES,
    }
    for child in body.named_children:
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
            supported=False,
            reason="static field declaration without initializer needs default review",
        )
        return [
            f"    # TODO(j2py): verify default value for static field {field.py_name}",
            f"    {_field_assignment(field.py_name, f'{field.py_type} | None', ctx.cfg)} = None",
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
) -> list[str]:
    _record_annotation_diagnostics(node, ctx.cfg, ctx.diagnostics)
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

    lines: list[str] = []
    if is_static:
        lines.append("    @staticmethod")
    returns = f" -> {return_type}" if ctx.cfg.emit_type_hints else ""
    lines.append(f"    def {py_name}({', '.join(params)}){returns}:")

    body = node.child_by_field("body")
    if body is None:
        body = first_child_by_type(node, "block", "constructor_body")

    body_lines = translate_body(body, ctx, indent="        ") if body else ["        pass"]
    lines.extend(pre_body_lines or [])
    lines.extend(body_lines)
    return lines


def _translate_overloaded_members(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_fields: set[str],
    class_field_types: dict[str, str] | None = None,
    pre_body_lines: list[str],
) -> list[str]:
    name = _member_python_name(members[0])
    for member in members:
        _record_annotation_diagnostics(member, cfg, diagnostics)

    field_types = class_field_types or {f: "object" for f in class_fields}

    if members[0].type == "constructor_declaration":
        merged_constructor = _merged_constructor_overload(
            members,
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=class_fields,
            class_field_types=field_types,
            pre_body_lines=pre_body_lines,
        )
        if merged_constructor is not None:
            return merged_constructor

    merged_method = _merged_method_overload(
        members,
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=class_fields,
        class_field_types=field_types,
    )
    if merged_method is not None:
        return merged_method

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


def _merged_constructor_overload(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_fields: set[str],
    class_field_types: dict[str, str],
    pre_body_lines: list[str],
) -> list[str] | None:
    implementation = _constructor_implementation_candidate(members, cfg)
    if implementation is None:
        return None

    params = _parameter_infos(implementation, cfg)
    defaults: dict[str, str] = {}
    for member in members:
        if member == implementation:
            continue
        forwarded_args = _constructor_delegation_args(member, cfg)
        if forwarded_args is None or len(forwarded_args) != len(params):
            return None
        for param, arg in zip(params, forwarded_args, strict=True):
            defaults[param.py_name] = arg

    diagnostics.record(
        implementation,
        supported=True,
        reason="translated overloaded constructor implementation",
    )
    for member in members:
        if member != implementation:
            diagnostics.record(member, supported=True, reason="translated constructor delegation")

    ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics, class_fields=class_fields)
    ctx.class_field_types = dict(class_field_types)
    ctx.in_instance_method = True
    for param in params:
        ctx.param_names.add(param.raw_name)
        ctx.variable_types[param.raw_name] = param.py_type

    lines = _overload_stubs(members, cfg)
    signature = _signature(
        "__init__",
        params,
        return_type="None",
        include_self=True,
        defaults=defaults,
        emit_type_hints=cfg.emit_type_hints,
    )
    lines.append(f"    {signature}:")
    lines.extend(pre_body_lines)
    body = _method_body(implementation)
    lines.extend(translate_body(body, ctx, indent="        ") if body else ["        pass"])
    return lines


def _merged_method_overload(
    members: list[JavaNode],
    *,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    class_fields: set[str],
    class_field_types: dict[str, str],
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
        )
        for index in range(len(param_sets[0]))
    ]
    return_type = _union_types(_return_type(member, cfg) for member in members)

    for member in members:
        diagnostics.record(member, supported=True, reason="translated overloaded method")

    ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics, class_fields=class_fields)
    ctx.class_field_types = dict(class_field_types)
    ctx.in_instance_method = not is_static
    for param in merged_params:
        ctx.param_names.add(param.raw_name)
        ctx.variable_types[param.raw_name] = param.py_type

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
    lines.extend(translate_body(body, ctx, indent="        ") if body else ["        pass"])
    return lines


def _constructor_implementation_candidate(
    members: list[JavaNode],
    cfg: TranslationConfig,
) -> JavaNode | None:
    candidates = [
        member
        for member in members
        if _constructor_delegation_args(member, cfg) is None
        and len(_parameter_infos(member, cfg)) > 0
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def _constructor_delegation_args(member: JavaNode, cfg: TranslationConfig) -> list[str] | None:
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
    if args_node is None:
        return []
    ctx = TranslationContext(cfg=cfg, diagnostics=TranslationDiagnostics())
    return [translate_expression(arg, ctx) for arg in args_node.named_children]


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
    rendered.extend(
        (f"{param.py_name}: {param.py_type}" if emit_type_hints else param.py_name)
        + (f" = {defaults[param.py_name]}" if param.py_name in defaults else "")
        for param in params
    )
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
        f"{param.py_name}: {param.py_type}" for param in _parameter_infos(member, cfg)
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
        type_node = param.child_by_field("type")
        name_node = param.child_by_field("name")
        raw_name = name_node.text if name_node is not None else "_"
        infos.append(
            ParameterInfo(
                raw_name=raw_name,
                py_name=translate_field_name(raw_name, snake_case=cfg.snake_case_fields),
                py_type=translate_type(type_node.text if type_node is not None else "Object", cfg),
            ),
        )
    return infos


def _params(node: JavaNode, ctx: TranslationContext) -> list[str]:
    params: list[str] = []
    for param in _parameter_infos(node, ctx.cfg):
        ctx.param_names.add(param.raw_name)
        ctx.variable_types[param.raw_name] = param.py_type
        if ctx.cfg.emit_type_hints:
            params.append(f"{param.py_name}: {param.py_type}")
        else:
            params.append(param.py_name)
    return params


def _field_assignment(name: str, py_type: str, cfg: TranslationConfig) -> str:
    if not cfg.emit_type_hints:
        return name
    return f"{name}: {py_type}"

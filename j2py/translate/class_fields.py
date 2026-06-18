"""Field extraction and field-initializer emission for class translation."""

from __future__ import annotations

import re

from j2py.config.loader import TranslationConfig
from j2py.framework import FrameworkTransformResult
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_comment_lines, record_annotation_diagnostics
from j2py.translate.bean_validation import bean_validation_field, is_required_field
from j2py.translate.class_members import iter_type_declarations
from j2py.translate.class_model import TYPE_DECLARATION_NODES, FieldInfo, _modifiers
from j2py.translate.comments import is_comment, is_javadoc_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.expressions import translate_expression
from j2py.translate.framework_dispatch import resolve_field
from j2py.translate.name_resolution import NameResolver
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import java_default_value, translate_type
from j2py.translate.spring_settings import spring_value_comment_lines, spring_value_field
from j2py.translate.sqlalchemy_model import sqlalchemy_model_field_lines
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

    for type_node in iter_type_declarations(class_node):
        name_node = type_node.child_by_field("name")
        if name_node is None:
            continue
        by_type[name_node.text] = {field.name: field for field in _class_fields(type_node, cfg)}
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
    class_static_methods: set[str] | None = None,
    containing_class_name: str | None = None,
    enclosing_static_dispatch: dict[str, str] | None = None,
    name_resolver: NameResolver | None = None,
    field_transforms: list[FrameworkTransformResult] | None = None,
    pydantic_model: bool = False,
    sqlalchemy_model: bool = False,
    sqlalchemy_entity_table_names: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    body = class_node.child_by_field("body")
    if body is None:
        return [], []

    static_lines: list[str] = []
    instance_init_lines: list[str] = []
    type_fields = declared_type_fields or {}
    type_java_fields = declared_type_java_fields or {}
    resolver = name_resolver or NameResolver.empty()
    static_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
        class_field_types=_class_field_types(fields),
        class_field_java_types=_class_field_java_types(fields),
        declared_type_fields=type_fields,
        declared_type_java_fields=type_java_fields,
        class_static_methods=class_static_methods or set(),
        containing_class_name=containing_class_name,
        enclosing_static_dispatch=enclosing_static_dispatch or {},
        name_resolver=resolver,
        allow_local_helpers=True,
    )
    instance_ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        class_fields=instance_field_names,
        class_field_types=_class_field_types(fields),
        class_field_java_types=_class_field_java_types(fields),
        declared_type_fields=type_fields,
        declared_type_java_fields=type_java_fields,
        class_static_methods=class_static_methods or set(),
        containing_class_name=containing_class_name,
        enclosing_static_dispatch=enclosing_static_dispatch or {},
        name_resolver=resolver,
        in_instance_method=True,
        allow_local_helpers=True,
    )

    transforms = (
        field_transforms
        if field_transforms is not None
        else [
            resolve_field(field, cfg, diagnostics, indent="    " if field.is_static else "        ")
            for field in fields
        ]
    )
    transform_index = 0
    supported_members = {
        "field_declaration",
        "constructor_declaration",
        "method_declaration",
        "static_initializer",
        "block",
        *TYPE_DECLARATION_NODES,
    }
    body_children = body.named_children
    for index, child in enumerate(body_children):
        if child.type == "field_declaration":
            for field in field_infos_from_declaration(child, cfg):
                transform = transforms[transform_index]
                transform_index += 1
                if field.is_static:
                    static_lines.extend(
                        _translate_static_field(field, static_ctx, diagnostics, transform)
                    )
                elif pydantic_model:
                    static_lines.extend(
                        _translate_pydantic_model_field(
                            field,
                            static_ctx,
                            diagnostics,
                            transform,
                        )
                    )
                elif sqlalchemy_model:
                    static_lines.extend(
                        sqlalchemy_model_field_lines(
                            field,
                            diagnostics,
                            entity_table_names=sqlalchemy_entity_table_names or {},
                        )
                    )
                else:
                    instance_init_lines.extend(
                        _translate_instance_field(
                            field,
                            assigned_fields,
                            instance_ctx,
                            diagnostics,
                            transform,
                        ),
                    )
            continue
        if child.type == "static_initializer":
            static_lines.extend(_translate_static_initializer(child, static_ctx, diagnostics))
            continue
        if child.type == "block":
            instance_init_lines.extend(
                _translate_instance_initializer(child, instance_ctx, diagnostics),
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


def _translate_pydantic_model_field(
    field: FieldInfo,
    ctx: TranslationContext,
    diagnostics: TranslationDiagnostics,
    transform: FrameworkTransformResult,
) -> list[str]:
    helper_lines, default_value, annotation = _pydantic_field_default_and_annotation(field, ctx)
    value = spring_value_field(field)
    if value is not None and field.initializer is None:
        default_value = value.default_value
        annotation = (
            field.py_type if default_value != "None" else _nullable_annotation(field.py_type)
        )
    validation = bean_validation_field(field, default_value=default_value)
    if validation is not None:
        diagnostics.record(
            field.node,
            supported=True,
            reason="translated Bean Validation field to Pydantic Field",
        )
        diagnostics.imports.need_line("from pydantic import Field")
        if ctx.cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(annotation)
        validation_lines = helper_lines
        if value is not None:
            validation_lines.extend(spring_value_comment_lines(field, value, indent="    "))
        validation_lines.extend(f"    {comment}" for comment in validation.comment_lines)
        validation_lines.extend(transform.prefix_lines)
        validation_lines.append(
            f"    {_field_assignment(field.py_name, annotation, ctx.cfg)} = "
            f"{validation.expression}",
        )
        return validation_lines

    if not transform.handled:
        record_annotation_diagnostics(
            field.node,
            ctx.cfg,
            diagnostics,
            target_kind="field",
            target_name=field.py_name,
            skip_names={"Value"} if value is not None else None,
        )
    if ctx.cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(field.py_type)
    lines: list[str] = []
    if not transform.handled:
        if value is not None:
            lines.extend(spring_value_comment_lines(field, value, indent="    "))
        lines.extend(
            annotation_comment_lines(
                field.node,
                ctx.cfg,
                indent="    ",
                skip_names={"Value"} if value is not None else None,
            )
        )
    lines.extend(transform.prefix_lines)
    if field.initializer is not None:
        diagnostics.record(
            field.node,
            supported=True,
            reason="translated Pydantic model field initializer",
        )
        lines.extend(helper_lines)
        lines.append(
            f"    {_field_assignment(field.py_name, annotation, ctx.cfg)} = {default_value}"
        )
        return lines

    diagnostics.record(
        field.node,
        supported=True,
        reason="translated Java default value for Pydantic model field",
    )
    default_value = (
        value.default_value if value is not None else java_default_value(field.java_type)
    )
    annotation = field.py_type if default_value != "None" else _nullable_annotation(field.py_type)
    if ctx.cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(annotation)
    lines.append(f"    {_field_assignment(field.py_name, annotation, ctx.cfg)} = {default_value}")
    return lines


def _pydantic_field_default_and_annotation(
    field: FieldInfo,
    ctx: TranslationContext,
) -> tuple[list[str], str, str]:
    helper_lines: list[str] = []
    if field.initializer is not None:
        default_value = translate_expression(field.initializer, ctx)
        _extend_with_local_helpers(helper_lines, ctx, base_indent="    ")
        return helper_lines, default_value, field.py_type

    java_default = java_default_value(field.java_type)
    if java_default != "None":
        return helper_lines, java_default, field.py_type
    if is_required_field(field):
        return helper_lines, "...", field.py_type
    return helper_lines, "None", _nullable_annotation(field.py_type)


def _nullable_annotation(py_type: str) -> str:
    if py_type == "None" or "None" in {part.strip() for part in py_type.split("|")}:
        return py_type
    return f"{py_type} | None"


def _translate_instance_field(
    field: FieldInfo,
    assigned_fields: set[str],
    ctx: TranslationContext,
    diagnostics: TranslationDiagnostics,
    transform: FrameworkTransformResult,
) -> list[str]:
    value = spring_value_field(field)
    if not transform.handled:
        record_annotation_diagnostics(
            field.node,
            ctx.cfg,
            diagnostics,
            target_kind="field",
            target_name=field.py_name,
            skip_names={"Value"} if value is not None else None,
        )
    if transform.init_params:
        init_param = transform.init_params[0]
        if len(transform.init_params) > 1:
            diagnostics.warn(
                field.node,
                reason=(
                    f"framework plugin returned multiple init_params for field "
                    f"{field.py_name}; only the first one ({init_param.py_name}) "
                    "will be assigned"
                ),
            )
        diagnostics.record(
            field.node,
            supported=True,
            reason=(
                "translated framework plugin constructor injection field"
                if transform.handled
                else "translated annotation-mapped constructor injection field"
            ),
        )
        if ctx.cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(field.py_type)
        target = _field_assignment(f"self.{field.py_name}", field.py_type, ctx.cfg)
        injection_lines: list[str] = []
        if not transform.handled:
            if value is not None:
                injection_lines.extend(spring_value_comment_lines(field, value, indent="        "))
            injection_lines.extend(
                annotation_comment_lines(
                    field.node,
                    ctx.cfg,
                    indent="        ",
                    skip_names={"Value"} if value is not None else None,
                )
            )
        injection_lines.extend(transform.prefix_lines)
        injection_lines.append(f"        {target} = {init_param.py_name}")
        return injection_lines

    if field.initializer is not None:
        diagnostics.record(
            field.node,
            supported=True,
            reason="translated instance field initializer",
        )
        if ctx.cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(field.py_type)
        initializer = translate_expression(field.initializer, ctx)
        initializer_lines: list[str] = []
        _extend_with_local_helpers(initializer_lines, ctx, base_indent="        ")
        if initializer_lines:
            initializer_lines.append("")
        if not transform.handled:
            if value is not None:
                initializer_lines.extend(
                    spring_value_comment_lines(field, value, indent="        ")
                )
            initializer_lines.extend(
                annotation_comment_lines(
                    field.node,
                    ctx.cfg,
                    indent="        ",
                    skip_names={"Value"} if value is not None else None,
                ),
            )
        initializer_lines.extend(transform.prefix_lines)
        initializer_lines.append(
            f"        {_field_assignment(f'self.{field.py_name}', field.py_type, ctx.cfg)} = "
            f"{initializer}",
        )
        return initializer_lines

    if field.name in assigned_fields:
        diagnostics.record(
            field.node,
            supported=True,
            reason="represented field declaration via constructor assignment",
        )
        return []

    diagnostics.record(
        field.node,
        supported=True,
        reason="translated Java default value for instance field",
    )
    default_value = (
        value.default_value if value is not None else java_default_value(field.java_type)
    )
    annotation = field.py_type if default_value != "None" else f"{field.py_type} | None"
    if ctx.cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(annotation)
    target = _field_assignment(f"self.{field.py_name}", annotation, ctx.cfg)
    default_lines = []
    if not transform.handled:
        if value is not None:
            default_lines.extend(spring_value_comment_lines(field, value, indent="        "))
        default_lines.extend(
            annotation_comment_lines(
                field.node,
                ctx.cfg,
                indent="        ",
                skip_names={"Value"} if value is not None else None,
            )
        )
    default_lines.extend(transform.prefix_lines)
    default_lines.append(f"        {target} = {default_value}")
    return default_lines


def _translate_static_initializer(
    node: JavaNode,
    ctx: TranslationContext,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated static initializer")
    static_body = first_child_by_type(node, "block")
    body_lines = (
        translate_body(
            static_body,
            ctx,
            indent="    ",
        )
        if static_body is not None
        else ["    pass"]
    )
    lines: list[str] = []
    _extend_with_local_helpers(lines, ctx, base_indent="    ")
    lines.extend(body_lines)
    return lines


def _translate_instance_initializer(
    node: JavaNode,
    ctx: TranslationContext,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    diagnostics.record(node, supported=True, reason="translated instance initializer")
    body_lines = translate_body(node, ctx, indent="        ")
    lines: list[str] = []
    _extend_with_local_helpers(lines, ctx, base_indent="        ")
    lines.extend(body_lines)
    return lines


def _javadoc_is_consumed_by_declaration(children: list[JavaNode], index: int) -> bool:
    for child in children[index + 1 :]:
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
    transform: FrameworkTransformResult,
) -> list[str]:
    value = spring_value_field(field)
    if not transform.handled:
        record_annotation_diagnostics(
            field.node,
            ctx.cfg,
            diagnostics,
            target_kind="field",
            target_name=field.py_name,
            skip_names={"Value"} if value is not None else None,
        )
    if field.initializer is None:
        diagnostics.record(
            field.node,
            supported=True,
            reason="translated Java default value for static field",
        )
        default_value = (
            value.default_value if value is not None else java_default_value(field.java_type)
        )
        annotation = field.py_type if default_value != "None" else f"{field.py_type} | None"
        if ctx.cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(annotation)
        default_lines: list[str] = []
        if not transform.handled:
            if value is not None:
                default_lines.extend(spring_value_comment_lines(field, value, indent="    "))
            default_lines.extend(
                annotation_comment_lines(
                    field.node,
                    ctx.cfg,
                    indent="    ",
                    skip_names={"Value"} if value is not None else None,
                )
            )
        default_lines.extend(transform.prefix_lines)
        default_lines.append(
            f"    {_field_assignment(field.py_name, annotation, ctx.cfg)} = {default_value}"
        )
        return default_lines

    diagnostics.record(field.node, supported=True, reason="translated static field declaration")
    if ctx.cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(field.py_type)
    initializer = translate_expression(field.initializer, ctx)
    lines: list[str] = []
    if not transform.handled:
        if value is not None:
            lines.extend(spring_value_comment_lines(field, value, indent="    "))
        lines.extend(
            annotation_comment_lines(
                field.node,
                ctx.cfg,
                indent="    ",
                skip_names={"Value"} if value is not None else None,
            )
        )
    lines.extend(transform.prefix_lines)
    _extend_with_local_helpers(lines, ctx, base_indent="    ")
    if _initializer_references_enclosing_class(initializer, ctx):
        # A static field whose initializer references the class being defined cannot run
        # in the class body (the class name is not yet bound). Defer it to a module-level
        # assignment emitted after the class block. Local helpers, if any, stay in body.
        diagnostics.deferred_module_lines.append(
            f"{ctx.containing_class_name}.{field.py_name} = {initializer}",
        )
        return lines
    lines.append(
        f"    {_field_assignment(field.py_name, field.py_type, ctx.cfg)} = {initializer}",
    )
    return lines


def _initializer_references_enclosing_class(initializer: str, ctx: TranslationContext) -> bool:
    """True when a static initializer references the class currently being defined.

    Such a forward self-reference (e.g. ``NULL = ImmutablePair(None, None)``) raises
    ``NameError`` if emitted inside the class body, so it must be deferred to a
    post-class assignment.
    """
    name = ctx.containing_class_name
    if not name:
        return False
    return re.search(rf"\b{re.escape(name)}\b", initializer) is not None


def _extend_with_local_helpers(
    lines: list[str],
    ctx: TranslationContext,
    *,
    base_indent: str,
) -> None:
    if not ctx.pending_local_helpers:
        return
    for helper in ctx.pending_local_helpers:
        if lines and helper:
            lines.append("")
        lines.extend(_reindent_local_helper_lines(helper, target_base_indent=base_indent))
    ctx.pending_local_helpers.clear()


def _reindent_local_helper_lines(helper: list[str], *, target_base_indent: str) -> list[str]:
    source_base_indent = "        "
    indent_shift = len(target_base_indent) - len(source_base_indent)
    reindented: list[str] = []
    for line in helper:
        if not line.strip():
            reindented.append(line)
            continue
        leading_spaces = len(line) - len(line.lstrip(" "))
        new_leading = max(0, leading_spaces + indent_shift)
        reindented.append(" " * new_leading + line.lstrip(" "))
    return reindented


def _field_assignment(name: str, py_type: str, cfg: TranslationConfig) -> str:
    if not cfg.emit_type_hints:
        return name
    return f"{name}: {py_type}"

"""Object-creation and anonymous-class expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.class_model import FieldInfo
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_class_name, translate_method_name
from j2py.translate.rules.types import java_default_value


def _translate_object_creation(node: JavaNode, ctx: TranslationContext) -> str:
    type_node = node.child_by_field("type")
    args_node = first_child_by_type(node, "argument_list")
    body_node = first_child_by_type(node, "class_body")
    args = translate_expression(args_node, ctx) if args_node is not None else ""
    raw_type = type_node.text if type_node is not None else "object"
    base_type = raw_type.split("<", 1)[0]

    if body_node is not None:
        return _translate_anonymous_class(node, body_node, base_type, args, ctx)

    collection_literals = {
        "ArrayList": "[]",
        "LinkedList": "[]",
        "Vector": "[]",
        "HashMap": "{}",
        "LinkedHashMap": "{}",
        "TreeMap": "{}",
        "Hashtable": "{}",
        "HashSet": "set()",
        "LinkedHashSet": "set()",
        "TreeSet": "set()",
    }
    collection_copy_constructors = {
        "ArrayList": "list",
        "LinkedList": "list",
        "Vector": "list",
        "HashMap": "dict",
        "LinkedHashMap": "dict",
        "TreeMap": "dict",
        "Hashtable": "dict",
        "HashSet": "set",
        "LinkedHashSet": "set",
        "TreeSet": "set",
    }
    if base_type in collection_literals:
        if not args:
            return collection_literals[base_type]
        arg_nodes = [
            child for child in args_node.named_children if not is_comment(child)
        ] if args_node is not None else []
        if len(arg_nodes) == 1:
            copied = translate_expression(arg_nodes[0], ctx)
            return f"{collection_copy_constructors[base_type]}({copied})"
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="non-empty collection constructor requires LLM completion",
        )
        return f"__j2py_todo__({node.text!r})"

    return f"{translate_class_name(base_type)}({args})"


def _translate_anonymous_class(
    node: JavaNode,
    body_node: JavaNode,
    base_type: str,
    args: str,
    ctx: TranslationContext,
) -> str:
    from j2py.translate.class_fields import (
        _instance_field_names,
        _instance_field_types,
        field_infos_from_declaration,
    )

    if not ctx.allow_local_helpers:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="anonymous class requires local helper scope",
        )
        return f"__j2py_todo__({node.text!r})"

    helper_id = len(ctx.pending_local_helpers) + 1
    helper_name = f"_J2pyAnonymous{helper_id}"
    base_name = translate_class_name(base_type)
    helper_lines = [f"        class {helper_name}({base_name}):"]

    instance_fields: list[FieldInfo] = []
    methods: list[JavaNode] = []
    for member in body_node.named_children:
        if is_comment(member):
            ctx.diagnostics.warn(member, reason="preserved comment")
            if ctx.cfg.emit_line_comments:
                helper_lines.extend(translate_comment(member, indent="            "))
            continue
        if member.type == "field_declaration":
            for field in field_infos_from_declaration(member, ctx.cfg):
                if field.is_static:
                    ctx.diagnostics.record(
                        member,
                        supported=False,
                        reason="unsupported anonymous class static field_declaration",
                    )
                    helper_lines.append(
                        "            # TODO(j2py): unsupported anonymous class static field",
                    )
                    continue
                ctx.diagnostics.record(
                    member,
                    supported=True,
                    reason="translated anonymous class instance field",
                )
                instance_fields.append(field)
            continue
        if member.type == "method_declaration":
            methods.append(member)
            continue
        ctx.diagnostics.record(
            member,
            supported=False,
            reason=f"unsupported anonymous class member {member.type}",
        )
        helper_lines.append(
            f"            # TODO(j2py): unsupported anonymous class member {member.type}",
        )

    instance_field_names = _instance_field_names(instance_fields)
    instance_field_types = _instance_field_types(instance_fields)
    wrote_member = False
    if instance_fields:
        helper_lines.extend(
            _anonymous_helper_init_lines(instance_fields, ctx),
        )
        wrote_member = True

    for method in methods:
        if wrote_member:
            helper_lines.append("")
        helper_lines.extend(
            _anonymous_method_lines(
                method,
                ctx,
                instance_field_names=instance_field_names,
                instance_field_types=instance_field_types,
            ),
        )
        wrote_member = True

    if not wrote_member:
        helper_lines.append("            pass")

    ctx.pending_local_helpers.append(helper_lines)
    ctx.diagnostics.record(
        node,
        supported=True,
        reason="translated anonymous class as local helper class",
    )
    ctx.diagnostics.warn(
        node,
        reason="anonymous class translated as local helper; verify captured outer this references",
    )
    return f"{helper_name}({args})"


def _anonymous_helper_init_lines(
    fields: list[FieldInfo],
    ctx: TranslationContext,
) -> list[str]:
    from j2py.translate.class_fields import (
        _class_field_types,
        _field_assignment,
        _instance_field_names,
    )

    lines = ["            def __init__(self):"]
    field_ctx = TranslationContext(
        cfg=ctx.cfg,
        diagnostics=ctx.diagnostics,
        class_fields=_instance_field_names(fields),
        class_field_types=_class_field_types(fields),
        declared_type_fields=dict(ctx.declared_type_fields),
        in_instance_method=True,
    )
    for field in fields:
        if field.initializer is not None:
            assignment = (
                f"{_field_assignment(f'self.{field.py_name}', field.py_type, ctx.cfg)} = "
                f"{translate_expression(field.initializer, field_ctx)}"
            )
        else:
            default_value = java_default_value(field.java_type)
            annotation = field.py_type if default_value != "None" else f"{field.py_type} | None"
            assignment = (
                f"{_field_assignment(f'self.{field.py_name}', annotation, ctx.cfg)} = "
                f"{default_value}"
            )
        lines.append(f"                {assignment}")
    return lines


def _anonymous_method_lines(
    method: JavaNode,
    ctx: TranslationContext,
    *,
    instance_field_names: set[str],
    instance_field_types: dict[str, str],
) -> list[str]:
    from j2py.translate.class_model import _modifiers
    from j2py.translate.classes import (
        _method_body,
        _parameter_infos,
        _record_annotation_diagnostics,
        _return_type,
    )
    from j2py.translate.statements import translate_body

    _record_annotation_diagnostics(method, ctx.cfg, ctx.diagnostics)
    ctx.diagnostics.record(
        method,
        supported=True,
        reason="translated anonymous class method",
    )

    name_node = method.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = translate_method_name(raw_name, snake_case=ctx.cfg.snake_case_methods)
    is_static = "static" in _modifiers(method)
    params = _parameter_infos(method, ctx.cfg)
    rendered_params = [
        f"{param.py_name}: {param.py_type}" if ctx.cfg.emit_type_hints else param.py_name
        for param in params
    ]
    if not is_static:
        rendered_params.insert(0, "self")
    returns = f" -> {_return_type(method, ctx.cfg)}" if ctx.cfg.emit_type_hints else ""
    lines: list[str] = []
    if is_static:
        lines.append("            @staticmethod")
    lines.append(f"            def {py_name}({', '.join(rendered_params)}){returns}:")

    previous_param_names = set(ctx.param_names)
    previous_types = dict(ctx.variable_types)
    previous_class_fields = set(ctx.class_fields)
    previous_class_field_types = dict(ctx.class_field_types)
    previous_in_instance_method = ctx.in_instance_method
    previous_allow_helpers = ctx.allow_local_helpers
    for param in params:
        ctx.param_names.add(param.raw_name)
        ctx.variable_types[param.raw_name] = param.py_type
    ctx.class_fields = instance_field_names
    ctx.class_field_types = instance_field_types
    ctx.in_instance_method = not is_static
    ctx.allow_local_helpers = True
    start_index = len(ctx.pending_local_helpers)
    try:
        body = _method_body(method)
        body_lines = (
            translate_body(body, ctx, indent="                ")
            if body
            else ["                pass"]
        )
        nested_helpers = ctx.pending_local_helpers[start_index:]
        del ctx.pending_local_helpers[start_index:]
        for helper in nested_helpers:
            lines.append("")
            lines.extend(f"        {line}" if line else line for line in helper)
        lines.extend(body_lines)
    finally:
        ctx.param_names = previous_param_names
        ctx.variable_types = previous_types
        ctx.class_fields = previous_class_fields
        ctx.class_field_types = previous_class_field_types
        ctx.in_instance_method = previous_in_instance_method
        ctx.allow_local_helpers = previous_allow_helpers

    return lines

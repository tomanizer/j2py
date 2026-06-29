"""Object-creation and anonymous-class expression helpers."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.class_members import references_enclosing_instance_fields, uses_qualified_this
from j2py.translate.class_model import FieldInfo
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext
from j2py.translate.expr_access import request_type_import
from j2py.translate.expressions import translate_expression
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import translate_class_name, translate_method_name
from j2py.translate.rules.types import java_default_value


def _request_constructor_import(class_name: str, ctx: TranslationContext) -> None:
    """Request a function-local import for same-package sibling constructor types.

    Only acts on cross-file ``"package_type"`` references so that
    ``new SiblingClass(...)`` inside a method body uses a function-local import,
    breaking base↔derived circular import cycles (issue #325).  Types declared in
    the same compilation unit (same Python module) need no import and are skipped.
    Qualified names (``Outer.Inner``) are also skipped — they are inner-class
    references that the object-creation caller already handles without an import.
    Explicitly-imported types were never auto-imported via the object-creation path;
    this function preserves that existing behaviour.
    """
    # Qualified names (inner-class constructors like ``new Outer.Inner()``) cannot
    # produce valid Python import statements and need no sibling import anyway.
    if "." in class_name:
        return
    from j2py.translate.name_resolution import scope_from_context
    from j2py.translate.rules.naming import translate_class_name

    py_name = translate_class_name(class_name)
    # Same-compilation-unit types (other classes in this file) need no import.
    if py_name in ctx.name_resolver.bindings.compilation_unit_types:
        return
    resolved = ctx.name_resolver.resolve_identifier(class_name, scope_from_context(ctx))
    if resolved.import_line and resolved.kind == "package_type":
        request_type_import(resolved.import_line, resolved.kind, ctx)


def _translate_object_creation(node: JavaNode, ctx: TranslationContext) -> str:
    type_node = node.child_by_field("type")
    args_node = first_child_by_type(node, "argument_list")
    body_node = first_child_by_type(node, "class_body")
    args = translate_expression(args_node, ctx) if args_node is not None else ""
    raw_type = type_node.text if type_node is not None else "object"
    base_type = raw_type.split("<", 1)[0]

    if body_node is not None:
        return _translate_anonymous_class(node, body_node, base_type, args, ctx)

    py_base_type = translate_class_name(base_type)
    _request_constructor_import(base_type, ctx)
    if py_base_type in ctx.local_class_names_requiring_outer:
        if ctx.in_instance_method:
            constructor_args = f"self, {args}" if args else "self"
            return f"{py_base_type}({constructor_args})"
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="qualified outer this in static context requires manual capture",
        )
        return f"__j2py_todo__({node.text!r})"
    if ctx.containing_class_name and py_base_type in ctx.nested_class_names:
        if ctx.in_instance_method and py_base_type in ctx.inner_class_names_requiring_outer:
            constructor_args = f"self, {args}" if args else "self"
            return f"self.{py_base_type}({constructor_args})"
        return f"{ctx.containing_class_name}.{py_base_type}({args})"

    # Bare java.lang.Object → Python object(). This is the canonical dedicated-lock
    # idiom (`private final Object lock = new Object();`); `Object` has no Python
    # name, so the fallback would emit an undefined `Object()` and raise NameError.
    if base_type in {"Object", "java.lang.Object"} and not args:
        return "object()"

    if base_type in {"String", "java.lang.String"}:
        arg_nodes = (
            [child for child in args_node.named_children if not is_comment(child)]
            if args_node is not None
            else []
        )
        if len(arg_nodes) == 1:
            value = translate_expression(arg_nodes[0], ctx)
            ctx.diagnostics.imports.need_line("from j2py_runtime import _j2py_string_from_value")
            return f"_j2py_string_from_value({value})"
        if len(arg_nodes) == 2:
            value = translate_expression(arg_nodes[0], ctx)
            charset = translate_expression(arg_nodes[1], ctx)
            ctx.diagnostics.imports.need_line("from j2py_runtime import _j2py_string_from_value")
            return f"_j2py_string_from_value({value}, {charset})"
        return "str()"

    if base_type in {"StringBuilder", "java.lang.StringBuilder"}:
        ctx.diagnostics.imports.need_line("from j2py_runtime import StringBuilder")
        return f"StringBuilder({args})"

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
        arg_nodes = (
            [child for child in args_node.named_children if not is_comment(child)]
            if args_node is not None
            else []
        )
        if len(arg_nodes) == 1:
            copied = translate_expression(arg_nodes[0], ctx)
            return f"{collection_copy_constructors[base_type]}({copied})"
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="non-empty collection constructor requires LLM completion",
        )
        return f"__j2py_todo__({node.text!r})"

    return f"{py_base_type}({args})"


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
    base_clause = "" if base_name in {"Comparator", "Object"} else f"({base_name})"
    current_field_reference = references_enclosing_instance_fields(
        body_node,
        ctx.class_fields,
    )
    inherited_field_reference = references_enclosing_instance_fields(
        body_node,
        ctx.enclosing_class_fields,
    )
    needs_outer_self = (
        uses_qualified_this(body_node) or current_field_reference or inherited_field_reference
    )
    reuse_outer_self_alias = inherited_field_reference and not current_field_reference
    outer_self_alias: str | None
    if needs_outer_self and reuse_outer_self_alias and ctx.outer_self_alias is not None:
        outer_self_alias = ctx.outer_self_alias
        bind_outer_self_alias = False
    else:
        outer_self_alias = "_outer_self" if needs_outer_self and ctx.in_instance_method else None
        bind_outer_self_alias = outer_self_alias is not None
    if needs_outer_self and outer_self_alias is None:
        ctx.diagnostics.record(
            node,
            supported=False,
            reason="qualified outer this in static context requires manual capture",
        )
        return f"__j2py_todo__({node.text!r})"

    helper_lines: list[str] = []
    if bind_outer_self_alias:
        helper_lines.extend([f"        {outer_self_alias} = self", ""])
    helper_lines.append(f"        class {helper_name}{base_clause}:")

    instance_fields: list[FieldInfo] = []
    static_fields: list[FieldInfo] = []
    init_members: list[FieldInfo | JavaNode] = []
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
                        supported=True,
                        reason="translated anonymous class static field",
                    )
                    static_fields.append(field)
                    continue
                ctx.diagnostics.record(
                    member,
                    supported=True,
                    reason="translated anonymous class instance field",
                )
                instance_fields.append(field)
                init_members.append(field)
            continue
        if member.type == "block":
            ctx.diagnostics.record(
                member,
                supported=True,
                reason="translated anonymous class member block",
            )
            init_members.append(member)
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
    instance_field_java_types = {field.name: field.java_type for field in instance_fields}
    enclosing_field_names = (ctx.class_fields | ctx.enclosing_class_fields) - instance_field_names
    enclosing_field_types = {
        name: py_type
        for name, py_type in {**ctx.enclosing_class_field_types, **ctx.class_field_types}.items()
        if name in enclosing_field_names
    }
    enclosing_field_java_types = {
        name: java_type
        for name, java_type in {
            **ctx.enclosing_class_field_java_types,
            **ctx.class_field_java_types,
        }.items()
        if name in enclosing_field_names
    }
    from j2py.translate.class_methods import class_method_return_types

    previous_return_types = dict(ctx.class_method_return_types)
    ctx.class_method_return_types = class_method_return_types(methods, ctx.cfg)
    wrote_member = False
    if static_fields:
        for field in static_fields:
            helper_lines.extend(_anonymous_static_field_lines(field, ctx, helper_name))
        wrote_member = True

    if init_members:
        if wrote_member:
            helper_lines.append("")
        helper_lines.extend(
            _anonymous_helper_init_lines(
                instance_fields,
                ctx,
                init_members=init_members,
                extra_self_dispatch_methods=_receiverless_method_invocation_names(
                    init_members, ctx
                ),
                enclosing_field_names=enclosing_field_names,
                enclosing_field_types=enclosing_field_types,
                enclosing_field_java_types=enclosing_field_java_types,
                outer_self_alias=outer_self_alias,
            ),
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
                instance_field_java_types=instance_field_java_types,
                enclosing_field_names=enclosing_field_names,
                enclosing_field_types=enclosing_field_types,
                enclosing_field_java_types=enclosing_field_java_types,
                outer_self_alias=outer_self_alias,
            ),
        )
        wrote_member = True

    method_names: set[str] = set()
    for method in methods:
        name_node = method.child_by_field("name")
        if name_node is not None:
            method_names.add(
                translate_method_name(
                    name_node.text,
                    snake_case=ctx.cfg.snake_case_methods,
                ),
            )
    has_next_name = translate_method_name("hasNext", snake_case=ctx.cfg.snake_case_methods)
    next_name = translate_method_name("next", snake_case=ctx.cfg.snake_case_methods)
    if base_name == "Iterator" and {has_next_name, next_name} <= method_names:
        if wrote_member:
            helper_lines.append("")
        helper_lines.extend(_anonymous_iterator_protocol_lines(has_next_name, next_name))
        wrote_member = True

    ctx.class_method_return_types = previous_return_types

    if not wrote_member:
        helper_lines.append("            pass")

    ctx.pending_local_helpers.append(helper_lines)
    ctx.diagnostics.record(
        node,
        supported=True,
        reason="translated anonymous class as local helper class",
    )
    return f"{helper_name}({args})"


def _anonymous_iterator_protocol_lines(
    has_next_name: str,
    next_name: str,
    *,
    def_indent: str = "            ",
    body_indent: str = "                ",
) -> list[str]:
    return [
        f"{def_indent}def __iter__(self):",
        f"{body_indent}return self",
        "",
        f"{def_indent}def __next__(self):",
        f"{body_indent}if not self.{has_next_name}():",
        f"{body_indent}    raise StopIteration",
        f"{body_indent}return self.{next_name}()",
    ]


def _anonymous_helper_init_lines(
    fields: list[FieldInfo],
    ctx: TranslationContext,
    *,
    init_members: list[FieldInfo | JavaNode] | None = None,
    extra_self_dispatch_methods: set[str] | None = None,
    enclosing_field_names: set[str] | None = None,
    enclosing_field_types: dict[str, str] | None = None,
    enclosing_field_java_types: dict[str, str] | None = None,
    outer_self_alias: str | None = None,
    def_indent: str = "            ",
    body_indent: str = "                ",
) -> list[str]:
    from j2py.translate.class_fields import (
        _class_field_types,
        _field_assignment,
        _instance_field_names,
    )
    from j2py.translate.statements import translate_body

    lines = [f"{def_indent}def __init__(self):"]
    field_ctx = TranslationContext(
        cfg=ctx.cfg,
        diagnostics=ctx.diagnostics,
        class_fields=_instance_field_names(fields),
        class_field_types=_class_field_types(fields),
        class_field_java_types={field.name: field.java_type for field in fields},
        declared_type_fields=dict(ctx.declared_type_fields),
        declared_type_java_fields=dict(ctx.declared_type_java_fields),
        name_resolver=ctx.name_resolver,
        in_instance_method=True,
        outer_self_alias=outer_self_alias,
        enclosing_class_fields=set(enclosing_field_names or set()),
        enclosing_class_field_types=dict(enclosing_field_types or {}),
        enclosing_class_field_java_types=dict(enclosing_field_java_types or {}),
        class_methods=set(ctx.class_methods) | set(extra_self_dispatch_methods or set()),
    )
    for member in init_members or fields:
        if not isinstance(member, FieldInfo):
            start_index = len(field_ctx.pending_local_helpers)
            body_lines = translate_body(member, field_ctx, indent=body_indent)
            nested_helpers = field_ctx.pending_local_helpers[start_index:]
            del field_ctx.pending_local_helpers[start_index:]
            for helper in nested_helpers:
                lines.extend(_anonymous_reindent_helper(helper, target_base_indent=body_indent))
            lines.extend(body_lines)
            continue

        field = member
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
        lines.append(f"{body_indent}{assignment}")
    return lines


def _anonymous_static_field_lines(
    field: FieldInfo,
    ctx: TranslationContext,
    helper_name: str,
    *,
    indent: str = "            ",
) -> list[str]:
    from j2py.translate.class_fields import _field_assignment

    static_ctx = TranslationContext(
        cfg=ctx.cfg,
        diagnostics=ctx.diagnostics,
        class_field_types={field.name: field.py_type},
        class_field_java_types={field.name: field.java_type},
        declared_type_fields=dict(ctx.declared_type_fields),
        declared_type_java_fields=dict(ctx.declared_type_java_fields),
        name_resolver=ctx.name_resolver,
        containing_class_name=helper_name,
    )
    if field.initializer is not None:
        value = translate_expression(field.initializer, static_ctx)
    else:
        value = java_default_value(field.java_type)
    if ctx.cfg.emit_type_hints:
        annotation = field.py_type if value != "None" else f"{field.py_type} | None"
        ctx.diagnostics.imports.need_type_annotation(annotation)
        target = _field_assignment(field.py_name, annotation, ctx.cfg)
    else:
        target = field.py_name

    lines: list[str] = []
    for helper in static_ctx.pending_local_helpers:
        lines.extend(_anonymous_reindent_helper(helper, target_base_indent=indent))
    lines.append(f"{indent}{target} = {value}")
    return lines


def _anonymous_reindent_helper(
    helper_lines: list[str],
    *,
    target_base_indent: str,
) -> list[str]:
    source_base_indent = "        "
    indent_shift = len(target_base_indent) - len(source_base_indent)
    reindented: list[str] = []
    for line in helper_lines:
        if not line.strip():
            reindented.append(line)
            continue
        leading_spaces = len(line) - len(line.lstrip(" "))
        new_leading = max(0, leading_spaces + indent_shift)
        reindented.append(" " * new_leading + line.lstrip(" "))
    return reindented


def _receiverless_method_invocation_names(
    members: list[FieldInfo | JavaNode],
    ctx: TranslationContext,
) -> set[str]:
    names: set[str] = set()
    for member in members:
        if isinstance(member, FieldInfo):
            continue
        for invocation in member.find_all("method_invocation"):
            named = invocation.named_children
            args_node = first_child_by_type(invocation, "argument_list")
            if args_node is None or len(named) < 2:
                continue
            args_index = named.index(args_node)
            if args_index > 1:
                continue
            method_node = named[args_index - 1]
            names.add(
                translate_method_name(method_node.text, snake_case=ctx.cfg.snake_case_methods)
            )
    return names


def _anonymous_method_lines(
    method: JavaNode,
    ctx: TranslationContext,
    *,
    instance_field_names: set[str],
    instance_field_types: dict[str, str],
    instance_field_java_types: dict[str, str],
    enclosing_field_names: set[str],
    enclosing_field_types: dict[str, str],
    enclosing_field_java_types: dict[str, str],
    outer_self_alias: str | None,
    member_indent: str = "            ",
    body_indent: str = "                ",
    nested_helper_indent: str = "        ",
    supported_reason: str = "translated anonymous class method",
) -> list[str]:
    from j2py.translate.annotation_emit import (
        annotation_comment_lines,
        record_annotation_diagnostics,
    )
    from j2py.translate.class_methods import (
        method_body,
        parameter_infos,
        return_type,
    )
    from j2py.translate.class_model import _modifiers
    from j2py.translate.statements import translate_body

    name_node = method.child_by_field("name")
    raw_name = name_node.text if name_node is not None else "unknown"
    py_name = translate_method_name(raw_name, snake_case=ctx.cfg.snake_case_methods)
    record_annotation_diagnostics(
        method,
        ctx.cfg,
        ctx.diagnostics,
        target_kind="method",
        target_name=py_name,
    )
    ctx.diagnostics.record(
        method,
        supported=True,
        reason=supported_reason,
    )

    is_static = "static" in _modifiers(method)
    params = parameter_infos(method, ctx.cfg)
    rendered_params = [
        f"{param.py_name}: {param.py_type}" if ctx.cfg.emit_type_hints else param.py_name
        for param in params
    ]
    if not is_static:
        rendered_params.insert(0, "self")
    returns = f" -> {return_type(method, ctx.cfg)}" if ctx.cfg.emit_type_hints else ""
    lines: list[str] = []
    lines.extend(annotation_comment_lines(method, ctx.cfg, indent=member_indent))
    if is_static:
        lines.append(f"{member_indent}@staticmethod")
    lines.append(f"{member_indent}def {py_name}({', '.join(rendered_params)}){returns}:")

    previous_param_names = set(ctx.param_names)
    previous_local_names = set(ctx.local_names)
    previous_spread_param_names = set(ctx.spread_param_names)
    previous_types = dict(ctx.variable_types)
    previous_java_types = dict(ctx.variable_java_types)
    previous_class_fields = set(ctx.class_fields)
    previous_class_field_types = dict(ctx.class_field_types)
    previous_class_field_java_types = dict(ctx.class_field_java_types)
    previous_enclosing_class_fields = set(ctx.enclosing_class_fields)
    previous_enclosing_class_field_types = dict(ctx.enclosing_class_field_types)
    previous_enclosing_class_field_java_types = dict(ctx.enclosing_class_field_java_types)
    previous_in_instance_method = ctx.in_instance_method
    previous_allow_helpers = ctx.allow_local_helpers
    previous_outer_self_alias = ctx.outer_self_alias
    ctx.local_names = set()
    ctx.param_names = set()
    ctx.spread_param_names = set()
    for param in params:
        ctx.param_names.add(param.raw_name)
        if param.is_spread:
            ctx.spread_param_names.add(param.raw_name)
        ctx.variable_types[param.raw_name] = param.py_type
        ctx.variable_java_types[param.raw_name] = param.java_type
    ctx.class_fields = instance_field_names
    ctx.class_field_types = instance_field_types
    ctx.class_field_java_types = instance_field_java_types
    ctx.enclosing_class_fields = enclosing_field_names
    ctx.enclosing_class_field_types = enclosing_field_types
    ctx.enclosing_class_field_java_types = enclosing_field_java_types
    ctx.in_instance_method = not is_static
    ctx.allow_local_helpers = True
    ctx.outer_self_alias = outer_self_alias
    start_index = len(ctx.pending_local_helpers)
    try:
        body = method_body(method)
        body_lines = (
            translate_body(body, ctx, indent=body_indent) if body else [f"{body_indent}pass"]
        )
        nested_helpers = ctx.pending_local_helpers[start_index:]
        del ctx.pending_local_helpers[start_index:]
        for helper in nested_helpers:
            lines.append("")
            lines.extend(f"{nested_helper_indent}{line}" if line else line for line in helper)
        lines.extend(body_lines)
    finally:
        ctx.param_names = previous_param_names
        ctx.local_names = previous_local_names
        ctx.spread_param_names = previous_spread_param_names
        ctx.variable_types = previous_types
        ctx.variable_java_types = previous_java_types
        ctx.class_fields = previous_class_fields
        ctx.class_field_types = previous_class_field_types
        ctx.class_field_java_types = previous_class_field_java_types
        ctx.enclosing_class_fields = previous_enclosing_class_fields
        ctx.enclosing_class_field_types = previous_enclosing_class_field_types
        ctx.enclosing_class_field_java_types = previous_enclosing_class_field_java_types
        ctx.in_instance_method = previous_in_instance_method
        ctx.allow_local_helpers = previous_allow_helpers
        ctx.outer_self_alias = previous_outer_self_alias

    return lines

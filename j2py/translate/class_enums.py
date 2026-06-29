"""Enum declaration emission for class translation."""

from __future__ import annotations

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_environment import ClassTranslationEnvironment
from j2py.translate.class_fields import (
    _class_field_java_types,
    _class_field_types,
    _collect_declared_type_fields,
    _collect_declared_type_java_fields,
    _field_assignment,
    _instance_field_names,
    _instance_field_types,
    field_infos_from_declaration,
)
from j2py.translate.class_members import (
    group_has_to_string_override,
    member_groups,
    member_method_names,
    member_static_method_names,
    static_instance_collision_static_aliases,
    static_instance_collision_zero_arg_names,
    to_string_dunder_wrapper,
)
from j2py.translate.class_methods import (
    class_method_return_types,
    parameter_infos,
    return_type,
    translate_method,
)
from j2py.translate.class_model import FieldInfo, _modifiers
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.expressions import translate_expression
from j2py.translate.name_resolution import NameResolver
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.naming import (
    translate_class_name,
    translate_field_name,
    translate_method_name,
)
from j2py.translate.rules.types import translate_type


def translate_enum(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    env: ClassTranslationEnvironment | None = None,
) -> list[str]:
    from j2py.translate.classes import translate_overloaded_members

    env = env or ClassTranslationEnvironment()
    static_field_aliases = env.static_field_aliases
    static_method_imports = env.static_method_imports
    name_resolver = env.name_resolver
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
    class_method_names = member_method_names(members, cfg)
    class_static_method_names = member_static_method_names(members, cfg)
    static_instance_aliases = static_instance_collision_static_aliases(members, cfg)
    instance_zero, static_zero = static_instance_collision_zero_arg_names(members, cfg)
    method_return_types = class_method_return_types(members, cfg)

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

    module_prefix: list[str] = []
    constant_body_helpers: list[list[str]] = []
    constant_assignments: list[list[str]] = []
    constants_with_bodies: list[str] = []
    overridden_method_py_names: set[str] = set()
    bodies_map_name = _enum_constant_bodies_map_name(class_name)

    for constant in constants:
        name_node = constant.child_by_field("name") or first_child_by_type(
            constant,
            "identifier",
        )
        constant_name = name_node.text if name_node is not None else constant.text.split("(", 1)[0]
        assignment_lines, helper_lines, overridden = _translate_enum_constant(
            constant,
            cfg,
            diagnostics,
            constant_name=constant_name,
            static_field_aliases=static_field_aliases,
            static_method_imports=static_method_imports,
            name_resolver=name_resolver,
            enum_field_names=instance_field_names,
            enum_field_types=class_field_types,
            enum_field_java_types=class_field_java_types,
        )
        constant_assignments.append(assignment_lines)
        if helper_lines is not None:
            constant_body_helpers.append(helper_lines)
            constants_with_bodies.append(constant_name)
            for raw_name in overridden:
                overridden_method_py_names.add(
                    translate_method_name(raw_name, snake_case=cfg.snake_case_methods),
                )

    for helper_lines in constant_body_helpers:
        module_prefix.extend(helper_lines)
        module_prefix.append("")

    for assignment_lines in constant_assignments:
        lines.extend(assignment_lines)

    if constants_with_bodies:
        body_entries = ", ".join(
            f'"{name}": _J2pyEnumConstant{translate_class_name(name)}'
            for name in constants_with_bodies
        )
        module_prefix.append(f"{bodies_map_name} = {{{body_entries}}}")
        module_prefix.append("")

    for field in fields:
        diagnostics.record(field.node, supported=True, reason="translated enum field declaration")
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(field.py_type)
        lines.append(f"    {_field_assignment(field.py_name, field.py_type, cfg)}")

    for group in member_groups(members):
        lines.append("")
        if len(group) > 1:
            lines.extend(
                translate_overloaded_members(
                    group,
                    cfg=cfg,
                    diagnostics=diagnostics,
                    containing_class_name=class_name,
                    class_fields=instance_field_names,
                    class_field_types=class_field_types,
                    class_field_java_types=class_field_java_types,
                    declared_type_fields=declared_type_fields,
                    declared_type_java_fields=declared_type_java_fields,
                    class_methods=class_method_names,
                    class_static_methods=class_static_method_names,
                    class_method_return_types=method_return_types,
                    static_field_aliases=static_field_aliases,
                    static_method_imports=static_method_imports,
                    name_resolver=name_resolver,
                    pre_body_lines=[],
                    static_instance_static_aliases=static_instance_aliases,
                    static_instance_instance_zero_arg_names=set(instance_zero),
                    static_instance_static_zero_arg_names=set(static_zero),
                ),
            )
            if group_has_to_string_override(group):
                lines.extend(to_string_dunder_wrapper(cfg))
            continue
        member = group[0]
        name_node = member.child_by_field("name")
        raw_name = name_node.text if name_node is not None else "unknown"
        py_name = translate_method_name(raw_name, snake_case=cfg.snake_case_methods)
        if (
            constants_with_bodies
            and py_name in overridden_method_py_names
            and member.type == "method_declaration"
        ):
            diagnostics.record(
                member,
                supported=True,
                reason="translated enum method via constant body dispatch",
            )
            lines.extend(
                _enum_constant_body_dispatcher(
                    member,
                    py_name,
                    cfg,
                    diagnostics,
                    bodies_map_name=bodies_map_name,
                ),
            )
            if group_has_to_string_override(group):
                lines.extend(to_string_dunder_wrapper(cfg))
            continue
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=instance_field_names,
            class_field_types=class_field_types,
            class_field_java_types=class_field_java_types,
            declared_type_fields=declared_type_fields,
            declared_type_java_fields=declared_type_java_fields,
            class_methods=class_method_names,
            class_static_methods=class_static_method_names,
            class_method_return_types=method_return_types,
            static_field_aliases=static_field_aliases,
            static_method_imports=static_method_imports,
            name_resolver=name_resolver,
            containing_class_name=class_name,
            allow_local_helpers=True,
            static_instance_static_aliases=static_instance_aliases,
            static_instance_instance_zero_arg_names=set(instance_zero),
            static_instance_static_zero_arg_names=set(static_zero),
        )
        lines.extend(translate_method(group[0], ctx))
        if group_has_to_string_override(group):
            lines.extend(to_string_dunder_wrapper(cfg))
    return module_prefix + lines


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
    constant_name: str,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    enum_field_names: set[str],
    enum_field_types: dict[str, str],
    enum_field_java_types: dict[str, str],
) -> tuple[list[str], list[str] | None, set[str]]:
    diagnostics.record(constant, supported=True, reason="translated enum constant")
    body = first_child_by_type(constant, "class_body")
    helper_lines: list[str] | None = None
    overridden: set[str] = set()
    if body is not None:
        ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            class_fields=enum_field_names,
            class_field_types=enum_field_types,
            class_field_java_types=enum_field_java_types,
            static_field_aliases=dict(static_field_aliases),
            static_method_imports=dict(static_method_imports),
            name_resolver=name_resolver,
            allow_local_helpers=True,
        )
        helper_lines, overridden = _translate_enum_constant_class_body(
            body,
            constant_name,
            ctx,
        )

    args_node = first_child_by_type(constant, "argument_list")
    if args_node is None or not args_node.named_children:
        assignment = [f"    {constant_name} = {constant_name!r}"]
    else:
        arg_ctx = TranslationContext(
            cfg=cfg,
            diagnostics=diagnostics,
            name_resolver=name_resolver,
        )
        arg_ctx.static_field_aliases = dict(static_field_aliases)
        arg_ctx.static_method_imports = dict(static_method_imports)
        args = [translate_expression(arg, arg_ctx) for arg in args_node.named_children]
        value = f"({', '.join(args)})" if len(args) > 1 else args[0]
        assignment = [f"    {constant_name} = {value}"]

    return assignment, helper_lines, overridden


def _translate_enum_constant_class_body(
    body: JavaNode,
    constant_name: str,
    ctx: TranslationContext,
) -> tuple[list[str], set[str]]:
    from j2py.translate.expr_objects import (
        _anonymous_helper_init_lines,
        _anonymous_method_lines,
    )

    ctx.diagnostics.record(
        body,
        supported=True,
        reason="translated enum constant class body",
    )
    helper_name = f"_J2pyEnumConstant{translate_class_name(constant_name)}"
    lines = [f"class {helper_name}:"]

    instance_fields: list[FieldInfo] = []
    methods: list[JavaNode] = []
    overridden: set[str] = set()
    for member in body.named_children:
        if is_comment(member):
            ctx.diagnostics.warn(member, reason="preserved comment")
            if ctx.cfg.emit_line_comments:
                lines.extend(translate_comment(member, indent="    "))
            continue
        if member.type == "field_declaration":
            for field in field_infos_from_declaration(member, ctx.cfg):
                if field.is_static:
                    ctx.diagnostics.record(
                        member,
                        supported=False,
                        reason="unsupported enum constant class body static field_declaration",
                    )
                    lines.append(
                        "    # TODO(j2py): unsupported enum constant class body static field",
                    )
                    continue
                ctx.diagnostics.record(
                    member,
                    supported=True,
                    reason="translated enum constant class body instance field",
                )
                instance_fields.append(field)
            continue
        if member.type == "method_declaration":
            methods.append(member)
            name_node = member.child_by_field("name")
            if name_node is not None:
                overridden.add(name_node.text)
            continue
        ctx.diagnostics.record(
            member,
            supported=False,
            reason=f"unsupported enum constant class body member {member.type}",
        )
        lines.append(
            f"    # TODO(j2py): unsupported enum constant class body member {member.type}",
        )

    instance_field_names = _instance_field_names(instance_fields)
    instance_field_types_map = _instance_field_types(instance_fields)
    instance_field_java_types = {field.name: field.java_type for field in instance_fields}
    wrote_member = False
    if instance_fields:
        lines.extend(
            _anonymous_helper_init_lines(
                instance_fields,
                ctx,
                def_indent="    ",
                body_indent="        ",
            ),
        )
        wrote_member = True

    for method in methods:
        if wrote_member:
            lines.append("")
        lines.extend(
            _anonymous_method_lines(
                method,
                ctx,
                instance_field_names=instance_field_names,
                instance_field_types=instance_field_types_map,
                instance_field_java_types=instance_field_java_types,
                enclosing_field_names=set(),
                enclosing_field_types={},
                enclosing_field_java_types={},
                outer_self_alias=None,
                member_indent="    ",
                body_indent="        ",
                nested_helper_indent="",
                supported_reason="translated enum constant class body method",
            ),
        )
        wrote_member = True

    if not wrote_member:
        lines.append("    pass")

    return lines, overridden


def _enum_constant_bodies_map_name(class_name: str) -> str:
    return f"_{class_name}_j2py_enum_bodies"


def _enum_constant_body_dispatcher(
    method: JavaNode,
    py_name: str,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    bodies_map_name: str,
) -> list[str]:
    method_return_type = return_type(method, cfg)
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(method_return_type)
    returns = f" -> {method_return_type}" if cfg.emit_type_hints else ""

    params = parameter_infos(method, cfg)
    rendered_params = ["self"]
    passed_params = ["self"]
    for param in params:
        prefix = "*" if param.is_spread else ""
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(param.py_type)
            rendered_params.append(f"{prefix}{param.py_name}: {param.py_type}")
        else:
            rendered_params.append(f"{prefix}{param.py_name}")
        passed_params.append(f"{prefix}{param.py_name}")

    return [
        f"    def {py_name}({', '.join(rendered_params)}){returns}:",
        f"        body_cls = {bodies_map_name}.get(self.name)",
        "        if body_cls is None:",
        "            raise NotImplementedError(self.name)",
        "        if not hasattr(self, '_j2py_enum_initialized'):",
        "            if '__init__' in body_cls.__dict__:",
        "                body_cls.__init__(self)",
        "            self._j2py_enum_initialized = True",
        f"        return body_cls.{py_name}({', '.join(passed_params)})",
    ]


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

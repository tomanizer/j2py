"""Annotation type declaration emission for class translation."""

from __future__ import annotations

import re

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.class_environment import ClassTranslationEnvironment
from j2py.translate.class_methods import _IMMUTABLE_LITERAL_NODES
from j2py.translate.class_model import TYPE_DECLARATION_NODES
from j2py.translate.comments import is_comment, translate_comment
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.expressions import translate_expression
from j2py.translate.name_resolution import NameResolver
from j2py.translate.node_utils import first_child_by_type
from j2py.translate.rules.literals import translate_literal, translate_string_literal
from j2py.translate.rules.naming import translate_class_name, translate_field_name
from j2py.translate.rules.types import java_default_value, translate_type

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


def translate_annotation_declaration(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    env: ClassTranslationEnvironment | None = None,
) -> list[str]:
    env = env or ClassTranslationEnvironment()
    static_field_aliases = env.static_field_aliases
    static_method_imports = env.static_method_imports
    name_resolver = env.name_resolver
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
                    lines.append(f"# {_annotation_comment_text(annotation, static_field_aliases)}")
                continue
            diagnostics.warn(annotation, reason=f"preserved annotation @{name}")
            if cfg.emit_line_comments:
                lines.append(f"# {_annotation_comment_text(annotation, static_field_aliases)}")

    diagnostics.imports.need_dataclass()
    lines.extend(["@dataclass(frozen=True)", f"class {class_name}:"])
    if env.docstring_lines:
        lines.extend(env.docstring_lines)

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
                        name_resolver=name_resolver,
                    )
                )
                continue
            if member.type == "constant_declaration":
                member_lines.extend(
                    _translate_annotation_constant(
                        member,
                        cfg,
                        diagnostics,
                        static_field_aliases=static_field_aliases,
                        static_method_imports=static_method_imports,
                        name_resolver=name_resolver,
                        containing_class_name=class_name,
                    )
                )
                continue
            if member.type in TYPE_DECLARATION_NODES:
                member_lines.extend(
                    _translate_annotation_nested_type(
                        member,
                        cfg,
                        diagnostics,
                        env=env.with_overrides(docstring_lines=None),
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


def _translate_annotation_constant(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
    containing_class_name: str,
) -> list[str]:
    type_node = _annotation_element_type_node(node)
    if type_node is None:
        diagnostics.record(node, supported=False, reason="malformed annotation constant")
        return ["    # TODO(j2py): malformed annotation constant"]

    py_type = translate_type(type_node.text, cfg)
    annotation = f"ClassVar[{py_type}]"
    if cfg.emit_type_hints:
        diagnostics.imports.need_type_annotation(annotation)
    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=diagnostics,
        name_resolver=name_resolver,
        containing_class_name=containing_class_name,
    )
    ctx.static_field_aliases = dict(static_field_aliases)
    ctx.static_method_imports = dict(static_method_imports)

    lines: list[str] = []
    for declarator in node.children_by_type("variable_declarator"):
        name_node = declarator.child_by_field("name")
        if name_node is None:
            continue
        py_name = translate_field_name(name_node.text, snake_case=cfg.snake_case_fields)
        value_node = declarator.child_by_field("value")
        value = (
            translate_expression(value_node, ctx)
            if value_node is not None
            else java_default_value(type_node.text)
        )
        if cfg.emit_type_hints:
            lines.append(f"    {py_name}: {annotation} = {value}")
        else:
            lines.append(f"    {py_name} = {value}")

    if not lines:
        diagnostics.record(node, supported=False, reason="malformed annotation constant")
        return ["    # TODO(j2py): malformed annotation constant"]

    diagnostics.record(node, supported=True, reason="translated annotation constant")
    return lines


def _translate_annotation_nested_type(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    env: ClassTranslationEnvironment,
) -> list[str]:
    from j2py.translate.classes import translate_class

    nested_lines = translate_class(node, cfg, diagnostics, env=env)
    return [f"    {line}" if line else line for line in nested_lines]


def _annotation_node_name(annotation: JavaNode) -> str | None:
    name_node = annotation.child_by_field("name")
    if name_node is None:
        name_node = first_child_by_type(annotation, "identifier", "scoped_identifier")
    return name_node.text if name_node is not None else None


def _annotation_comment_text(
    annotation: JavaNode,
    static_field_aliases: dict[str, str],
) -> str:
    text = annotation.text.strip()
    for raw_name, alias in sorted(static_field_aliases.items(), key=lambda item: -len(item[0])):
        text = re.sub(
            rf"(?<![\w.]){re.escape(raw_name)}(?![\w.])",
            alias,
            text,
        )
    return text


def _translate_annotation_element(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
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
        name_resolver=name_resolver,
    )
    if default_value is None:
        diagnostics.record(
            node,
            supported=False,
            reason="unsupported annotation element default",
        )
        if cfg.emit_type_hints:
            return f"    {py_name}: {py_type} | None = None  # TODO(j2py): unsupported default"
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
    name_resolver: NameResolver,
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
                name_resolver=name_resolver,
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
        name_resolver=name_resolver,
    )


def _annotation_scalar_default(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    static_field_aliases: dict[str, str],
    static_method_imports: dict[str, str],
    name_resolver: NameResolver,
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

    ctx = TranslationContext(cfg=cfg, diagnostics=diagnostics, name_resolver=name_resolver)
    ctx.static_field_aliases = dict(static_field_aliases)
    ctx.static_method_imports = dict(static_method_imports)
    translated = translate_expression(node, ctx)
    if translated.startswith("__j2py_todo__"):
        return None
    return translated

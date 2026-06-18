"""JPA entity lowering to SQLAlchemy 2.0 declarative models."""

from __future__ import annotations

import re

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.bean_validation import is_required_field
from j2py.translate.class_model import FieldInfo
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.framework_annotations import (
    annotation_map_entry,
    annotation_simple_name,
    annotation_template_values,
)
from j2py.translate.java_types import java_type_simple_name
from j2py.translate.rules.naming import translate_field_name
from j2py.translate.rules.types import element_type_from_container, java_default_value

_ENTITY_ANNOTATIONS = frozenset({"Entity"})
_TABLE_ANNOTATIONS = frozenset({"Table"})
_COLUMN_ANNOTATIONS = frozenset({"Column"})
_ID_ANNOTATIONS = frozenset({"Id"})
_GENERATED_VALUE_ANNOTATIONS = frozenset({"GeneratedValue"})
_JOIN_COLUMN_ANNOTATIONS = frozenset({"JoinColumn"})
_RELATIONSHIP_ANNOTATIONS = frozenset({"ManyToMany", "ManyToOne", "OneToMany", "OneToOne"})
_TO_MANY_ANNOTATIONS = frozenset({"ManyToMany", "OneToMany"})
_TYPE_NAME_TOKEN_RE = re.compile(r"\b\w+\b")


def collect_sqlalchemy_entity_table_names(
    root: JavaNode,
    cfg: TranslationConfig,
) -> dict[str, str]:
    """Return Java entity class names and their emitted table names."""

    if "Entity" in _local_annotation_type_names(root):
        return {}

    entities: dict[str, str] = {}
    for node in root.walk():
        if node.type != "class_declaration" or not _is_entity_node(node, cfg):
            continue
        name_node = node.child_by_field("name")
        if name_node is None:
            continue
        entities[name_node.text] = _table_name(node, name_node.text)
    return entities


def sqlalchemy_model_field_lines(
    field: FieldInfo,
    diagnostics: TranslationDiagnostics,
    *,
    entity_table_names: dict[str, str],
) -> list[str]:
    """Render one Java entity field as SQLAlchemy 2.0 mapped declarations."""

    diagnostics.imports.need_line("from sqlalchemy.orm import Mapped")
    if _relationship_annotation(field) is not None:
        return _relationship_field_lines(field, diagnostics, entity_table_names)
    return _column_field_lines(field, diagnostics)


def _is_entity_node(node: JavaNode, cfg: TranslationConfig) -> bool:
    for annotation in annotation_nodes(node):
        if annotation_simple_name(annotation) not in _ENTITY_ANNOTATIONS:
            continue
        return annotation_map_entry(annotation, cfg) is None
    return False


def _table_name(node: JavaNode, class_name: str) -> str:
    table = _annotation_values(node, _TABLE_ANNOTATIONS)
    explicit = table.get("name") or table.get("value")
    return explicit if explicit else translate_field_name(class_name, snake_case=True)


def _column_field_lines(field: FieldInfo, diagnostics: TranslationDiagnostics) -> list[str]:
    diagnostics.record(field.node, supported=True, reason="translated JPA column to SQLAlchemy")
    diagnostics.imports.need_line("from sqlalchemy.orm import mapped_column")

    column_values = _annotation_values(field.node, _COLUMN_ANNOTATIONS)
    args: list[str] = []
    kwargs: list[str] = []

    column_name = column_values.get("name") or column_values.get("value")
    if column_name:
        args.append(_quote(column_name))

    if _is_string_field(field):
        diagnostics.imports.need_line("from sqlalchemy import String")
        length = _parse_int(column_values.get("length"))
        args.append(f"String({length})" if length is not None else "String")

    if _has_annotation(field.node, _ID_ANNOTATIONS):
        kwargs.append("primary_key=True")
    if _has_annotation(field.node, _GENERATED_VALUE_ANNOTATIONS):
        kwargs.append("autoincrement=True")

    nullable = _nullable_value(field, column_values)
    if nullable is not None:
        kwargs.append(f"nullable={nullable}")

    annotation = _mapped_annotation(field, nullable=nullable is True)
    call_args = [*args, *kwargs]
    expression = f"mapped_column({', '.join(call_args)})" if call_args else "mapped_column()"
    return [f"    {_sqlalchemy_field_name(field)}: Mapped[{annotation}] = {expression}"]


def _relationship_field_lines(
    field: FieldInfo,
    diagnostics: TranslationDiagnostics,
    entity_table_names: dict[str, str],
) -> list[str]:
    diagnostics.record(
        field.node,
        supported=True,
        reason="translated JPA relationship to SQLAlchemy",
    )
    diagnostics.imports.need_line("from sqlalchemy.orm import relationship")

    lines: list[str] = []
    target = _relationship_target(field, entity_table_names)
    join_column = _annotation_values(field.node, _JOIN_COLUMN_ANNOTATIONS)
    if target is not None and join_column:
        diagnostics.imports.need_line("from sqlalchemy import ForeignKey")
        diagnostics.imports.need_line("from sqlalchemy.orm import mapped_column")
        column_name = join_column.get("name") or join_column.get("value") or f"{field.py_name}_id"
        table_name = entity_table_names.get(target, translate_field_name(target, snake_case=True))
        foreign_key = f"{table_name}.id"
        lines.append(
            f"    {translate_field_name(column_name, snake_case=True)}: Mapped[int] = "
            f"mapped_column(ForeignKey({_quote(foreign_key)}))",
        )

    annotation = _relationship_annotation_text(field, target)
    relationship_args = _relationship_args(field)
    expression = (
        f"relationship({', '.join(relationship_args)})" if relationship_args else "relationship()"
    )
    lines.append(f"    {field.py_name}: Mapped[{annotation}] = {expression}")
    return lines


def _relationship_annotation_text(field: FieldInfo, target: str | None) -> str:
    target_text = target if target else field.py_type
    if _is_to_many_relationship(field):
        return f"list[{target_text}]"
    return target_text


def _relationship_args(field: FieldInfo) -> list[str]:
    values = _annotation_values(field.node, _RELATIONSHIP_ANNOTATIONS)
    args: list[str] = []
    mapped_by = values.get("mappedBy")
    if mapped_by:
        args.append(f"back_populates={_quote(mapped_by)}")
    cascade = _cascade_value(values.get("cascade"))
    if cascade:
        args.append(f"cascade={_quote(cascade)}")
    return args


def _relationship_target(field: FieldInfo, entity_table_names: dict[str, str]) -> str | None:
    entity_names: set[str] = set(entity_table_names)
    names: set[str] = set(_TYPE_NAME_TOKEN_RE.findall(field.java_type)) & entity_names
    if names:
        return sorted(names)[0]
    simple = java_type_simple_name(field.java_type)
    return simple if simple in entity_table_names else None


def _is_to_many_relationship(field: FieldInfo) -> bool:
    annotation_name = _relationship_annotation(field)
    if annotation_name in _TO_MANY_ANNOTATIONS:
        return True
    element = element_type_from_container(field.py_type)
    return element is not None


def _relationship_annotation(field: FieldInfo) -> str | None:
    for annotation in annotation_nodes(field.node):
        name = annotation_simple_name(annotation)
        if name in _RELATIONSHIP_ANNOTATIONS:
            return name
    return None


def _mapped_annotation(field: FieldInfo, *, nullable: bool) -> str:
    if nullable and java_default_value(field.java_type) == "None" and "None" not in field.py_type:
        return f"{field.py_type} | None"
    return field.py_type


def _nullable_value(field: FieldInfo, column_values: dict[str, str]) -> bool | None:
    explicit = _bool_value(column_values.get("nullable"))
    if explicit is not None:
        return explicit
    if _has_annotation(field.node, _ID_ANNOTATIONS):
        return None
    if is_required_field(field):
        return False
    return None


def _is_string_field(field: FieldInfo) -> bool:
    return java_type_simple_name(field.java_type) == "String"


def _sqlalchemy_field_name(field: FieldInfo) -> str:
    return "id" if field.name == "id" else field.py_name


def _local_annotation_type_names(root: JavaNode) -> set[str]:
    names: set[str] = set()
    for node in root.walk():
        if node.type != "annotation_type_declaration":
            continue
        name_node = node.child_by_field("name")
        if name_node is not None:
            names.add(name_node.text)
    return names


def _annotation_values(node: JavaNode, names: frozenset[str]) -> dict[str, str]:
    for annotation in annotation_nodes(node):
        if annotation_simple_name(annotation) in names:
            return annotation_template_values(annotation)
    return {}


def _has_annotation(node: JavaNode, names: frozenset[str]) -> bool:
    return any(annotation_simple_name(annotation) in names for annotation in annotation_nodes(node))


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.replace("_", ""))
    except ValueError:
        return None


def _bool_value(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.rsplit(".", 1)[-1].lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _cascade_value(value: str | None) -> str | None:
    if value is None:
        return None
    values = [part.rsplit(".", 1)[-1].strip().lower() for part in value.split(",")]
    if "all" in values:
        return "all"
    return ", ".join(value for value in values if value) or None


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

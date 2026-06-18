"""Spring configuration property lowering helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.class_model import FieldInfo
from j2py.translate.framework_annotations import (
    annotation_simple_name,
    annotation_template_values,
)
from j2py.translate.rules.types import java_default_value


@dataclass(frozen=True)
class ValueField:
    annotation: JavaNode
    expression: str
    default_value: str


_PLACEHOLDER_DEFAULT_RE = re.compile(r"^\$\{[^:}]+:(?P<default>.*)\}$")
_NON_ENV_CHARS_RE = re.compile(r"[^A-Za-z0-9]+")


def configuration_properties_env_prefix(node: JavaNode) -> str | None:
    """Return the Pydantic Settings env_prefix for @ConfigurationProperties."""
    for annotation in annotation_nodes(node):
        if annotation_simple_name(annotation) != "ConfigurationProperties":
            continue
        values = annotation_template_values(annotation)
        prefix = values.get("prefix") or values.get("value") or ""
        return _env_prefix(prefix)
    return None


def spring_value_field(field: FieldInfo) -> ValueField | None:
    """Return metadata for a Spring @Value field, if present."""
    for annotation in annotation_nodes(field.node):
        if annotation_simple_name(annotation) != "Value":
            continue
        values = annotation_template_values(annotation)
        expression = values.get("value", "")
        return ValueField(
            annotation=annotation,
            expression=expression,
            default_value=_value_default(expression, field.java_type),
        )
    return None


def spring_value_comment_lines(
    field: FieldInfo,
    value: ValueField,
    *,
    indent: str,
) -> list[str]:
    """Emit conservative comments for Spring @Value injection sites."""
    return [
        f"{indent}# TODO(j2py): @Value injection is hard to lower statically",
        f'{indent}# @Value("{value.expression}") -> {field.name}',
        (f"{indent}# Replace with: {field.py_name}: {field.py_type} = settings.{field.py_name}"),
    ]


def _env_prefix(prefix: str) -> str:
    rendered = _NON_ENV_CHARS_RE.sub("_", prefix).strip("_").upper()
    return f"{rendered}_" if rendered else ""


def _value_default(expression: str, java_type: str) -> str:
    match = _PLACEHOLDER_DEFAULT_RE.match(expression)
    if match is None:
        return java_default_value(java_type)
    raw_default = match.group("default")
    if raw_default == "":
        return java_default_value(java_type)
    return _coerce_default(raw_default, java_type)


def _coerce_default(raw_default: str, java_type: str) -> str:
    lowered_type = java_type.lower()
    if lowered_type in {"string", "char", "character"} or java_type.endswith(".String"):
        return json.dumps(raw_default)
    if lowered_type in {"boolean", "bool"}:
        if raw_default.lower() == "true":
            return "True"
        if raw_default.lower() == "false":
            return "False"
        return java_default_value(java_type)
    if lowered_type in {"float", "double"}:
        try:
            float(raw_default)
        except ValueError:
            return java_default_value(java_type)
        return raw_default
    if lowered_type in {"byte", "short", "int", "integer", "long"}:
        try:
            int(raw_default, 0)
        except ValueError:
            return java_default_value(java_type)
        return raw_default
    return repr(raw_default)

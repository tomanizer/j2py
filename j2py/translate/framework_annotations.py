"""Config-driven lowering for project framework annotations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from j2py.config.loader import AnnotationMapEntry, TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.class_model import FieldInfo, ParameterInfo
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.node_utils import first_child_by_type


@dataclass(frozen=True)
class ClassAnnotationMapping:
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)


def class_annotation_mapping(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    indent: str = "",
) -> ClassAnnotationMapping:
    decorators: list[str] = []
    bases: list[str] = []
    for annotation in annotation_nodes(node):
        entry = annotation_map_entry(annotation, cfg)
        if entry is None or entry.drop:
            continue
        _register_import(entry, diagnostics)
        values = annotation_template_values(annotation)
        if entry.python_decorator:
            decorators.append(
                f"{indent}@{render_annotation_template(entry.python_decorator, values)}"
            )
        if entry.python_base:
            base = render_annotation_template(entry.python_base, values)
            if base not in bases:
                bases.append(base)
    return ClassAnnotationMapping(decorators=decorators, bases=bases)


def method_annotation_decorator_lines(
    node: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    indent: str,
) -> list[str]:
    lines: list[str] = []
    for annotation in annotation_nodes(node):
        entry = annotation_map_entry(annotation, cfg)
        if entry is None or entry.drop or not entry.python_decorator:
            continue
        _register_import(entry, diagnostics)
        rendered = render_annotation_template(
            entry.python_decorator,
            annotation_template_values(annotation),
        )
        lines.append(f"{indent}@{rendered}")
    return lines


def field_annotation_comment_lines(
    field: FieldInfo,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    indent: str,
) -> list[str]:
    lines: list[str] = []
    for annotation in annotation_nodes(field.node):
        entry = annotation_map_entry(annotation, cfg)
        if entry is None or entry.drop or not entry.field_comment:
            continue
        _register_import(entry, diagnostics)
        values = annotation_template_values(annotation)
        values.update(
            {
                "field_name": field.py_name,
                "field_type": field.py_type,
                "java_type": field.java_type,
            },
        )
        rendered = render_annotation_template(entry.field_comment, values)
        if rendered.lstrip().startswith("#"):
            lines.append(f"{indent}{rendered}")
        else:
            lines.append(f"{indent}# {rendered}")
    return lines


def field_init_parameter(
    field: FieldInfo,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics | None = None,
) -> ParameterInfo | None:
    if field.is_static:
        return None
    for annotation in annotation_nodes(field.node):
        entry = annotation_map_entry(annotation, cfg)
        if entry is not None and not entry.drop and entry.emit_init_param:
            if diagnostics is not None:
                _register_import(entry, diagnostics)
            return ParameterInfo(
                raw_name=field.name,
                py_name=field.py_name,
                py_type=field.py_type,
                java_type=field.java_type,
            )
    return None


def parameter_annotation_metadata(
    parameter: JavaNode,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
) -> list[str]:
    metadata: list[str] = []
    for annotation in annotation_nodes(parameter):
        entry = annotation_map_entry(annotation, cfg)
        if entry is None or entry.drop or not entry.python_annotation:
            continue
        _register_import(entry, diagnostics)
        metadata.append(
            render_annotation_template(
                entry.python_annotation,
                annotation_template_values(annotation),
            )
        )
    return metadata


def annotation_map_entry(
    annotation: JavaNode,
    cfg: TranslationConfig,
) -> AnnotationMapEntry | None:
    full_name = annotation_full_name(annotation)
    simple_name = annotation_simple_name(annotation)
    if simple_name and simple_name in cfg.annotation_map:
        return _coerce_entry(cfg.annotation_map[simple_name])
    if full_name and full_name in cfg.annotation_map:
        return _coerce_entry(cfg.annotation_map[full_name])
    return None


def annotation_simple_name(annotation: JavaNode) -> str | None:
    full_name = annotation_full_name(annotation)
    if full_name is None:
        return None
    return full_name.rsplit(".", 1)[-1] if "." in full_name else full_name


def annotation_full_name(annotation: JavaNode) -> str | None:
    name_node = annotation.child_by_field("name")
    if name_node is None:
        name_node = first_child_by_type(annotation, "identifier", "scoped_identifier")
    return name_node.text if name_node is not None else None


def annotation_template_values(annotation: JavaNode) -> dict[str, str]:
    args = first_child_by_type(annotation, "annotation_argument_list")
    if args is None:
        return {}

    values: dict[str, str] = {}
    positional_index = 0
    for child in args.named_children:
        if child.type == "element_value_pair":
            key_node = first_child_by_type(child, "identifier")
            value_node = child.named_children[-1] if child.named_children else None
            if key_node is not None and value_node is not None:
                values[key_node.text] = _annotation_value_text(value_node)
            continue
        key = "value" if positional_index == 0 else f"value{positional_index + 1}"
        values[key] = _annotation_value_text(child)
        positional_index += 1
    return _annotation_value_aliases(values)


def transactional_annotation_comment_lines(
    annotation: JavaNode,
    *,
    indent: str,
) -> list[str]:
    """Render Spring @Transactional as actionable rule-layer comments."""
    values = annotation_template_values(annotation)
    attributes = _transactional_attributes(values)
    suffix = f"({', '.join(attributes)})" if attributes else ""
    lines = [f"{indent}# @Transactional{suffix}"]
    read_only = _transactional_bool(values.get("readOnly"))
    if read_only is True:
        lines.append(f"{indent}# read-only transaction")
    rollback_for = values.get("rollbackFor")
    if rollback_for:
        normalized = _transactional_exception_list(rollback_for)
        lines.append(f"{indent}# rollbackFor={normalized}")
    return lines


def render_annotation_template(template: str, values: dict[str, str]) -> str:
    rendered = template.format_map(_TemplateValues(values))
    return _strip_unresolved_keyword_arguments(rendered)


def _annotation_value_aliases(values: dict[str, str]) -> dict[str, str]:
    aliased = dict(values)
    if "path" in aliased and "value" not in aliased:
        aliased["value"] = aliased["path"]
    if "value" in aliased and "path" not in aliased:
        aliased["path"] = aliased["value"]
    if "code" in aliased and "value" not in aliased:
        aliased["value"] = aliased["code"]
    return aliased


def _transactional_attributes(values: dict[str, str]) -> list[str]:
    attributes: list[str] = []
    for key, value in values.items():
        if key == "readOnly":
            rendered = _transactional_bool(value)
            attributes.append(f"readOnly={rendered if rendered is not None else value}")
            continue
        if key == "rollbackFor":
            attributes.append(f"rollbackFor={_transactional_exception_list(value)}")
            continue
        attributes.append(f"{key}={value}")
    return attributes


def _transactional_bool(value: str | None) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _transactional_exception_list(value: str) -> str:
    exceptions = [part.strip() for part in value.split(",")]
    return ", ".join(
        exception.removesuffix(".class") if exception.endswith(".class") else exception
        for exception in exceptions
    )


def _strip_unresolved_keyword_arguments(rendered: str) -> str:
    return re.sub(
        r",\s*[A-Za-z_]\w*\s*=\s*(['\"])\{[A-Za-z_]\w*\}\1",
        "",
        rendered,
    )


def _annotation_value_text(node: JavaNode) -> str:
    if node.type == "element_value_array_initializer":
        values = [_annotation_value_text(child) for child in node.named_children]
        return values[0] if len(values) == 1 else ", ".join(values)
    if node.type == "string_literal":
        fragments = [child.text for child in node.named_children if child.type == "string_fragment"]
        if fragments:
            return "".join(fragments)
        text = node.text
        if len(text) >= 2 and text[0] == text[-1] == '"':
            return text[1:-1]
    return _spring_enum_literal(node.text) or node.text


def _spring_enum_literal(text: str) -> str | None:
    value = text.rsplit(".", 1)[-1]
    if value in {"GET", "POST", "PUT", "DELETE", "PATCH"} and (
        text == value or text.endswith(f".{value}")
    ):
        return value
    status_codes = {
        "ACCEPTED": "202",
        "BAD_REQUEST": "400",
        "CONFLICT": "409",
        "CREATED": "201",
        "FORBIDDEN": "403",
        "FOUND": "302",
        "INTERNAL_SERVER_ERROR": "500",
        "NO_CONTENT": "204",
        "NOT_FOUND": "404",
        "OK": "200",
        "UNAUTHORIZED": "401",
    }
    if value in status_codes and (text == value or "HttpStatus." in text):
        return status_codes[value]
    return None


def _register_import(entry: AnnotationMapEntry, diagnostics: TranslationDiagnostics) -> None:
    if not entry.import_:
        return
    for line in entry.import_.splitlines():
        stripped = line.strip()
        if stripped:
            diagnostics.imports.need_line(stripped)


def _coerce_entry(entry: AnnotationMapEntry | dict[str, object]) -> AnnotationMapEntry:
    if isinstance(entry, AnnotationMapEntry):
        return entry
    return AnnotationMapEntry.model_validate(entry)


class _TemplateValues(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"

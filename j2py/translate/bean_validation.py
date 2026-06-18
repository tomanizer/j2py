"""Bean Validation annotation lowering for field declarations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_emit import annotation_nodes
from j2py.translate.class_model import FieldInfo
from j2py.translate.framework_annotations import (
    annotation_simple_name,
    annotation_template_values,
)


@dataclass(frozen=True)
class BeanValidationField:
    """Rendered Pydantic ``Field`` expression for Bean Validation annotations."""

    expression: str
    comment_lines: tuple[str, ...] = ()


_VALIDATION_ANNOTATIONS = frozenset(
    {
        "Digits",
        "Email",
        "Max",
        "Min",
        "NotBlank",
        "NotEmpty",
        "NotNull",
        "Pattern",
        "Positive",
        "PositiveOrZero",
        "Size",
    }
)
_JPA_ENTITY_ANNOTATIONS = frozenset({"Entity"})
_FIELD_KWARG_ORDER = ("min_length", "max_length", "ge", "le", "gt", "pattern")
_EMAIL_PATTERN = r"[^@]+@[^@]+\.[^@]+"


def bean_validation_field(
    field: FieldInfo,
    *,
    default_value: str = "...",
) -> BeanValidationField | None:
    """Return the Pydantic field expression for a validated Java field, if any."""

    kwargs: dict[str, int | str] = {}
    comments: list[str] = []
    saw_validation = False
    for annotation in annotation_nodes(field.node):
        name = annotation_simple_name(annotation)
        if name not in _VALIDATION_ANNOTATIONS:
            continue
        saw_validation = True
        values = annotation_template_values(annotation)
        if name in {"NotEmpty", "NotBlank"}:
            _merge_lower_bound(kwargs, "min_length", 1)
            if name == "NotBlank":
                comments.append("# @NotBlank: strip whitespace before validation")
            continue
        if name == "Size":
            _merge_lower_bound_from_annotation(kwargs, "min_length", values.get("min"))
            _merge_upper_bound_from_annotation(kwargs, "max_length", values.get("max"))
            continue
        if name == "Min":
            _merge_lower_bound_from_annotation(kwargs, "ge", values.get("value"))
            continue
        if name == "Max":
            _merge_upper_bound_from_annotation(kwargs, "le", values.get("value"))
            continue
        if name == "Pattern":
            pattern = values.get("regexp") or values.get("value")
            if pattern is not None:
                kwargs["pattern"] = pattern
            continue
        if name == "Email":
            kwargs["pattern"] = _EMAIL_PATTERN
            continue
        if name == "Positive":
            _merge_lower_bound(kwargs, "gt", 0)
            continue
        if name == "PositiveOrZero":
            _merge_lower_bound(kwargs, "ge", 0)
            continue
        if name == "Digits":
            comments.append(_digits_comment(values))

    if not saw_validation:
        return None

    rendered_kwargs = [
        f"{key}={_render_value(kwargs[key])}" for key in _FIELD_KWARG_ORDER if key in kwargs
    ]
    args = [default_value, *rendered_kwargs]
    return BeanValidationField(
        expression=f"Field({', '.join(args)})",
        comment_lines=tuple(dict.fromkeys(comments)),
    )


def is_required_field(field: FieldInfo) -> bool:
    """Return true when Bean Validation semantics require a non-null value."""

    for annotation in annotation_nodes(field.node):
        name = annotation_simple_name(annotation)
        if name in {"NotBlank", "NotEmpty", "NotNull"}:
            return True
    return False


def has_bean_validation(field: FieldInfo) -> bool:
    """Return true when ``field`` has a supported Bean Validation annotation."""

    return bean_validation_field(field) is not None


def has_bean_validation_fields(fields: Iterable[FieldInfo]) -> bool:
    """Return true when any non-static field has supported validation metadata."""

    return any(not field.is_static and has_bean_validation(field) for field in fields)


def should_promote_to_pydantic_model(node: JavaNode, fields: Iterable[FieldInfo]) -> bool:
    """Return true when a plain validated DTO should extend Pydantic ``BaseModel``."""

    if not has_bean_validation_fields(fields):
        return False
    if _has_annotation(node, _JPA_ENTITY_ANNOTATIONS):
        return False
    return node.child_by_field("superclass") is None


def _has_annotation(node: JavaNode, names: frozenset[str]) -> bool:
    for annotation in annotation_nodes(node):
        name = annotation_simple_name(annotation)
        if name in names:
            return True
    return False


def _merge_lower_bound_from_annotation(
    kwargs: dict[str, int | str],
    key: str,
    value: str | None,
) -> None:
    parsed = _parse_int(value)
    if parsed is not None:
        _merge_lower_bound(kwargs, key, parsed)


def _merge_upper_bound_from_annotation(
    kwargs: dict[str, int | str],
    key: str,
    value: str | None,
) -> None:
    parsed = _parse_int(value)
    if parsed is not None:
        _merge_upper_bound(kwargs, key, parsed)


def _merge_lower_bound(kwargs: dict[str, int | str], key: str, value: int) -> None:
    existing = kwargs.get(key)
    kwargs[key] = max(existing, value) if isinstance(existing, int) else value


def _merge_upper_bound(kwargs: dict[str, int | str], key: str, value: int) -> None:
    existing = kwargs.get(key)
    kwargs[key] = min(existing, value) if isinstance(existing, int) else value


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    literal = value.replace("_", "").rstrip("Ll")
    sign = ""
    if literal.startswith(("+", "-")):
        sign = literal[0]
        literal = literal[1:]
    try:
        if literal.startswith(("0x", "0X")):
            return int(f"{sign}{literal}", 16)
        if literal.startswith(("0b", "0B")):
            return int(f"{sign}{literal}", 2)
        return int(f"{sign}{literal}")
    except ValueError:
        return None


def _render_value(value: int | str) -> str:
    return str(value) if isinstance(value, int) else repr(value)


def _digits_comment(values: dict[str, str]) -> str:
    parts = []
    if "integer" in values:
        parts.append(f"integer={values['integer']}")
    if "fraction" in values:
        parts.append(f"fraction={values['fraction']}")
    suffix = f"({', '.join(parts)})" if parts else ""
    return f"# @Digits{suffix}"

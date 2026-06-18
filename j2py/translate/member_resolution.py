"""Shared Java member and type-shape binding helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from j2py.config.loader import TranslationConfig
from j2py.translate.overload_signatures import _erase_py_type
from j2py.translate.rules.naming import translate_class_name, translate_field_name
from j2py.translate.rules.types import _split_type_params, translate_type

JavaMemberKind = Literal["method", "field", "unknown"]
JavaMemberSource = Literal[
    "explicit_static_import",
    "wildcard_static_import",
    "qualified_receiver",
    "same_class",
    "inherited",
    "fallback",
]
JavaTypeCategory = Literal[
    "primitive",
    "numeric",
    "string",
    "collection",
    "map",
    "callable",
    "enum",
    "object",
    "unknown",
]


@dataclass(frozen=True)
class JavaMemberBinding:
    """A source-level Java member binding preserved for deterministic lowering."""

    owner: str
    member: str
    kind: JavaMemberKind
    source: JavaMemberSource
    python_owner: str | None
    python_member: str
    intrinsic: str | None = None


@dataclass(frozen=True)
class JavaTypeShape:
    """Java type facts retained before translation erases them to Python shapes."""

    raw: str
    simple: str
    python_erasure: str
    category: JavaTypeCategory
    type_args: tuple[JavaTypeShape, ...] = ()


def static_import_binding(
    imported_name: str,
    cfg: TranslationConfig,
    *,
    kind: JavaMemberKind,
    intrinsic: str | None = None,
) -> JavaMemberBinding:
    """Bind an explicit static import to owner/member plus Python fallback names."""
    owner, _, member = imported_name.rpartition(".")
    python_owner = translate_class_name(owner.rsplit(".", 1)[-1]) if owner else None
    python_member = (
        translate_field_name(member, snake_case=cfg.snake_case_fields)
        if kind == "field"
        else _translate_member_method_name(member, cfg)
    )
    return JavaMemberBinding(
        owner=owner,
        member=member,
        kind=kind,
        source="explicit_static_import",
        python_owner=python_owner,
        python_member=python_member,
        intrinsic=intrinsic,
    )


def static_import_field_fallback(binding: JavaMemberBinding, cfg: TranslationConfig) -> str:
    """Return a reviewable Python field reference for a static import binding."""
    if binding.python_owner is None:
        return translate_field_name(binding.member, snake_case=cfg.snake_case_fields)
    py_member = translate_field_name(binding.member, snake_case=cfg.snake_case_fields)
    return f"{binding.python_owner}.{py_member}"


def static_import_method_fallback(
    binding: JavaMemberBinding,
    args: list[str],
    cfg: TranslationConfig,
) -> str:
    """Return a reviewable Python method call for a static import binding."""
    if binding.python_owner is None:
        return f"{_translate_member_method_name(binding.member, cfg)}({', '.join(args)})"
    py_method = _translate_member_method_name(binding.member, cfg)
    return f"{binding.python_owner}.{py_method}({', '.join(args)})"


def java_type_shape(java_type: str, cfg: TranslationConfig) -> JavaTypeShape:
    """Classify a Java type before Python erasure removes source-level distinctions."""
    raw = _normalize_java_type(java_type)
    simple = _simple_java_type(raw)
    type_args = _type_arg_shapes(raw, cfg)
    py_type = translate_type(_type_text_for_translation(raw), cfg)
    return JavaTypeShape(
        raw=raw,
        simple=simple,
        python_erasure=_erase_py_type(py_type),
        category=_type_category(simple, raw, cfg),
        type_args=type_args,
    )


def java_type_shape_signature(
    java_types: list[str],
    cfg: TranslationConfig,
) -> tuple[str, ...]:
    """Return stable, compact signatures for overload classifier diagnostics."""
    return tuple(_shape_signature(java_type_shape(java_type, cfg)) for java_type in java_types)


def _translate_member_method_name(member: str, cfg: TranslationConfig) -> str:
    from j2py.translate.rules.naming import translate_method_name

    return translate_method_name(member, snake_case=cfg.snake_case_methods)


def _normalize_java_type(java_type: str) -> str:
    text = java_type.strip()
    text = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", text).strip()
    return re.sub(r"\s+", " ", text)


def _simple_java_type(java_type: str) -> str:
    text = java_type
    while text.endswith("[]"):
        text = text[:-2].strip()
    if text.endswith("..."):
        text = text[:-3].strip()
    text = text.split("<", 1)[0].strip()
    return text.rsplit(".", 1)[-1]


def _type_text_for_translation(java_type: str) -> str:
    raw = java_type.strip()
    match = re.match(r"^([\w.]+)\s*<(.+)>$", raw)
    if match is not None:
        simple = match.group(1).rsplit(".", 1)[-1]
        return f"{simple}<{match.group(2)}>"
    if raw.endswith("[]"):
        return f"{_type_text_for_translation(raw[:-2])}[]"
    if raw.endswith("..."):
        return f"{_type_text_for_translation(raw[:-3])}..."
    return raw.rsplit(".", 1)[-1]


def _type_arg_shapes(java_type: str, cfg: TranslationConfig) -> tuple[JavaTypeShape, ...]:
    match = re.match(r"^[\w.]+\s*<(.+)>$", java_type)
    if match is None:
        return ()
    return tuple(java_type_shape(param, cfg) for param in _split_type_params(match.group(1)))


def _type_category(
    simple: str,
    java_type: str,
    cfg: TranslationConfig,
) -> JavaTypeCategory:
    if simple in {"boolean", "Boolean"}:
        return "primitive"
    if simple in {
        "byte",
        "short",
        "int",
        "long",
        "float",
        "double",
        "Byte",
        "Short",
        "Integer",
        "Long",
        "Float",
        "Double",
        "Number",
    }:
        return "numeric"
    if simple in {"char", "Character", "String", "CharSequence"}:
        return "string"
    if simple in {"Function", "Predicate", "Consumer", "Supplier", "Callable"}:
        return "callable"
    if simple in {"Map", "HashMap", "LinkedHashMap", "TreeMap", "Hashtable", "Properties"}:
        return "map"
    if simple in cfg.collection_map and cfg.collection_map[simple].startswith("dict"):
        return "map"
    if simple in cfg.collection_map:
        return "collection"
    if simple.endswith("Map") or simple.endswith("Multimap"):
        return "map"
    if java_type in {"Object", "java.lang.Object"} or simple == "Object":
        return "object"
    return "unknown"


def _shape_signature(shape: JavaTypeShape) -> str:
    suffix = ""
    if shape.type_args:
        suffix = "[" + ",".join(_shape_signature(arg) for arg in shape.type_args) + "]"
    return f"{shape.category}:{shape.simple}->{shape.python_erasure}{suffix}"

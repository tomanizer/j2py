"""Shared Java member and type-shape binding helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from j2py.config.loader import TranslationConfig
from j2py.translate.overload_signatures import _erase_py_type
from j2py.translate.rules.naming import translate_class_name, translate_field_name
from j2py.translate.rules.types import _split_type_params, translate_type

if TYPE_CHECKING:
    from j2py.parse.java_ast import JavaNode
    from j2py.translate.diagnostics import TranslationContext

JavaMemberKind = Literal["method", "field", "unknown"]
JavaMemberSource = Literal[
    "config",
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
    return_type: str | None = None
    return_shape: str | None = None


@dataclass(frozen=True)
class JavaOverloadCallTarget:
    """Body-backed overload branch available for source-proven call-site binding."""

    member: str
    python_member: str
    java_shape_signature: tuple[str, ...]
    is_static: bool
    helper_name: str


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
    configured = configured_member_binding(imported_name, cfg, source="explicit_static_import")
    if configured is not None:
        if kind != "unknown" and configured.kind == "unknown":
            return JavaMemberBinding(
                owner=configured.owner,
                member=configured.member,
                kind=kind,
                source=configured.source,
                python_owner=configured.python_owner,
                python_member=configured.python_member,
                intrinsic=intrinsic or configured.intrinsic,
                return_type=configured.return_type,
                return_shape=configured.return_shape,
            )
        return configured
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


def configured_member_binding(
    qualified_member: str,
    cfg: TranslationConfig,
    *,
    source: JavaMemberSource = "config",
) -> JavaMemberBinding | None:
    """Return a configured project member binding if one exists."""
    entry = cfg.member_map.get(qualified_member)
    if entry is None:
        return None
    owner, _, member = qualified_member.rpartition(".")
    python_owner = entry.python_owner
    if python_owner is None and owner:
        python_owner = translate_class_name(owner.rsplit(".", 1)[-1])
    python_member = entry.python_member
    if python_member is None:
        python_member = (
            translate_field_name(member, snake_case=cfg.snake_case_fields)
            if entry.kind == "field"
            else _translate_member_method_name(member, cfg)
        )
    return JavaMemberBinding(
        owner=owner,
        member=member,
        kind=entry.kind,
        source=source,
        python_owner=python_owner,
        python_member=python_member,
        intrinsic=entry.intrinsic or None,
        return_type=entry.return_type,
        return_shape=entry.return_shape,
    )


def wildcard_static_import_binding(
    owner: str,
    member: str,
    ctx: TranslationContext,
    *,
    kind: JavaMemberKind = "unknown",
) -> JavaMemberBinding | None:
    """Resolve a wildcard static import using local/configured member facts only."""
    configured = configured_member_binding(
        f"{owner}.{member}",
        ctx.cfg,
        source="wildcard_static_import",
    )
    if configured is not None:
        if kind != "unknown" and configured.kind == "unknown":
            return JavaMemberBinding(
                owner=configured.owner,
                member=configured.member,
                kind=kind,
                source=configured.source,
                python_owner=configured.python_owner,
                python_member=configured.python_member,
                intrinsic=configured.intrinsic,
                return_type=configured.return_type,
                return_shape=configured.return_shape,
            )
        return configured

    simple_owner = owner.rsplit(".", 1)[-1]
    py_owner = translate_class_name(simple_owner)
    py_member = (
        translate_field_name(member, snake_case=ctx.cfg.snake_case_fields)
        if kind == "field"
        else _translate_member_method_name(member, ctx.cfg)
    )
    local_static_methods = ctx.declared_type_method_return_types.get(py_owner) or {}
    local_static_fields = ctx.declared_type_java_fields.get(py_owner) or {}
    if kind in {"method", "unknown"} and member in local_static_methods:
        return JavaMemberBinding(
            owner=owner,
            member=member,
            kind="method",
            source="wildcard_static_import",
            python_owner=py_owner,
            python_member=py_member,
            return_type=local_static_methods.get(member),
        )
    if kind in {"field", "unknown"} and member in local_static_fields:
        return JavaMemberBinding(
            owner=owner,
            member=member,
            kind="field",
            source="wildcard_static_import",
            python_owner=py_owner,
            python_member=py_member,
            return_type=local_static_fields.get(member),
        )
    return None


def resolve_unqualified_member(
    member: str,
    ctx: TranslationContext,
    *,
    kind: JavaMemberKind = "method",
) -> JavaMemberBinding | None:
    """Resolve a receiverless member reference from shared class/static bindings."""
    py_method = _translate_member_method_name(member, ctx.cfg)
    py_field = translate_field_name(member, snake_case=ctx.cfg.snake_case_fields)
    if kind in {"method", "unknown"}:
        static_py_method = ctx.static_instance_static_aliases.get(py_method, py_method)
        if static_py_method in ctx.class_static_methods and ctx.containing_class_name:
            return JavaMemberBinding(
                owner=ctx.containing_class_name,
                member=member,
                kind="method",
                source="same_class",
                python_owner=ctx.containing_class_name,
                python_member=static_py_method,
                return_type=ctx.class_method_return_types.get(member),
            )
        if member in ctx.self_dispatch_methods and ctx.in_instance_method:
            return JavaMemberBinding(
                owner=ctx.containing_class_name or "",
                member=member,
                kind="method",
                source="same_class",
                python_owner="self",
                python_member=py_method,
                return_type=ctx.class_method_return_types.get(member),
            )
        if ctx.in_instance_method and py_method in ctx.class_methods:
            return JavaMemberBinding(
                owner=ctx.containing_class_name or "",
                member=member,
                kind="method",
                source="same_class",
                python_owner="self",
                python_member=py_method,
                return_type=ctx.class_method_return_types.get(member),
            )
        inherited_owner = ctx.enclosing_static_dispatch.get(py_method)
        if inherited_owner is not None:
            return JavaMemberBinding(
                owner=inherited_owner,
                member=member,
                kind="method",
                source="inherited",
                python_owner=inherited_owner,
                python_member=static_py_method,
            )
    if kind in {"field", "unknown"}:
        if member in ctx.class_fields and ctx.in_instance_method:
            return JavaMemberBinding(
                owner=ctx.containing_class_name or "",
                member=member,
                kind="field",
                source="same_class",
                python_owner="self",
                python_member=py_field,
                return_type=ctx.class_field_java_types.get(member),
            )
        if member in ctx.class_field_java_types and ctx.containing_class_name:
            return JavaMemberBinding(
                owner=ctx.containing_class_name,
                member=member,
                kind="field",
                source="same_class",
                python_owner=ctx.containing_class_name,
                python_member=py_field,
                return_type=ctx.class_field_java_types.get(member),
            )
    return None


def java_type_shape_of_value(
    node: JavaNode,
    ctx: TranslationContext,
) -> JavaTypeShape | None:
    """Return Java type-shape facts for a value expression when locally knowable."""
    from j2py.translate.java_types import java_expression_type

    java_type = java_expression_type(node, ctx)
    if java_type is None:
        return None
    return java_type_shape(java_type, ctx.cfg)


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
        return f"{binding.python_member}({', '.join(args)})"
    py_method = binding.python_member
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

"""Shared overload signature and stub helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode
from j2py.translate.annotation_types import bind_annotation_type_names
from j2py.translate.class_members import member_python_name
from j2py.translate.class_methods import method_body, parameter_infos
from j2py.translate.class_methods import return_type as method_return_type
from j2py.translate.class_methods import signature as render_method_signature
from j2py.translate.class_model import _modifiers
from j2py.translate.diagnostics import TranslationDiagnostics

if TYPE_CHECKING:
    from j2py.translate.diagnostics import TranslationContext


def _java_simple_type(java_type: str) -> str:
    base = java_type.strip()
    while base.startswith("@"):
        _, _, base = base.partition(" ")
        base = base.strip()
    base = base.split("<", 1)[0].strip()
    while base.endswith("[]"):
        base = base[:-2].strip()
    return base.rsplit(".", 1)[-1]


def _erased_overload_signature(member: JavaNode, cfg: TranslationConfig) -> tuple[str, ...]:
    return tuple(
        ("*" if param.is_spread else "") + _erase_py_type(param.py_type)
        for param in parameter_infos(member, cfg)
    )


def _erase_py_type(py_type: str) -> str:
    """Reduce a Python annotation to the part isinstance dispatch can see."""
    text = py_type.strip()
    prefix = ""
    if text.startswith("*"):
        prefix, text = "*", text[1:].strip()
    parts = _split_top_level_union(text)
    if len(parts) > 1:
        return prefix + " | ".join(sorted({_erase_py_type(part) for part in parts}))
    base = text.split("[", 1)[0].strip()
    if base in {"Callable", "typing.Callable", "collections.abc.Callable"}:
        base = "Callable"
    return prefix + base


def _split_top_level_union(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "|" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _union_types(types: Iterable[str]) -> str:
    unique: list[str] = []
    for py_type in types:
        if py_type not in unique:
            unique.append(py_type)
    return " | ".join(unique)


def _readable_signature(member: JavaNode, cfg: TranslationConfig) -> str:
    params = ", ".join(
        f"{'*' if param.is_spread else ''}{param.py_name}: {param.py_type}"
        for param in parameter_infos(member, cfg)
    )
    return f"{member_python_name(member)}({params})"


def _has_this_delegation(member: JavaNode) -> bool:
    body = method_body(member)
    if body is None:
        return False
    for invocation in body.find_all("explicit_constructor_invocation"):
        target = invocation.named_children[0] if invocation.named_children else None
        if target is not None and target.type == "this":
            return True
    return False


def _overload_stubs(
    members: list[JavaNode],
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    *,
    python_name_for_member: Callable[[JavaNode], str] | None = None,
    ctx: TranslationContext | None = None,
) -> list[str]:
    diagnostics.imports.need_typing("overload")
    lines: list[str] = []
    for member in members:
        is_static = "static" in _modifiers(member)
        if is_static:
            lines.append("    @staticmethod")
        lines.append("    @overload")
        params = parameter_infos(member, cfg)
        return_type = (
            "None" if member.type == "constructor_declaration" else method_return_type(member, cfg)
        )
        if ctx is not None:
            params = [
                type(param)(
                    raw_name=param.raw_name,
                    py_name=param.py_name,
                    py_type=bind_annotation_type_names(param.py_type, ctx),
                    java_type=param.java_type,
                    is_spread=param.is_spread,
                    py_annotations=param.py_annotations,
                )
                for param in params
            ]
            return_type = bind_annotation_type_names(return_type, ctx)
        if cfg.emit_type_hints:
            diagnostics.imports.need_type_annotation(return_type)
            for param in params:
                diagnostics.imports.need_type_annotation(param.py_type)
        py_name = (
            python_name_for_member(member)
            if python_name_for_member is not None
            else member_python_name(member)
        )
        signature = render_method_signature(
            py_name,
            params,
            return_type=return_type,
            include_self=not is_static,
            emit_type_hints=cfg.emit_type_hints,
        )
        lines.append(f"    {signature}: ...")
    return lines


def _static_instance_overload_stubs(
    members: list[JavaNode],
    *,
    canonical_name: str,
    static_name: str,
    cfg: TranslationConfig,
    diagnostics: TranslationDiagnostics,
    ctx: TranslationContext | None = None,
) -> list[str]:
    def python_name_for_member(member: JavaNode) -> str:
        if "static" in _modifiers(member):
            return static_name
        return canonical_name

    return _overload_stubs(
        members,
        cfg,
        diagnostics,
        python_name_for_member=python_name_for_member,
        ctx=ctx,
    )

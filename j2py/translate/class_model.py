"""Shared class translation metadata and small class-node helpers."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.parse.java_ast import JavaNode

TYPE_DECLARATION_NODES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}


@dataclass(frozen=True)
class FieldInfo:
    node: JavaNode
    name: str
    py_name: str
    java_type: str
    py_type: str
    is_static: bool
    initializer: JavaNode | None


@dataclass(frozen=True)
class ParameterInfo:
    raw_name: str
    py_name: str
    py_type: str
    is_spread: bool = False


def _modifiers(node: JavaNode) -> set[str]:
    modifiers: set[str] = set()
    for modifier_node in node.children_by_type("modifiers"):
        modifiers.update(modifier_node.text.split())
    return modifiers

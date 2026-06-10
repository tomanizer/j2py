"""Small tree-sitter node helpers used by the skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode


def first_child_by_type(node: JavaNode, *types: str) -> JavaNode | None:
    for child in node.named_children:
        if child.type in types:
            return child
    return None


def direct_children_by_type(node: JavaNode, *types: str) -> list[JavaNode]:
    return [child for child in node.named_children if child.type in types]


def class_body_needs_pass(lines: list[str]) -> bool:
    class_body_lines = lines[1:]
    if not class_body_lines:
        return True
    return all(not line.strip() or line.lstrip().startswith("#") for line in class_body_lines)

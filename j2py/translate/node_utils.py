"""Small tree-sitter node helpers used by the skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode


def unwrap_parens(node: JavaNode) -> JavaNode:
    """Strip nested parenthesized_expression wrappers, returning the inner node."""
    while node.type == "parenthesized_expression" and len(node.named_children) == 1:
        node = node.named_children[0]
    return node


def first_child_by_type(node: JavaNode, *types: str) -> JavaNode | None:
    for child in node.named_children:
        if child.type in types:
            return child
    return None


def direct_children_by_type(node: JavaNode, *types: str) -> list[JavaNode]:
    return [child for child in node.named_children if child.type in types]


def class_body_needs_pass(lines: list[str]) -> bool:
    class_header_index = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("class ")),
        None,
    )
    if class_header_index is None:
        return True
    class_body_lines = lines[class_header_index + 1 :]
    if not class_body_lines:
        return True
    return all(not line.strip() or line.lstrip().startswith("#") for line in class_body_lines)

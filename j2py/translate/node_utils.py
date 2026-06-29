"""Small tree-sitter node helpers used by the skeleton translator."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.comments import is_comment


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


def ternary_expression_operands(node: JavaNode) -> tuple[JavaNode, JavaNode, JavaNode] | None:
    condition = node.child_by_field("condition")
    consequence = node.child_by_field("consequence")
    alternative = node.child_by_field("alternative")
    if condition is not None and consequence is not None and alternative is not None:
        return condition, consequence, alternative

    children = [child for child in node.named_children if not is_comment(child)]
    if len(children) == 3:
        return children[0], children[1], children[2]
    return None


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


def reindent_helper_lines(
    helper_lines: list[str],
    *,
    target_base_indent: str,
    source_base_indent: str = "        ",
) -> list[str]:
    indent_shift = len(target_base_indent) - len(source_base_indent)
    reindented: list[str] = []
    for line in helper_lines:
        if not line.strip():
            reindented.append(line)
            continue
        leading_spaces = len(line) - len(line.lstrip(" "))
        new_leading = max(0, leading_spaces + indent_shift)
        reindented.append(" " * new_leading + line.lstrip(" "))
    return reindented

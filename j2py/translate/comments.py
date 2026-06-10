"""Comment normalization for skeleton translation."""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode

COMMENT_TYPES = frozenset({"line_comment", "block_comment"})


def is_comment(node: JavaNode) -> bool:
    return node.type in COMMENT_TYPES


def translate_comment(node: JavaNode, *, indent: str) -> list[str]:
    if node.type == "line_comment":
        text = node.text.removeprefix("//").strip()
        return [f"{indent}# {text}"] if text else []

    if node.type == "block_comment":
        return [f"{indent}# {line}" for line in _block_comment_lines(node.text)]

    return []


def _block_comment_lines(text: str) -> list[str]:
    text = text.strip()
    if text.startswith("/**"):
        text = text[3:]
    elif text.startswith("/*"):
        text = text[2:]
    if text.endswith("*/"):
        text = text[:-2]

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("*"):
            line = line[1:].strip()
        if line:
            lines.append(line)
    return lines

"""Comment and Javadoc normalization for skeleton translation."""

from __future__ import annotations

import re

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


def is_javadoc_comment(node: JavaNode) -> bool:
    return node.type == "block_comment" and node.text.strip().startswith("/**")


def translate_javadoc_docstring(node: JavaNode, *, indent: str) -> list[str]:
    body = _javadoc_docstring_body(node.text)
    if not body:
        return []
    if len(body) == 1:
        return [f'{indent}"""{_escape_docstring_line(body[0])}"""']

    lines = [f'{indent}"""{_escape_docstring_line(body[0])}']
    lines.extend(f"{indent}{_escape_docstring_line(line)}" if line else "" for line in body[1:])
    lines.append(f'{indent}"""')
    return lines


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


def _javadoc_docstring_body(text: str) -> list[str]:
    description: list[str] = []
    params: list[tuple[str, str]] = []
    returns: list[str] = []
    raises: list[tuple[str, str]] = []
    deprecated: list[str] = []
    notes: list[str] = []

    for raw_line in _javadoc_lines(text):
        line = _normalize_javadoc_inline(raw_line)
        if not line:
            if description and description[-1] != "":
                description.append("")
            continue
        if line.startswith("@param "):
            _, rest = line.split("@param ", 1)
            name, _, detail = rest.strip().partition(" ")
            params.append((name, detail.strip()))
            continue
        if line.startswith("@return "):
            returns.append(line.removeprefix("@return ").strip())
            continue
        if line.startswith(("@throws ", "@exception ")):
            _, rest = line.split(" ", 1)
            exc, _, detail = rest.strip().partition(" ")
            raises.append((exc, detail.strip()))
            continue
        if line.startswith("@deprecated"):
            deprecated.append(line.removeprefix("@deprecated").strip())
            continue
        if line.startswith("@since "):
            continue
        if line.startswith("@apiNote"):
            notes.append(f"API note: {line.removeprefix('@apiNote').strip()}")
            continue
        if line.startswith("@implNote"):
            notes.append(f"Implementation note: {line.removeprefix('@implNote').strip()}")
            continue
        if line.startswith("@see "):
            notes.append(f"See: {line.removeprefix('@see ').strip()}")
            continue
        description.append(line)

    body = _trim_blank_lines(description)
    for note in notes:
        if body and body[-1] != "":
            body.append("")
        body.append(note)
    if deprecated:
        if body and body[-1] != "":
            body.append("")
        body.append(".. deprecated:: " + " ".join(deprecated).strip())
    if params:
        if body and body[-1] != "":
            body.append("")
        body.append("Args:")
        body.extend(
            f"    {name}: {detail}" if detail else f"    {name}:" for name, detail in params
        )
    if returns:
        if body and body[-1] != "":
            body.append("")
        body.append("Returns:")
        body.extend(f"    {line}" for line in returns)
    if raises:
        if body and body[-1] != "":
            body.append("")
        body.append("Raises:")
        body.extend(f"    {exc}: {detail}" if detail else f"    {exc}:" for exc, detail in raises)
    return _trim_blank_lines(body)


def _javadoc_lines(text: str) -> list[str]:
    text = text.strip()
    if text.startswith("/**"):
        text = text[3:]
    if text.endswith("*/"):
        text = text[:-2]

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("*"):
            line = line[1:].strip()
        lines.append(line)
    return lines


def _normalize_javadoc_inline(line: str) -> str:
    line = line.replace("<p>", "").replace("</p>", "")
    line = line.replace("<pre>", "Code:").replace("</pre>", "")
    line = re.sub(r"\{@code\s+([^}]+)\}", r"`\1`", line)
    line = re.sub(r"\{@literal\s+([^}]+)\}", r"\1", line)
    line = re.sub(
        r"\{@(?:link|linkplain)\s+#?([^}]*\([^)]*\)|[^\s}]+)(?:\s+[^}]*)?\}",
        lambda match: f"`{match.group(1)}`",
        line,
    )
    line = re.sub(r"\{@value\s+([^}]+)\}", r"\1", line)
    line = re.sub(r"<[^>]+>", "", line)
    return " ".join(line.split())


def _trim_blank_lines(lines: list[str]) -> list[str]:
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _escape_docstring_line(line: str) -> str:
    return line.replace('"""', r"\"\"\"")

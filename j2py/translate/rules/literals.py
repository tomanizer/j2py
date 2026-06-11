"""Literal and keyword token translations."""

from __future__ import annotations

import ast
import re

from j2py.config.loader import TranslationConfig


def translate_literal(token: str, cfg: TranslationConfig) -> str:
    """Map a Java literal token to its Python equivalent."""
    if token in cfg.literal_map:
        return cfg.literal_map[token]

    # Long suffix: 100L, 0xFFL, 0b1010L → suffixless Python integer
    if re.match(r"^(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|\d[\d_]*)[Ll]$", token):
        token = token[:-1]

    # Float suffix: 1.0f, 1.0F → 1.0
    if re.match(r"^[\d.]+[fF]$", token):
        return token[:-1]

    # Double suffix: 1.0d → 1.0
    if re.match(r"^[\d.]+[dD]$", token):
        return token[:-1]

    # Hex: 0xFF → same in Python
    # Binary: 0b1010 → same in Python
    # Underscore separators: 1_000_000 → same in Python

    # Java octal: 0777 → Python 0o777
    if re.match(r"^0[0-7_]+$", token) and not token.lower().startswith("0o"):
        digits = token[1:].lstrip("_") or "0"
        return f"0o{digits}"

    # Char literal: 'a' → "a"
    if re.match(r"^'[^']'$", token) or re.match(r"^'\\.'$", token):
        inner = token[1:-1]
        return f'"{inner}"'

    return token


def translate_string_literal(token: str) -> str:
    """Translate a Java string literal token into a Python string literal."""
    if not _is_text_block(token):
        return token
    return _python_triple_quoted_string(java_string_literal_value(token))


def java_string_literal_value(token: str) -> str:
    """Return the runtime string value for Java string literals we translate."""
    if not _is_text_block(token):
        return str(ast.literal_eval(token))
    return _decode_text_block_escapes(_strip_text_block_indent(token))


def _is_text_block(token: str) -> bool:
    return token.startswith('"""') and token.endswith('"""')


def _strip_text_block_indent(token: str) -> str:
    content = token[3:-3].replace("\r\n", "\n").replace("\r", "\n")
    if content.startswith("\n"):
        content = content[1:]

    lines = content.split("\n")
    indents = [_indent_width(line) for line in lines if line.strip()]
    if lines and not lines[-1].strip():
        indents.append(_indent_width(lines[-1]))
    indent = min(indents, default=0)
    if indent:
        lines = [_remove_indent(line, indent) for line in lines]
    return "\n".join(lines)


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _remove_indent(line: str, width: int) -> str:
    index = 0
    remaining = width
    while index < len(line) and remaining and line[index] in {" ", "\t"}:
        index += 1
        remaining -= 1
    return line[index:]


def _decode_text_block_escapes(content: str) -> str:
    escapes = {
        "b": "\b",
        "t": "\t",
        "n": "\n",
        "f": "\f",
        "r": "\r",
        '"': '"',
        "'": "'",
        "\\": "\\",
        "s": " ",
    }
    decoded: list[str] = []
    index = 0
    while index < len(content):
        char = content[index]
        if char != "\\" or index == len(content) - 1:
            decoded.append(char)
            index += 1
            continue

        escape = content[index + 1]
        if escape == "\n":
            index += 2
            continue
        if escape in escapes:
            decoded.append(escapes[escape])
            index += 2
            continue
        if escape in "01234567":
            max_len = 3 if escape in "0123" else 2
            end = index + 2
            while end < min(index + 1 + max_len, len(content)) and content[end] in "01234567":
                end += 1
            decoded.append(chr(int(content[index + 1 : end], 8)))
            index = end
            continue
        if escape == "u":
            match = re.match(r"u+([0-9a-fA-F]{4})", content[index + 1 :])
            if match is not None:
                decoded.append(chr(int(match.group(1), 16)))
                index += 1 + len(match.group(0))
                continue

        decoded.append(f"\\{escape}")
        index += 2
    return "".join(decoded)


def _python_triple_quoted_string(value: str) -> str:
    if any(ord(char) < 32 and char not in {"\n", "\t", "\r", "\f", "\b"} for char in value):
        return repr(value)

    delimiter = '"""'
    if delimiter in value or value.endswith('"'):
        delimiter = "'''"
    if delimiter in value or value.endswith(delimiter[0]):
        return repr(value)

    escaped = value.replace("\\", "\\\\")
    return f"{delimiter}{escaped}{delimiter}"

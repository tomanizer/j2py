"""Escaped counter serialization for corpus diagnostics."""

from __future__ import annotations

from collections import Counter


def counter_summary(counter: Counter[str]) -> str:
    return ";".join(
        f"{_escape_counter_key(key)}:{value}" for key, value in sorted(counter.items())
    )


def parse_counter_summary(value: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not value:
        return counter
    for part in _split_escaped(value, ";"):
        if ":" not in part:
            continue
        key, raw_count = part.rsplit(":", 1)
        counter[_unescape_counter_key(key)] = int(raw_count)
    return counter


def _escape_counter_key(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;")


def _unescape_counter_key(value: str) -> str:
    result: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    if escaped:
        result.append("\\")
    return "".join(result)


def _split_escaped(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            current.extend(("\\", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    parts.append("".join(current))
    return parts

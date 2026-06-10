"""Identifier naming conventions: camelCase → snake_case, reserved word handling."""

from __future__ import annotations

import keyword
import re


PYTHON_BUILTINS: frozenset[str] = frozenset(
    {"abs", "all", "any", "bin", "bool", "breakpoint", "bytearray", "bytes",
     "callable", "chr", "compile", "complex", "copyright", "credits", "delattr",
     "dict", "dir", "divmod", "enumerate", "eval", "exec", "exit", "filter",
     "float", "format", "frozenset", "getattr", "globals", "hasattr", "hash",
     "help", "hex", "id", "input", "int", "isinstance", "issubclass", "iter",
     "len", "license", "list", "locals", "map", "max", "memoryview", "min",
     "next", "object", "oct", "open", "ord", "pow", "print", "property",
     "quit", "range", "repr", "reversed", "round", "set", "setattr", "slice",
     "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars",
     "zip"}
)

_RESERVED: frozenset[str] = frozenset(keyword.kwlist) | PYTHON_BUILTINS


def camel_to_snake(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case.

    Examples:
        "myVariable"   → "my_variable"
        "getHTTPCode"  → "get_http_code"
        "XMLParser"    → "xml_parser"
    """
    # Insert _ before runs of uppercase followed by lowercase (e.g. HTTPCode → HTTP_Code)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    # Insert _ before uppercase that follows lowercase/digit
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def safe_identifier(name: str) -> str:
    """Append trailing underscore if `name` collides with a Python keyword or builtin."""
    if name in _RESERVED:
        return f"{name}_"
    return name


def translate_method_name(name: str) -> str:
    return safe_identifier(camel_to_snake(name))


def translate_field_name(name: str) -> str:
    return safe_identifier(camel_to_snake(name))


def translate_class_name(name: str) -> str:
    """Class names stay PascalCase; only reserved-word collision needs fixing."""
    return safe_identifier(name)

"""Pure transform functions for individual Java AST nodes → Python text.

Each function takes a JavaNode and returns a Python string replacement,
or None to signal "no change / fall through to next layer".

These are wired into the selector rules table in rules/*.py.
"""

from __future__ import annotations

from j2py.parse.java_ast import JavaNode
from j2py.translate.rules.naming import camel_to_snake


# ---------------------------------------------------------------------------
# Literal transforms
# ---------------------------------------------------------------------------

def null_to_none(node: JavaNode) -> str:
    return "None"


def true_to_true(node: JavaNode) -> str:
    return "True"


def false_to_false(node: JavaNode) -> str:
    return "False"


def this_to_self(node: JavaNode) -> str:
    return "self"


# ---------------------------------------------------------------------------
# Common method call transforms
# ---------------------------------------------------------------------------

def length_to_len(node: JavaNode) -> str:
    """Transform obj.length() → len(obj) — detected at the call-site level."""
    # Note: caller is responsible for restructuring the method invocation node
    return "len"


def to_string_to_str(node: JavaNode) -> str:
    return "str"


def equals_to_eq(node: JavaNode) -> str:
    """obj.equals(other) → obj == other — detected at call-site."""
    return "=="


# ---------------------------------------------------------------------------
# Operator transforms
# ---------------------------------------------------------------------------

def instanceof_to_isinstance(node: JavaNode) -> str:
    """expr instanceof Type → isinstance(expr, Type)."""
    # This is handled structurally in the visitor, not here
    return "isinstance"


# ---------------------------------------------------------------------------
# Factory helpers — make parametric transforms
# ---------------------------------------------------------------------------

def make_const(value: str):
    """Return a transform that always replaces the node text with `value`."""
    def _transform(node: JavaNode) -> str:
        return value
    _transform.__name__ = f"const_{value}"
    return _transform


def keyword_safe(node: JavaNode) -> str | None:
    """Append _ to identifiers that are Python keywords/builtins."""
    import keyword
    from j2py.translate.rules.naming import PYTHON_BUILTINS
    text = node.text
    if text in keyword.kwlist or text in PYTHON_BUILTINS:
        return f"{text}_"
    return None

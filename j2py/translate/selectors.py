"""Declarative AST selectors for targeting Java nodes — inspired by java2python.

Usage:
    rule = (NodeType("method_declaration"), my_transform_fn)
    rule = (HasChild(NodeType("modifier"), text="static"), handle_static)
    rule = (And(NodeType("identifier"), Text("length")), length_to_len)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from j2py.parse.java_ast import JavaNode


class Selector(ABC):
    """Base class for AST node selectors."""

    @abstractmethod
    def matches(self, node: JavaNode) -> bool: ...

    def __and__(self, other: Selector) -> And:
        return And(self, other)

    def __or__(self, other: Selector) -> Or:
        return Or(self, other)

    def __invert__(self) -> Not:
        return Not(self)


class NodeType(Selector):
    """Matches nodes of a specific tree-sitter type."""

    def __init__(self, *types: str) -> None:
        self.types = frozenset(types)

    def matches(self, node: JavaNode) -> bool:
        return node.type in self.types


class Text(Selector):
    """Matches nodes whose full text equals the given string."""

    def __init__(self, text: str) -> None:
        self.text = text

    def matches(self, node: JavaNode) -> bool:
        return node.text == self.text


class TextIn(Selector):
    """Matches nodes whose text is in the given set."""

    def __init__(self, *texts: str) -> None:
        self.texts = frozenset(texts)

    def matches(self, node: JavaNode) -> bool:
        return node.text in self.texts


class HasChild(Selector):
    """Matches nodes that have at least one child matching the inner selector."""

    def __init__(self, inner: Selector) -> None:
        self.inner = inner

    def matches(self, node: JavaNode) -> bool:
        return any(self.inner.matches(c) for c in node.children)


class And(Selector):
    def __init__(self, *selectors: Selector) -> None:
        self.selectors = selectors

    def matches(self, node: JavaNode) -> bool:
        return all(s.matches(node) for s in self.selectors)


class Or(Selector):
    def __init__(self, *selectors: Selector) -> None:
        self.selectors = selectors

    def matches(self, node: JavaNode) -> bool:
        return any(s.matches(node) for s in self.selectors)


class Not(Selector):
    def __init__(self, inner: Selector) -> None:
        self.inner = inner

    def matches(self, node: JavaNode) -> bool:
        return not self.inner.matches(node)


# ---------------------------------------------------------------------------
# Transform function type
# ---------------------------------------------------------------------------

TransformFn = Callable[[JavaNode], str | None]
Rule = tuple[Selector, TransformFn]


def apply_rules(node: JavaNode, rules: list[Rule]) -> str | None:
    """Apply the first matching rule to `node` and return the result.

    Returns None if no rule matches (caller should handle the node normally).
    """
    for selector, transform in rules:
        if selector.matches(node):
            return transform(node)
    return None

"""Java source parsing via tree-sitter.

Wraps tree-sitter-java to provide a clean interface for traversing
Java ASTs and extracting node text/metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import tree_sitter_java as ts_java
from tree_sitter import Language, Node, Parser


JAVA_LANGUAGE = Language(ts_java.language())


@dataclass(frozen=True)
class SourceLocation:
    line: int        # 1-based
    column: int      # 0-based
    end_line: int
    end_column: int


@dataclass
class JavaNode:
    """Thin wrapper around a tree-sitter Node with convenience helpers."""

    node: Node
    source: bytes

    @property
    def type(self) -> str:
        return self.node.type

    @property
    def text(self) -> str:
        return self.source[self.node.start_byte:self.node.end_byte].decode("utf-8")

    @property
    def location(self) -> SourceLocation:
        sr, sc = self.node.start_point
        er, ec = self.node.end_point
        return SourceLocation(sr + 1, sc, er + 1, ec)

    @property
    def children(self) -> list[JavaNode]:
        return [JavaNode(c, self.source) for c in self.node.children]

    @property
    def named_children(self) -> list[JavaNode]:
        return [JavaNode(c, self.source) for c in self.node.named_children]

    def child_by_field(self, field_name: str) -> JavaNode | None:
        c = self.node.child_by_field_name(field_name)
        return JavaNode(c, self.source) if c else None

    def children_by_type(self, *types: str) -> list[JavaNode]:
        return [c for c in self.children if c.type in types]

    def walk(self) -> Iterator[JavaNode]:
        """Pre-order traversal of the subtree."""
        yield self
        for child in self.named_children:
            yield from child.walk()

    def find_all(self, *node_types: str) -> Iterator[JavaNode]:
        """Yield all descendant nodes matching any of the given types."""
        for node in self.walk():
            if node.type in node_types:
                yield node

    def __repr__(self) -> str:
        loc = self.location
        return f"JavaNode({self.type!r}, line={loc.line}, text={self.text[:40]!r})"


@dataclass
class ParsedFile:
    path: Path
    source: bytes
    root: JavaNode
    errors: list[JavaNode] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def parse_file(path: Path) -> ParsedFile:
    source = path.read_bytes()
    return parse_source(source, path=path)


def parse_source(source: bytes | str, *, path: Path | None = None) -> ParsedFile:
    if isinstance(source, str):
        source = source.encode("utf-8")

    parser = Parser(JAVA_LANGUAGE)
    tree = parser.parse(source)
    root = JavaNode(tree.root_node, source)
    errors = list(root.find_all("ERROR", "MISSING"))

    return ParsedFile(
        path=path or Path("<string>"),
        source=source,
        root=root,
        errors=errors,
    )

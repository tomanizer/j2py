"""Tests for dependency graph ordering."""

from pathlib import Path

import pytest

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import ClassSymbol, FileSymbols


def _symbols(path: str, class_name: str, *, superclass: str | None = None) -> FileSymbols:
    return FileSymbols(
        path=Path(path),
        package="com.example",
        classes=[ClassSymbol(name=class_name, package="com.example", superclass=superclass)],
    )


def test_translation_order_places_dependencies_first() -> None:
    base = _symbols("Base.java", "Base")
    child = _symbols("Child.java", "Child", superclass="Base")

    graph = build_dependency_graph([child, base])

    assert translation_order(graph) == ["Base.java", "Child.java"]


def test_translation_order_warns_and_returns_cycle_members() -> None:
    a = _symbols("A.java", "A", superclass="B")
    b = _symbols("B.java", "B", superclass="A")

    graph = build_dependency_graph([a, b])

    with pytest.warns(UserWarning, match="Circular dependencies"):
        order = translation_order(graph)

    assert sorted(order) == ["A.java", "B.java"]

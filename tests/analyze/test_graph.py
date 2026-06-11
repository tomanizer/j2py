"""Tests for dependency graph ordering."""

from pathlib import Path

import pytest

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import ClassSymbol, FileSymbols, extract_symbols
from j2py.parse.java_ast import parse_source


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


def test_dependency_graph_uses_imports_and_parsed_inheritance() -> None:
    base = parse_source("package com.example; public class Base {}")
    base.path = Path("Base.java")
    imported = parse_source(
        """
        package com.example.child;
        import com.example.Base;
        public class Child extends Base {}
        """,
    )
    imported.path = Path("Child.java")

    graph = build_dependency_graph([extract_symbols(imported), extract_symbols(base)])

    assert translation_order(graph) == ["Base.java", "Child.java"]


def test_dependency_graph_uses_nested_dependencies_without_extra_nodes() -> None:
    base = parse_source("package com.example; public class Base {}")
    base.path = Path("Base.java")
    outer = parse_source(
        """
        package com.example;
        public class Outer {
            public static class Inner extends Base {}
        }
        """,
    )
    outer.path = Path("Outer.java")

    graph = build_dependency_graph([extract_symbols(outer), extract_symbols(base)])

    assert sorted(graph.nodes) == ["Base.java", "Outer.java"]
    assert translation_order(graph) == ["Base.java", "Outer.java"]


def test_dependency_graph_skips_ambiguous_simple_name_superclasses() -> None:
    user_a = FileSymbols(
        path=Path("com/a/User.java"),
        package="com.a",
        classes=[ClassSymbol(name="User", package="com.a")],
    )
    user_b = FileSymbols(
        path=Path("com/b/User.java"),
        package="com.b",
        classes=[ClassSymbol(name="User", package="com.b")],
    )
    child = FileSymbols(
        path=Path("com/c/Child.java"),
        package="com.c",
        classes=[ClassSymbol(name="Child", package="com.c", superclass="User")],
    )

    graph = build_dependency_graph([user_a, user_b, child])

    assert list(graph.edges()) == []


def test_dependency_graph_prefers_same_package_before_ambiguous_simple_name() -> None:
    user_a = FileSymbols(
        path=Path("com/a/User.java"),
        package="com.a",
        classes=[ClassSymbol(name="User", package="com.a")],
    )
    user_b = FileSymbols(
        path=Path("com/b/User.java"),
        package="com.b",
        classes=[ClassSymbol(name="User", package="com.b")],
    )
    child = FileSymbols(
        path=Path("com/a/Child.java"),
        package="com.a",
        classes=[ClassSymbol(name="Child", package="com.a", superclass="User")],
    )

    graph = build_dependency_graph([user_a, user_b, child])

    assert ("com/a/Child.java", "com/a/User.java") in graph.edges()
    assert ("com/a/Child.java", "com/b/User.java") not in graph.edges()


def test_dependency_graph_resolves_unambiguous_simple_names() -> None:
    base = _symbols("Base.java", "Base")
    child = _symbols("Child.java", "Child", superclass="Base")

    graph = build_dependency_graph([child, base])

    assert translation_order(graph) == ["Base.java", "Child.java"]

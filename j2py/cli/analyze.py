"""Implementation for the ``j2py analyze`` command."""

from __future__ import annotations

import warnings
from pathlib import Path

import networkx as nx
import typer

from j2py.analyze.symbols import ClassSymbol, class_kind
from j2py.cli.output import console


def analyze(
    source: Path = typer.Argument(..., help="Java file or directory to analyze."),
) -> None:
    """Print class inventory, dependency graph, and parse-error status without translating."""
    from j2py.analyze.graph import build_dependency_graph
    from j2py.analyze.symbols import extract_symbols
    from j2py.parse.java_ast import parse_file

    if not source.exists():
        console.print(f"[red]Error:[/red] source path not found: {source}")
        raise typer.Exit(code=1)

    java_files = sorted(source.rglob("*.java")) if source.is_dir() else [source]
    if not java_files:
        console.print("[yellow]No .java files found.[/yellow]")
        return

    all_symbols = []
    for jf in java_files:
        parsed = parse_file(jf)
        symbols = extract_symbols(parsed)
        all_symbols.append(symbols)
        console.print(f"\n[bold]{jf}[/bold] — package: {symbols.package}")
        if parsed.has_errors:
            console.print("  [yellow]Parse errors detected in source[/yellow]")
        for cls in symbols.classes:
            _print_class_inventory(cls, indent=2)

    graph = build_dependency_graph(all_symbols)
    root = source if source.is_dir() else source.parent
    _print_dependency_graph(graph, root=root)


def _print_class_inventory(cls: ClassSymbol, *, indent: int) -> None:
    console.print(_format_class_inventory_line(cls, indent=indent))
    for inner in cls.inner_classes:
        _print_class_inventory(inner, indent=indent + 2)


def _format_class_inventory_line(cls: ClassSymbol, *, indent: int) -> str:
    padding = " " * indent
    return (
        f"{padding}{cls.name} ({class_kind(cls)}) — "
        f"{len(cls.methods)} methods, {len(cls.fields)} fields"
    )


def _relative_display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _print_dependency_graph(graph: nx.DiGraph, *, root: Path) -> None:
    if graph.number_of_nodes() == 0:
        return

    console.print("\n[bold]Dependency graph[/bold] (A → B means A depends on B):")
    edges = sorted(graph.edges(), key=lambda edge: (edge[0], edge[1]))
    if edges:
        for src, dep in edges:
            console.print(
                f"  {_relative_display_path(Path(src), root)}"
                f" → {_relative_display_path(Path(dep), root)}"
            )
    else:
        console.print("  [dim]No cross-file dependencies resolved[/dim]")

    from j2py.analyze.graph import translation_order

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        order = translation_order(graph)
    for warning in caught:
        console.print(f"[yellow]Warning:[/yellow] {warning.message}")

    console.print("\n[bold]Translation order:[/bold]")
    for index, path in enumerate(order, start=1):
        console.print(f"  {index}. {_relative_display_path(Path(path), root)}")

"""Dependency graph for determining translation order.

Builds a directed graph of Java class dependencies so we can translate
leaf classes first (bottom-up), avoiding forward references in the output.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from j2py.analyze.symbols import FileSymbols


def build_dependency_graph(all_symbols: list[FileSymbols]) -> nx.DiGraph:
    """Return a directed graph where an edge A → B means A depends on B."""
    fqn_to_file: dict[str, Path] = {}
    for fs in all_symbols:
        for cls in fs.classes:
            fqn = f"{fs.package}.{cls.name}" if fs.package else cls.name
            fqn_to_file[fqn] = fs.path
            fqn_to_file[cls.name] = fs.path  # short name fallback

    graph: nx.DiGraph = nx.DiGraph()
    for fs in all_symbols:
        src = str(fs.path)
        graph.add_node(src)
        for cls in fs.classes:
            if cls.superclass and cls.superclass in fqn_to_file:
                dep = str(fqn_to_file[cls.superclass])
                if dep != src:
                    graph.add_edge(src, dep)
            for iface in cls.interfaces:
                if iface in fqn_to_file:
                    dep = str(fqn_to_file[iface])
                    if dep != src:
                        graph.add_edge(src, dep)
        for imp in fs.imports:
            if imp in fqn_to_file:
                dep = str(fqn_to_file[imp])
                if dep != src:
                    graph.add_edge(src, dep)

    return graph


def translation_order(graph: nx.DiGraph) -> list[str]:
    """Return file paths in topological order (dependencies first).

    Falls back to cycle-aware ordering if the graph has cycles
    (e.g., mutual dependencies — flag these for manual review).
    """
    try:
        return list(reversed(list(nx.topological_sort(graph))))
    except nx.NetworkXUnfeasible:
        # Cycle detected — use SCC condensation and sort within each SCC
        cycles = list(nx.simple_cycles(graph))
        cycle_nodes = {n for cycle in cycles for n in cycle}
        if cycle_nodes:
            import warnings
            warnings.warn(
                f"Circular dependencies detected between: {cycle_nodes}. "
                "Translation order within these classes may be incorrect.",
                stacklevel=2,
            )
        condensed = nx.condensation(graph)
        ordered_components = reversed(list(nx.topological_sort(condensed)))
        ordered_nodes: list[str] = []
        for component in ordered_components:
            ordered_nodes.extend(sorted(condensed.nodes[component]["members"]))
        return ordered_nodes

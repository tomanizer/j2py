"""Dependency graph for determining translation order.

Builds a directed graph of Java class dependencies so we can translate
leaf classes first (bottom-up), avoiding forward references in the output.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import networkx as nx

from j2py.analyze.symbols import ClassSymbol, FileSymbols


def build_dependency_graph(all_symbols: list[FileSymbols]) -> nx.DiGraph:
    """Return a directed graph where an edge A → B means A depends on B."""
    fqn_to_file: dict[str, Path] = {}
    simple_names: dict[str, list[str]] = defaultdict(list)

    for fs in all_symbols:
        for cls in _all_classes(fs.classes):
            fqn = _class_fqn(fs.package, cls.name)
            fqn_to_file[fqn] = fs.path
            simple_names[cls.name].append(fqn)

    unambiguous_short_names = {
        name: fqns[0]
        for name, fqns in simple_names.items()
        if len(fqns) == 1
    }

    graph: nx.DiGraph = nx.DiGraph()
    for fs in all_symbols:
        src = str(fs.path)
        graph.add_node(src)
        for cls in _all_classes(fs.classes):
            if cls.superclass:
                dep = _resolve_type_to_file(
                    cls.superclass,
                    fqn_to_file=fqn_to_file,
                    unambiguous_short_names=unambiguous_short_names,
                )
                if dep is not None and str(dep) != src:
                    graph.add_edge(src, str(dep))
            for iface in cls.interfaces:
                dep = _resolve_type_to_file(
                    iface,
                    fqn_to_file=fqn_to_file,
                    unambiguous_short_names=unambiguous_short_names,
                )
                if dep is not None and str(dep) != src:
                    graph.add_edge(src, str(dep))
        for imp in fs.imports:
            dep = _resolve_type_to_file(
                imp,
                fqn_to_file=fqn_to_file,
                unambiguous_short_names=unambiguous_short_names,
            )
            if dep is not None and str(dep) != src:
                graph.add_edge(src, str(dep))

    return graph


def _class_fqn(package: str, class_name: str) -> str:
    return f"{package}.{class_name}" if package else class_name


def _resolve_type_to_file(
    type_name: str,
    *,
    fqn_to_file: dict[str, Path],
    unambiguous_short_names: dict[str, str],
) -> Path | None:
    if type_name in fqn_to_file:
        return fqn_to_file[type_name]
    fqn = unambiguous_short_names.get(type_name)
    if fqn is None:
        return None
    return fqn_to_file.get(fqn)


def _all_classes(classes: list[ClassSymbol]) -> list[ClassSymbol]:
    result: list[ClassSymbol] = []
    for cls in classes:
        result.append(cls)
        result.extend(_all_classes(cls.inner_classes))
    return result


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

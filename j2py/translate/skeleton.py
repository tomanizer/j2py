"""Rule-based skeleton generator for the deterministic translation layer."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode, ParsedFile
from j2py.translate.classes import top_level_classes, translate_class
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.runtime import RUNTIME_IMPORT_LINE


@dataclass
class SkeletonTranslation:
    """Rule-layer output plus structured diagnostic details."""

    source: str
    coverage: float
    diagnostics: TranslationDiagnostics


def translate_skeleton(
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
) -> tuple[str, float]:
    """Produce a partial Python translation and a coverage estimate.

    Returns:
        (skeleton_source, coverage) where coverage is 0.0-1.0.
        Coverage < 1.0 triggers the LLM layer.
    """
    result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)
    return result.source, result.coverage


def translate_skeleton_with_diagnostics(
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
) -> SkeletonTranslation:
    """Produce a partial Python translation with structured coverage diagnostics."""
    diagnostics = TranslationDiagnostics()
    class_nodes = top_level_classes(parsed.root)

    class_blocks: list[list[str]] = []
    for class_node in class_nodes:
        class_blocks.append(translate_class(class_node, cfg, diagnostics))

    lines = ["from __future__ import annotations"]
    import_lines = _import_lines(parsed, cfg, class_blocks)
    if import_lines:
        lines.append("")
        lines.extend(import_lines)
    lines.extend(["", ""])

    for index, block in enumerate(class_blocks):
        if index:
            lines.append("")
            lines.append("")
        lines.extend(block)

    return SkeletonTranslation(
        source="\n".join(lines) + "\n",
        coverage=diagnostics.coverage,
        diagnostics=diagnostics,
    )


def _import_lines(
    parsed: ParsedFile,
    cfg: TranslationConfig,
    class_blocks: list[list[str]],
) -> list[str]:
    imports: set[str] = set()
    for java_import in parsed.root.find_all("import_declaration"):
        imported_name = _java_import_name(java_import)
        if not imported_name or imported_name in cfg.drop_imports:
            continue
        mapped = cfg.import_map.get(imported_name)
        if mapped:
            imports.update(line for line in mapped.splitlines() if line.strip())

    flattened = "\n".join(line for block in class_blocks for line in block)
    stripped_lines = {line.strip() for block in class_blocks for line in block}
    if "@dataclass(frozen=True)" in flattened:
        imports.add("from dataclasses import dataclass")
    if "Enum):" in flattened:
        imports.add("from enum import Enum")
    if "@overloaded" in stripped_lines:
        imports.add(RUNTIME_IMPORT_LINE)

    typing_names: set[str] = set()
    if "Any" in flattened:
        typing_names.add("Any")
    if "(Protocol):" in flattened:
        typing_names.add("Protocol")
    if "@overload" in stripped_lines:
        typing_names.add("overload")
    if typing_names:
        imports.add(f"from typing import {', '.join(sorted(typing_names))}")
    if "_j2py_lock" in flattened or "threading.Lock" in flattened:
        imports.add("import threading")

    return sorted(imports)


def _java_import_name(node: JavaNode) -> str:
    for child in node.walk():
        if child.type in {"scoped_identifier", "identifier"}:
            return child.text
    return ""

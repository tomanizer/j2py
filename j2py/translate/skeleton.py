"""Rule-based skeleton generator for the deterministic translation layer."""

from __future__ import annotations

from dataclasses import dataclass

from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import ParsedFile
from j2py.translate.classes import top_level_classes, translate_class
from j2py.translate.diagnostics import TranslationDiagnostics


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
    if any(line.strip() == "@overload" for block in class_blocks for line in block):
        lines.extend(["", "from typing import overload"])
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

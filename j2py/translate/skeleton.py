"""Rule-based skeleton generator — placeholder for the full implementation.

This module will grow to cover:
  - Class/interface/enum declarations
  - Method signatures with type annotations
  - Field declarations
  - Import translation
  - Literal/keyword substitution
  - Control flow structure (braces → indentation)

Currently returns the raw Java source with a TODO marker so the LLM layer
always fires during early development.
"""

from __future__ import annotations

from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import ParsedFile


def translate_skeleton(
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
) -> tuple[str, float]:
    """Produce a partial Python translation and a coverage estimate.

    Returns:
        (skeleton_source, coverage) where coverage is 0.0–1.0.
        Coverage < 1.0 triggers the LLM layer.
    """
    # TODO: implement rule-based translation layers
    # For now, return empty skeleton with 0 coverage so LLM always fires
    return "", 0.0

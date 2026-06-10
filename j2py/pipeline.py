"""Top-level translation pipeline: Java file → Python source."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import parse_file


@dataclass
class TranslationResult:
    source_path: Path
    python_source: str
    used_llm: bool = False
    confidence: float = 1.0   # 0.0–1.0; <0.8 means LLM was needed for significant portions


def translate_file(
    path: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str = "claude-sonnet-4-6",
) -> TranslationResult:
    """Full pipeline: parse → analyse → rule-translate → (optionally) LLM-complete."""
    parsed = parse_file(path)
    symbols = extract_symbols(parsed)

    # Layer 1: rule-based skeleton translation
    from j2py.translate.skeleton import translate_skeleton
    skeleton, coverage = translate_skeleton(parsed, symbols, cfg)

    if use_llm and coverage < 1.0:
        from j2py.llm.client import translate_with_llm
        python_source = translate_with_llm(
            java_source=path.read_text(),
            partial_python=skeleton,
            model=model,
        )
        used_llm = True
    else:
        python_source = skeleton
        used_llm = False

    return TranslationResult(
        source_path=path,
        python_source=python_source,
        used_llm=used_llm,
        confidence=coverage,
    )

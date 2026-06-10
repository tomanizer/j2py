"""Top-level translation pipeline: Java file → Python source."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import FileSymbols, extract_symbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import parse_file
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.validate.checks import ValidationResult, validate_source


@dataclass
class TranslationResult:
    source_path: Path
    python_source: str
    used_llm: bool = False
    confidence: float = 1.0   # 0.0–1.0; <0.8 means LLM was needed for significant portions
    output_path: Path | None = None
    diagnostics: TranslationDiagnostics | None = None
    validation: ValidationResult | None = None


@dataclass
class DirectoryTranslationResult:
    source_root: Path
    output_root: Path
    files: list[TranslationResult]
    order: list[Path]
    warnings: list[str]


def translate_file(
    path: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str = "claude-sonnet-4-6",
    validate: bool = False,
) -> TranslationResult:
    """Full pipeline: parse → analyse → rule-translate → (optionally) LLM-complete."""
    parsed = parse_file(path)
    symbols = extract_symbols(parsed)

    # Layer 1: rule-based skeleton translation
    from j2py.translate.skeleton import translate_skeleton_with_diagnostics
    skeleton_result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)
    skeleton = skeleton_result.source
    coverage = skeleton_result.coverage

    if use_llm and coverage < 1.0:
        from j2py.llm.client import translate_with_llm
        python_source = translate_with_llm(
            java_source=path.read_text(),
            partial_python=skeleton,
            context=_project_context(symbols),
            diagnostics=_diagnostics_context(skeleton_result.diagnostics),
            config_fingerprint=_config_fingerprint(cfg),
            model=model,
        )
        used_llm = True
    else:
        python_source = skeleton
        used_llm = False

    validation = validate_source(python_source, path.with_suffix(".py")) if validate else None

    return TranslationResult(
        source_path=path,
        python_source=python_source,
        used_llm=used_llm,
        confidence=coverage,
        diagnostics=skeleton_result.diagnostics,
        validation=validation,
    )


def translate_directory(
    source_root: Path,
    output_root: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str = "claude-sonnet-4-6",
    validate: bool = False,
) -> DirectoryTranslationResult:
    """Translate a directory using dependency order and package-relative outputs."""
    java_files = sorted(source_root.rglob("*.java"))
    parsed_files = [parse_file(path) for path in java_files]
    all_symbols = [extract_symbols(parsed) for parsed in parsed_files]
    symbols_by_path = {symbols.path: symbols for symbols in all_symbols}
    graph = build_dependency_graph(all_symbols)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ordered = [Path(path) for path in translation_order(graph)]

    if not ordered:
        ordered = java_files

    results: list[TranslationResult] = []
    for path in ordered:
        symbols = symbols_by_path[path]
        result = translate_file(
            path,
            cfg=cfg,
            use_llm=use_llm,
            model=model,
            validate=validate,
        )
        result.output_path = output_root / _output_relative_path(
            path,
            symbols.package,
            source_root,
        )
        results.append(result)

    return DirectoryTranslationResult(
        source_root=source_root,
        output_root=output_root,
        files=results,
        order=ordered,
        warnings=[str(warning.message) for warning in caught],
    )


def _output_relative_path(path: Path, package: str, source_root: Path) -> Path:
    if package:
        return Path(*package.split(".")) / path.with_suffix(".py").name
    return path.relative_to(source_root).with_suffix(".py")


def _project_context(symbols: FileSymbols) -> str:
    imports = "\n".join(f"- {item}" for item in symbols.imports) or "- <none>"
    classes = "\n".join(f"- {item.name}" for item in symbols.classes) or "- <none>"
    return f"package: {symbols.package or '<default>'}\nimports:\n{imports}\nclasses:\n{classes}"


def _diagnostics_context(diagnostics: TranslationDiagnostics) -> str:
    if not diagnostics.unhandled:
        return "No unresolved rule-layer diagnostics."
    return "\n".join(
        f"- line {item.line}: {item.node_type}: {item.reason}: {item.text}"
        for item in diagnostics.unhandled
    )


def _config_fingerprint(cfg: TranslationConfig) -> str:
    payload = json.dumps(cfg.model_dump(mode="json"), sort_keys=True)
    return payload

"""Top-level translation pipeline: Java file → Python source."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import FileSymbols, extract_symbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import ParsedFile, parse_file
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.validate.checks import ValidationResult, validate_source
from j2py.verify.structure import StructuralVerificationResult, verify_structure

PARSE_ERROR_LLM_SKIP_MSG = "Java parse errors detected; skipping LLM completion"


@dataclass
class TranslationResult:
    source_path: Path
    python_source: str
    used_llm: bool = False
    confidence: float = 1.0   # rule-layer coverage (0.0–1.0); not updated after LLM completion
    parse_ok: bool = True
    output_path: Path | None = None
    diagnostics: TranslationDiagnostics | None = None
    validation: ValidationResult | None = None
    structural_verification: StructuralVerificationResult | None = None


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
    validate: bool = True,
) -> TranslationResult:
    """Full pipeline: parse → analyse → rule-translate → (optionally) LLM-complete."""
    parsed = parse_file(path)
    symbols = extract_symbols(parsed)
    return _translate_parsed_file(
        path,
        parsed=parsed,
        symbols=symbols,
        cfg=cfg,
        use_llm=use_llm,
        model=model,
        validate=validate,
        validation_path=path.with_suffix(".py"),
    )


def _translate_parsed_file(
    path: Path,
    *,
    parsed: ParsedFile,
    symbols: FileSymbols,
    cfg: TranslationConfig,
    use_llm: bool,
    model: str,
    validate: bool,
    validation_path: Path,
) -> TranslationResult:
    """Translate a file using already-parsed AST and symbols."""
    parse_ok = not parsed.has_errors

    # Layer 1: rule-based skeleton translation
    from j2py.translate.skeleton import translate_skeleton_with_diagnostics
    skeleton_result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)
    skeleton = skeleton_result.source
    coverage = skeleton_result.coverage

    # Layer 2: LLM fires when rule layer is incomplete OR skeleton fails syntax/type checks.
    # Coverage < 1.0 means the rule layer left gaps; coverage == 1.0 means it translated
    # every construct but may still have produced semantically invalid output (e.g. undefined
    # names from Java constructs the rules don't fully understand).  We pre-validate and
    # thread any errors into the LLM call as validation_feedback so Claude can fix them.
    # Ruff lint failures alone do not trigger the LLM — only syntax and type errors do.
    validation_feedback = ""
    should_use_llm = False
    if use_llm and parse_ok:
        if coverage < 1.0:
            should_use_llm = True
        else:
            pre = validate_source(skeleton, path.with_suffix(".py"))
            if not (pre.syntax_ok and pre.mypy_ok):
                should_use_llm = True
                validation_feedback = "\n".join(pre.syntax_errors + pre.mypy_errors)

    if should_use_llm:
        from j2py.llm.client import translate_with_llm

        java_source = path.read_text()
        context = _project_context(symbols)
        diagnostics_context = _diagnostics_context(skeleton_result.diagnostics)
        config_fingerprint = _config_fingerprint(cfg)

        python_source = translate_with_llm(
            java_source=java_source,
            partial_python=skeleton,
            context=context,
            diagnostics=diagnostics_context,
            validation_feedback=validation_feedback,
            config_fingerprint=config_fingerprint,
            model=model,
        )
        used_llm = True
        validation = validate_source(python_source, validation_path) if validate else None
        structural_verification = verify_structure(symbols, python_source)
        feedback = _post_llm_feedback(validation, structural_verification)
        if feedback:
            python_source = translate_with_llm(
                java_source=java_source,
                partial_python=skeleton,
                context=context,
                diagnostics=diagnostics_context,
                validation_feedback=feedback,
                config_fingerprint=config_fingerprint,
                model=model,
            )
            validation = validate_source(python_source, validation_path) if validate else None
            structural_verification = verify_structure(symbols, python_source)
    else:
        python_source = skeleton
        used_llm = False
        validation = validate_source(python_source, validation_path) if validate else None
        structural_verification = None

    confidence = 0.0 if not parse_ok else coverage

    return TranslationResult(
        source_path=path,
        python_source=python_source,
        used_llm=used_llm,
        confidence=confidence,
        parse_ok=parse_ok,
        diagnostics=skeleton_result.diagnostics,
        validation=validation,
        structural_verification=structural_verification,
    )


def _post_llm_feedback(
    validation: ValidationResult | None,
    structural_verification: StructuralVerificationResult,
    *,
    limit: int = 5,
) -> str:
    errors: list[str] = []
    if validation is not None:
        errors.extend(validation.syntax_errors)
        errors.extend(validation.ruff_errors)
        errors.extend(validation.mypy_errors)
    errors.extend(structural_verification.errors)
    return "\n".join(errors[:limit])


def translate_directory(
    source_root: Path,
    output_root: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str = "claude-sonnet-4-6",
    validate: bool = True,
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
        parsed = parsed_files[java_files.index(path)]
        output_path = output_root / _output_relative_path(
            path,
            symbols.package,
            source_root,
        )
        result = _translate_parsed_file(
            path,
            parsed=parsed,
            symbols=symbols,
            cfg=cfg,
            use_llm=use_llm,
            model=model,
            validate=validate,
            validation_path=output_path,
        )
        result.output_path = output_path
        results.append(result)

    graph_warnings = [str(warning.message) for warning in caught]
    parse_warnings = [
        f"{result.source_path}: {PARSE_ERROR_LLM_SKIP_MSG}"
        for result in results
        if not result.parse_ok
    ]

    return DirectoryTranslationResult(
        source_root=source_root,
        output_root=output_root,
        files=results,
        order=ordered,
        warnings=graph_warnings + parse_warnings,
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

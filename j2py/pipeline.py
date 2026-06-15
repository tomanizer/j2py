"""Top-level translation pipeline: Java file → Python source."""

from __future__ import annotations

import ast
import json
import os
import threading
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import networkx as nx

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import FileSymbols, extract_symbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import ParsedFile, parse_file
from j2py.state import StateEntry
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.validate.checks import ValidationResult, validate_directory, validate_source
from j2py.verify.structure import StructuralVerificationResult, verify_structure

PARSE_ERROR_LLM_SKIP_MSG = "Java parse errors detected; skipping LLM completion"
LLM_REPAIR_RETRY_LIMIT = 2
LlmPrevalidationMode = Literal["full", "syntax"]
LLMProvider = Literal["anthropic", "gemini"]
SEMANTIC_WARNING_CONFIDENCE_CAP = 0.99
REVIEW_REQUIRED_CONFIDENCE_CAP = 0.79


@dataclass
class TranslationResult:
    source_path: Path
    python_source: str
    used_llm: bool = False
    confidence: float = 1.0  # user-facing review confidence; raw coverage is diagnostics.coverage
    parse_ok: bool = True
    output_path: Path | None = None
    diagnostics: TranslationDiagnostics | None = None
    validation: ValidationResult | None = None
    structural_verification: StructuralVerificationResult | None = None
    skipped: bool = False


@dataclass
class DirectoryTranslationResult:
    source_root: Path
    output_root: Path
    files: list[TranslationResult]
    order: list[Path]
    warnings: list[str]
    skipped_count: int = 0
    translated_count: int = 0


def translate_file(
    path: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str | None = None,
    llm_provider: LLMProvider | None = None,
    validate: bool = True,
) -> TranslationResult:
    """Full pipeline: parse → analyse → rule-translate → (optionally) LLM-complete."""
    parsed = parse_file(path)
    symbols = extract_symbols(parsed)
    effective_model, effective_provider = _resolve_llm_runtime(cfg, model, llm_provider)
    return _translate_parsed_file(
        path,
        parsed=parsed,
        symbols=symbols,
        cfg=cfg,
        use_llm=use_llm,
        model=effective_model,
        llm_provider=effective_provider,
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
    model: str | None,
    llm_provider: LLMProvider,
    validate: bool,
    validation_path: Path,
    sibling_signatures: dict[str, str] | None = None,
    llm_semaphore: threading.Semaphore | None = None,
    llm_prevalidation: LlmPrevalidationMode = "full",
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
    # thread any errors into the LLM call as validation_feedback so the provider can fix them.
    # Ruff lint failures alone do not trigger the LLM — only syntax and type errors do.
    validation_feedback = ""
    should_use_llm = False
    skeleton_pre_validation: ValidationResult | None = None
    if use_llm and parse_ok:
        if coverage < 1.0:
            should_use_llm = True
            skeleton_pre_validation = (
                validate_source(skeleton, path.with_suffix(".py"))
                if llm_prevalidation == "full"
                else None
            )
        else:
            if llm_prevalidation == "full":
                pre = validate_source(skeleton, path.with_suffix(".py"))
                skeleton_pre_validation = pre
                if not (pre.syntax_ok and pre.mypy_ok):
                    should_use_llm = True
                    validation_feedback = "\n".join(pre.syntax_errors + pre.mypy_errors)
            else:
                syntax_errors = _syntax_errors(skeleton, filename=validation_path.name)
                if syntax_errors:
                    should_use_llm = True
                    validation_feedback = "\n".join(syntax_errors)

    if should_use_llm:
        from j2py.llm.client import resolve_model, translate_with_llm

        java_source = path.read_text()
        context = _project_context(symbols, sibling_signatures=sibling_signatures)
        diagnostics_context = _diagnostics_context(skeleton_result.diagnostics)
        config_fingerprint = _config_fingerprint(cfg)

        python_source = _call_llm(
            translate_with_llm,
            llm_semaphore=llm_semaphore,
            java_source=java_source,
            partial_python=skeleton,
            context=context,
            diagnostics=diagnostics_context,
            validation_feedback=validation_feedback,
            previous_python="",
            config_fingerprint=config_fingerprint,
            model=model,
            provider=llm_provider,
        )
        used_llm = True
        validation = validate_source(python_source, validation_path) if validate else None
        structural_verification = verify_structure(symbols, python_source)
        for _ in range(LLM_REPAIR_RETRY_LIMIT):
            feedback = _post_llm_feedback(validation, structural_verification)
            if not feedback:
                break
            previous_python = python_source
            python_source = _call_llm(
                translate_with_llm,
                llm_semaphore=llm_semaphore,
                java_source=java_source,
                partial_python=skeleton,
                context=context,
                diagnostics=diagnostics_context,
                validation_feedback=feedback,
                previous_python=previous_python,
                config_fingerprint=config_fingerprint,
                model=model,
                provider=llm_provider,
            )
            validation = validate_source(python_source, validation_path) if validate else None
            structural_verification = verify_structure(symbols, python_source)
        from j2py.llm.harvest import record_llm_repair

        record_llm_repair(
            source_path=path,
            java_source=java_source,
            skeleton=skeleton,
            final_python=python_source,
            model=resolve_model(llm_provider, model),
            coverage=coverage,
            diagnostics=skeleton_result.diagnostics,
            pre_validation=skeleton_pre_validation,
            structural_verification=None,
            repo_root=_repo_root_for_harvest(path),
        )
    else:
        python_source = skeleton
        used_llm = False
        validation = validate_source(python_source, validation_path) if validate else None
        structural_verification = None

    confidence = _surface_confidence(
        rule_coverage=coverage,
        parse_ok=parse_ok,
        diagnostics=skeleton_result.diagnostics,
        validation=validation,
        structural_verification=structural_verification,
    )

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


def _call_llm(
    translate_with_llm: Callable[..., str],
    *,
    llm_semaphore: threading.Semaphore | None,
    **kwargs: object,
) -> str:
    if llm_semaphore is None:
        return translate_with_llm(**kwargs)
    with llm_semaphore:
        return translate_with_llm(**kwargs)


def _surface_confidence(
    *,
    rule_coverage: float,
    parse_ok: bool,
    diagnostics: TranslationDiagnostics,
    validation: ValidationResult | None,
    structural_verification: StructuralVerificationResult | None,
) -> float:
    """Return the user-facing trust score, keeping raw node coverage on diagnostics."""
    if not parse_ok:
        return 0.0
    confidence = rule_coverage
    if diagnostics.semantic_warning_count:
        # Semantic warnings preserve raw coverage ordering, but they must never present
        # as perfect trust.
        confidence = min(confidence, SEMANTIC_WARNING_CONFIDENCE_CAP)
    if validation is not None and not validation.ok:
        confidence = min(confidence, REVIEW_REQUIRED_CONFIDENCE_CAP)
    if structural_verification is not None and not structural_verification.ok:
        confidence = min(confidence, REVIEW_REQUIRED_CONFIDENCE_CAP)
    return confidence


def _refresh_result_confidence(result: TranslationResult) -> None:
    """Recompute surfaced confidence after late validation or verification updates."""
    if result.diagnostics is None:
        return
    result.confidence = _surface_confidence(
        rule_coverage=result.diagnostics.coverage,
        parse_ok=result.parse_ok,
        diagnostics=result.diagnostics,
        validation=result.validation,
        structural_verification=result.structural_verification,
    )


def _syntax_errors(source: str, filename: str = "<string>") -> list[str]:
    try:
        ast.parse(source, filename=filename)
    except SyntaxError as error:
        return [f"SyntaxError: {error}"]
    return []


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
    selected = errors[:limit]
    if validation is not None:
        selected = _sanitize_feedback_paths(selected, validation.path)
    hints = _llm_repair_hints(selected)
    if hints:
        selected.append("Repair guidance:")
        selected.extend(hints)
    return "\n".join(selected)


def _sanitize_feedback_paths(errors: list[str], path: Path) -> list[str]:
    """Replace environment-specific validation paths before they reach LLM caching."""
    path_str = str(path)
    if not path_str or path_str == path.name:
        return errors
    return [error.replace(path_str, path.name) for error in errors]


def _llm_repair_hints(errors: list[str]) -> list[str]:
    """Return targeted prompt hints for common validation failures."""
    joined = "\n".join(errors)
    hints: list[str] = []
    if "unused-ignore" in joined:
        hints.append(
            "- Remove unused # type: ignore comments; prefer typed placeholders or "
            "direct annotations that pass mypy.",
        )
    if "overload-cannot-match" in joined or "will never be matched" in joined:
        hints.append(
            "- Fix unreachable overloads: do not put an object/Any overload before a "
            "narrower overload. For unresolved Java types, create nominal local "
            "placeholder classes so overload signatures stay distinct, or collapse "
            "to a single implementation signature.",
        )
    if "Missing type arguments for generic type" in joined:
        hints.append(
            "- Add explicit type arguments to bare generic containers, for example "
            "tuple[object, ...], list[object], or dict[str, object].",
        )
    if any(prefix in joined for prefix in ("javax.", "jakarta.", "org.", "com.", "net.")):
        hints.append(
            "- Do not import unresolved Java packages. Replace Java platform/framework "
            "types with local TODO(j2py) placeholder classes or Protocols.",
        )
    return hints


def translate_directory(
    source_root: Path,
    output_root: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str | None = None,
    llm_provider: LLMProvider | None = None,
    validate: bool = True,
    workers: int | None = None,
    llm_concurrency: int | None = None,
    incremental: bool = False,
) -> DirectoryTranslationResult:
    """Translate a directory using dependency order and package-relative outputs."""
    effective_model, effective_provider = _resolve_llm_runtime(cfg, model, llm_provider)
    java_files = sorted(source_root.rglob("*.java"))
    parsed_files = [parse_file(path) for path in java_files]
    parsed_by_path = dict(zip(java_files, parsed_files, strict=True))
    all_symbols = [extract_symbols(parsed) for parsed in parsed_files]
    symbols_by_path = {symbols.path: symbols for symbols in all_symbols}
    graph = build_dependency_graph(all_symbols)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ordered = [Path(path) for path in translation_order(graph)]

    if not ordered:
        ordered = java_files

    effective_workers = workers if workers is not None else min(8, os.cpu_count() or 1)
    effective_workers = max(1, effective_workers)
    effective_llm_concurrency = (
        llm_concurrency if llm_concurrency is not None else min(4, effective_workers)
    )
    llm_semaphore = threading.Semaphore(max(1, effective_llm_concurrency))
    previous_state: dict[str, StateEntry] = {}
    if incremental:
        from j2py.state import load_state

        previous_state = load_state(output_root)
    skip_paths = (
        _incremental_skip_paths(
            java_files,
            source_root=source_root,
            output_root=output_root,
            symbols_by_path=symbols_by_path,
            graph=graph,
            previous=previous_state,
        )
        if incremental
        else set()
    )

    results: list[TranslationResult] = []
    sibling_signatures: dict[str, dict[str, str]] = {}
    completed: set[Path] = set()
    remaining = list(ordered)
    while remaining:
        ready = [path for path in remaining if _dependencies_for(path, graph).issubset(completed)]
        if not ready:
            ready = [remaining[0]]

        translated = _translate_ready_paths(
            ready,
            skip_paths=skip_paths,
            source_root=source_root,
            output_root=output_root,
            symbols_by_path=symbols_by_path,
            parsed_by_path=parsed_by_path,
            cfg=cfg,
            use_llm=use_llm,
            model=effective_model,
            llm_provider=effective_provider,
            sibling_signatures=sibling_signatures,
            workers=effective_workers,
            llm_semaphore=llm_semaphore,
            previous_state=previous_state,
        )
        for result in translated:
            results.append(result)
            symbols = symbols_by_path[result.source_path]
            sibling_signatures.setdefault(symbols.package, {}).update(
                _extract_python_signatures(result.python_source)
            )
            completed.add(result.source_path)
        remaining = [path for path in remaining if path not in set(ready)]

    if validate:
        validation_results = validate_directory(
            {
                result.output_path: result.python_source
                for result in results
                if result.output_path is not None and not result.skipped
            }
        )
        for result in results:
            if result.output_path is not None and result.output_path in validation_results:
                result.validation = validation_results[result.output_path]
                _refresh_result_confidence(result)

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
        skipped_count=sum(1 for result in results if result.skipped),
        translated_count=sum(1 for result in results if not result.skipped),
    )


def _resolve_llm_runtime(
    cfg: TranslationConfig,
    model: str | None,
    llm_provider: LLMProvider | None,
) -> tuple[str | None, LLMProvider]:
    provider = llm_provider or cfg.llm_provider or "anthropic"
    effective_model = model if model is not None else cfg.model
    return effective_model, provider


def _translate_ready_paths(
    paths: list[Path],
    *,
    skip_paths: set[Path],
    source_root: Path,
    output_root: Path,
    symbols_by_path: dict[Path, FileSymbols],
    parsed_by_path: dict[Path, ParsedFile],
    cfg: TranslationConfig,
    use_llm: bool,
    model: str | None,
    llm_provider: LLMProvider,
    sibling_signatures: dict[str, dict[str, str]],
    workers: int,
    llm_semaphore: threading.Semaphore,
    previous_state: dict[str, StateEntry],
) -> list[TranslationResult]:
    from j2py.state import source_key

    ordered_results: dict[Path, TranslationResult] = {}
    to_translate: list[Path] = []
    for path in paths:
        symbols = symbols_by_path[path]
        output_path = output_root / _output_relative_path(path, symbols.package, source_root)
        if path in skip_paths:
            entry = previous_state.get(source_key(path, source_root))
            ordered_results[path] = TranslationResult(
                source_path=path,
                python_source=output_path.read_text(),
                used_llm=entry.used_llm if entry is not None else False,
                confidence=entry.confidence if entry is not None else 1.0,
                output_path=output_path,
                skipped=True,
            )
        else:
            to_translate.append(path)

    def translate_one(path: Path) -> TranslationResult:
        symbols = symbols_by_path[path]
        output_path = output_root / _output_relative_path(path, symbols.package, source_root)
        direct_sibling_signatures = _direct_import_signatures(symbols, sibling_signatures)
        result = _translate_parsed_file(
            path,
            parsed=parsed_by_path[path],
            symbols=symbols,
            cfg=cfg,
            use_llm=use_llm,
            model=model,
            llm_provider=llm_provider,
            validate=False,
            validation_path=output_path,
            sibling_signatures=direct_sibling_signatures,
            llm_semaphore=llm_semaphore,
            llm_prevalidation="syntax",
        )
        result.output_path = output_path
        return result

    if workers == 1 or len(to_translate) < 2:
        for path in to_translate:
            ordered_results[path] = translate_one(path)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(translate_one, path): path for path in to_translate}
            for future, path in futures.items():
                ordered_results[path] = future.result()

    return [ordered_results[path] for path in paths]


def _dependencies_for(path: Path, graph: nx.DiGraph) -> set[Path]:
    if str(path) not in graph:
        return set()
    return {Path(item) for item in graph.successors(str(path))}


def _incremental_skip_paths(
    java_files: list[Path],
    *,
    source_root: Path,
    output_root: Path,
    symbols_by_path: dict[Path, FileSymbols],
    graph: nx.DiGraph,
    previous: dict[str, StateEntry],
) -> set[Path]:
    from j2py.state import sha256_file, source_key

    unchanged: set[Path] = set()
    for path in java_files:
        symbols = symbols_by_path[path]
        output_path = output_root / _output_relative_path(path, symbols.package, source_root)
        entry = previous.get(source_key(path, source_root))
        if entry is None or not output_path.exists():
            continue
        if entry.sha256 == sha256_file(path):
            unchanged.add(path)
    changed = set(java_files) - unchanged
    invalidated = set(changed)
    for path in changed:
        if str(path) in graph:
            invalidated.update(Path(item) for item in nx.ancestors(graph, str(path)))
    return set(java_files) - invalidated


def _output_relative_path(path: Path, package: str, source_root: Path) -> Path:
    if package:
        return Path(*package.split(".")) / path.with_suffix(".py").name
    return path.relative_to(source_root).with_suffix(".py")


def _project_context(
    symbols: FileSymbols,
    *,
    sibling_signatures: dict[str, str] | None = None,
) -> str:
    imports = "\n".join(f"- {item}" for item in symbols.imports) or "- <none>"
    classes = "\n".join(f"- {item.name}" for item in symbols.classes) or "- <none>"
    parts = [
        f"package: {symbols.package or '<default>'}",
        f"imports:\n{imports}",
        f"classes:\n{classes}",
    ]
    if sibling_signatures:
        sibling_context = "\n".join(
            f"- {name}: {signature}" for name, signature in sorted(sibling_signatures.items())
        )
        parts.append(f"Already-translated sibling classes:\n{sibling_context}")
    return "\n".join(parts)


def _direct_import_signatures(
    symbols: FileSymbols,
    sibling_signatures: dict[str, dict[str, str]],
) -> dict[str, str]:
    result = dict(sibling_signatures.get(symbols.package, {}))
    for item in symbols.imports:
        if item in sibling_signatures:
            result.update(sibling_signatures[item])
            continue
        package, _, class_name = item.rpartition(".")
        if package and class_name in sibling_signatures.get(package, {}):
            result[class_name] = sibling_signatures[package][class_name]
    return result


def _extract_python_signatures(python_source: str) -> dict[str, str]:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return {}
    return {
        node.name: _class_signature(node) for node in tree.body if isinstance(node, ast.ClassDef)
    }


def _class_signature(node: ast.ClassDef) -> str:
    fields = [
        item.target.id
        for item in node.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    ]
    methods = [
        _function_signature(item)
        for item in node.body
        if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef))
    ]
    parts = [f"class {node.name}"]
    if fields:
        parts.append(f"fields={fields}")
    if methods:
        parts.append(f"methods={methods}")
    return "; ".join(parts)


def _function_signature(node: ast.AsyncFunctionDef | ast.FunctionDef) -> str:
    arg_list: list[str] = []
    arg_list.extend(_argument_signature(arg) for arg in node.args.posonlyargs)
    arg_list.extend(_argument_signature(arg) for arg in node.args.args)
    if node.args.vararg:
        arg_list.append(f"*{_argument_signature(node.args.vararg)}")
    elif node.args.kwonlyargs:
        arg_list.append("*")
    arg_list.extend(_argument_signature(arg) for arg in node.args.kwonlyargs)
    if node.args.kwarg:
        arg_list.append(f"**{_argument_signature(node.args.kwarg)}")
    args = ", ".join(arg_list)
    signature = f"{node.name}({args})"
    if node.returns is not None:
        signature += f" -> {ast.unparse(node.returns)}"
    return signature


def _argument_signature(arg: ast.arg) -> str:
    if arg.annotation is None:
        return arg.arg
    return f"{arg.arg}: {ast.unparse(arg.annotation)}"


def _repo_root_for_harvest(source_path: Path) -> Path:
    for candidate in (source_path, *source_path.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


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

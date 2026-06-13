"""Top-level translation pipeline: Java file → Python source."""

from __future__ import annotations

import ast
import json
import warnings
from dataclasses import dataclass
from pathlib import Path

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import FileSymbols, extract_symbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import ParsedFile, parse_file
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.validate.checks import ValidationResult, validate_directory, validate_source
from j2py.verify.structure import StructuralVerificationResult, verify_structure

PARSE_ERROR_LLM_SKIP_MSG = "Java parse errors detected; skipping LLM completion"
LLM_REPAIR_RETRY_LIMIT = 2


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
    sibling_signatures: dict[str, str] | None = None,
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
        context = _project_context(symbols, sibling_signatures=sibling_signatures)
        diagnostics_context = _diagnostics_context(skeleton_result.diagnostics)
        config_fingerprint = _config_fingerprint(cfg)

        python_source = translate_with_llm(
            java_source=java_source,
            partial_python=skeleton,
            context=context,
            diagnostics=diagnostics_context,
            validation_feedback=validation_feedback,
            previous_python="",
            config_fingerprint=config_fingerprint,
            model=model,
        )
        used_llm = True
        validation = validate_source(python_source, validation_path) if validate else None
        structural_verification = verify_structure(symbols, python_source)
        for _ in range(LLM_REPAIR_RETRY_LIMIT):
            feedback = _post_llm_feedback(validation, structural_verification)
            if not feedback:
                break
            previous_python = python_source
            python_source = translate_with_llm(
                java_source=java_source,
                partial_python=skeleton,
                context=context,
                diagnostics=diagnostics_context,
                validation_feedback=feedback,
                previous_python=previous_python,
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
    sibling_signatures: dict[str, dict[str, str]] = {}
    for path in ordered:
        symbols = symbols_by_path[path]
        parsed = parsed_files[java_files.index(path)]
        output_path = output_root / _output_relative_path(
            path,
            symbols.package,
            source_root,
        )
        direct_sibling_signatures = _direct_import_signatures(symbols, sibling_signatures)
        result = _translate_parsed_file(
            path,
            parsed=parsed,
            symbols=symbols,
            cfg=cfg,
            use_llm=use_llm,
            model=model,
            validate=False,
            validation_path=output_path,
            sibling_signatures=direct_sibling_signatures,
        )
        result.output_path = output_path
        results.append(result)
        sibling_signatures.setdefault(symbols.package, {}).update(
            _extract_python_signatures(result.python_source)
        )

    if validate:
        validation_results = validate_directory(
            {
                result.output_path: result.python_source
                for result in results
                if result.output_path is not None
            }
        )
        for result in results:
            if result.output_path is not None:
                result.validation = validation_results[result.output_path]

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
            f"- {name}: {signature}"
            for name, signature in sorted(sibling_signatures.items())
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
        node.name: _class_signature(node)
        for node in tree.body
        if isinstance(node, ast.ClassDef)
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

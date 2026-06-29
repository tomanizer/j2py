"""Project assessment report construction."""

from __future__ import annotations

import warnings
from collections import Counter
from pathlib import Path
from typing import Any

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import ClassSymbol, FileSymbols, class_kind, extract_symbols
from j2py.config.loader import TranslationConfig
from j2py.doctor_models import DOCTOR_SCHEMA_VERSION, DoctorAssessment
from j2py.parse.java_ast import JavaNode, parse_file
from j2py.pipeline import translate_file
from j2py.translate.annotation_emit import _FRAMEWORK_ANNOTATIONS
from j2py.translate.diagnostics import diagnostic_payload, todo_lines


def assess_project(
    source: Path,
    *,
    cfg: TranslationConfig,
    include_validation: bool = False,
    sample_limit: int | None = None,
) -> DoctorAssessment:
    """Assess Java sources without using the LLM layer."""
    java_files = _java_files(source)
    if sample_limit is not None:
        java_files = java_files[:sample_limit]

    parsed_by_path = {path: parse_file(path) for path in java_files}
    symbols_by_path = {path: extract_symbols(parsed) for path, parsed in parsed_by_path.items()}
    import_owner = _import_owner_index(symbols_by_path.values())
    graph = build_dependency_graph(list(symbols_by_path.values()))
    graph_warnings, order = _translation_order(graph)
    files = [
        _assess_file(
            path,
            source_root=source if source.is_dir() else source.parent,
            cfg=cfg,
            symbols=symbols_by_path[path],
            parsed=parsed_by_path[path],
            import_owner=import_owner,
            include_validation=include_validation,
        )
        for path in java_files
    ]

    payload = {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "source": str(source),
        "summary": _summary(files, graph_warnings),
        "dependency_graph": {
            "warnings": graph_warnings,
            "translation_order": [
                _relative_path(Path(path), source if source.is_dir() else source.parent)
                for path in order
            ],
        },
        "annotation_inventory": _annotation_inventory(files),
        "unresolved_imports": _unresolved_imports(files),
        "config_suggestions": _config_suggestions(files, cfg),
        "hotspots": _hotspots(files),
        "recommended_next_commands": _recommended_next_commands(source),
        "files": files,
    }
    return DoctorAssessment(payload=payload)


def _assess_file(
    path: Path,
    *,
    source_root: Path,
    cfg: TranslationConfig,
    symbols: FileSymbols,
    parsed: Any,
    import_owner: dict[str, str],
    include_validation: bool,
) -> dict[str, Any]:
    result = translate_file(path, cfg=cfg, use_llm=False, validate=include_validation)
    diagnostics = result.diagnostics
    annotations = _annotations(parsed.root, symbols.imports)
    unresolved = _unresolved_import_candidates(symbols, cfg, import_owner)
    return {
        "path": _relative_path(path, source_root),
        "package": symbols.package,
        "parse_ok": not parsed.has_errors,
        "parse_errors": [_node_payload(item, reason="Java parse error") for item in parsed.errors],
        "classes": [_class_payload(item) for item in symbols.classes],
        "imports": symbols.imports,
        "annotations": annotations,
        "unresolved_imports": unresolved,
        "translation": {
            "rule_coverage": diagnostics.coverage if diagnostics is not None else 0.0,
            "confidence": result.confidence,
            "semantic_warnings": []
            if diagnostics is None
            else [diagnostic_payload(item) for item in diagnostics.warnings],
            "unhandled": []
            if diagnostics is None
            else [diagnostic_payload(item) for item in diagnostics.unhandled],
            "todos": todo_lines(result.python_source),
            "validation": _validation_payload(result.validation),
        },
    }


def _java_files(source: Path) -> list[Path]:
    if source.is_dir():
        return sorted(source.rglob("*.java"))
    return [source]


def _translation_order(graph: Any) -> tuple[list[str], list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        order = translation_order(graph)
    return [str(item.message) for item in caught], [str(item) for item in order]


def _summary(files: list[dict[str, Any]], graph_warnings: list[str]) -> dict[str, Any]:
    coverages = [item["translation"]["rule_coverage"] for item in files]
    return {
        "files": len(files),
        "classes": sum(len(item["classes"]) for item in files),
        "parse_failures": sum(1 for item in files if not item["parse_ok"]),
        "graph_warnings": len(graph_warnings),
        "average_rule_coverage": sum(coverages) / len(coverages) if coverages else 0.0,
        "semantic_warnings": sum(len(item["translation"]["semantic_warnings"]) for item in files),
        "unhandled_diagnostics": sum(len(item["translation"]["unhandled"]) for item in files),
        "todo_lines": sum(len(item["translation"]["todos"]) for item in files),
        "unresolved_imports": sum(len(item["unresolved_imports"]) for item in files),
    }


def _annotation_inventory(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for item in files:
        counter.update(annotation["simple_name"] for annotation in item["annotations"])
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _unresolved_imports(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    for item in files:
        for candidate in item["unresolved_imports"]:
            candidates.setdefault(candidate["import"], candidate)
    return [candidates[key] for key in sorted(candidates)]


def _config_suggestions(
    files: list[dict[str, Any]],
    cfg: TranslationConfig,
) -> dict[str, list[dict[str, str]]]:
    imports = _unresolved_imports(files)
    annotations = _annotation_inventory(files)
    configured_annotations = _configured_annotation_names(cfg)
    annotation_suggestions = [
        {
            "annotation": item["name"],
            "confidence": "low",
            "reason": "annotation observed during assessment; map only after target-stack review",
        }
        for item in annotations
        if item["name"] not in configured_annotations
        and (item["name"] in _FRAMEWORK_ANNOTATIONS or item["name"].endswith("Mapping"))
    ]
    return {
        "import_map": [
            {
                "java_import": item["import"],
                "confidence": "low",
                "reason": f"{item['category']} needs project-owned mapping or stub",
            }
            for item in imports
        ],
        "type_map": [
            {
                "java_type": item["import"].rsplit(".", 1)[-1],
                "confidence": "low",
                "reason": "unresolved imported type; map only if it has a target Python equivalent",
            }
            for item in imports
            if not item["import"].endswith(".*")
        ],
        "annotation_map": annotation_suggestions,
    }


def _configured_annotation_names(cfg: TranslationConfig) -> set[str]:
    names = set(cfg.annotation_map) | set(cfg.drop_annotations)
    names.update(name.rsplit(".", 1)[-1] for name in tuple(names))
    return names


def _hotspots(files: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    unhandled_types: Counter[str] = Counter()
    warning_reasons: Counter[str] = Counter()
    import_packages: Counter[str] = Counter()
    annotations: Counter[str] = Counter()
    for item in files:
        translation = item["translation"]
        unhandled_types.update(diagnostic["node_type"] for diagnostic in translation["unhandled"])
        warning_reasons.update(
            diagnostic["reason"] for diagnostic in translation["semantic_warnings"]
        )
        import_packages.update(
            _import_package(candidate["import"]) for candidate in item["unresolved_imports"]
        )
        annotations.update(annotation["simple_name"] for annotation in item["annotations"])

    return {
        "unhandled_node_types": _counter_payload(unhandled_types, "node_type"),
        "semantic_warning_reasons": _counter_payload(warning_reasons, "reason"),
        "unresolved_import_packages": _counter_payload(import_packages, "package"),
        "annotations": _counter_payload(annotations, "name"),
        "files_with_most_semantic_warnings": _rank_files(
            files,
            key=lambda item: len(item["translation"]["semantic_warnings"]),
        ),
        "lowest_coverage_files": _lowest_coverage_files(files),
    }


def _counter_payload(counter: Counter[str], label: str, *, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {label: name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _rank_files(
    files: list[dict[str, Any]],
    *,
    key: Any,
    limit: int = 10,
) -> list[dict[str, Any]]:
    ranked = sorted(files, key=lambda item: (-key(item), item["path"]))
    return [
        {
            "path": item["path"],
            "count": key(item),
            "rule_coverage": item["translation"]["rule_coverage"],
        }
        for item in ranked[:limit]
        if key(item) > 0
    ]


def _lowest_coverage_files(files: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    ranked = sorted(
        files,
        key=lambda item: (
            item["translation"]["rule_coverage"],
            item["path"],
        ),
    )
    return [
        {
            "path": item["path"],
            "rule_coverage": item["translation"]["rule_coverage"],
            "semantic_warnings": len(item["translation"]["semantic_warnings"]),
            "unhandled": len(item["translation"]["unhandled"]),
            "unresolved_imports": len(item["unresolved_imports"]),
        }
        for item in ranked[:limit]
    ]


def _import_package(java_import: str) -> str:
    clean = java_import.removesuffix(".*")
    if "." not in clean:
        return clean
    return clean.rsplit(".", 1)[0]


def _recommended_next_commands(source: Path) -> list[str]:
    src = str(source)
    return [
        f"j2py translate {src} --no-llm --no-validate --dashboard j2py-dashboard.html",
        f"j2py doctor {src} --json j2py-assessment.json --html j2py-assessment.html",
        "make check",
    ]


def _class_payload(cls: ClassSymbol) -> dict[str, Any]:
    return {
        "name": cls.name,
        "line": cls.line,
        "kind": class_kind(cls),
        "fields": [
            {
                "name": field.name,
                "java_type": field.java_type,
                "line": field.line,
                "static": field.is_static,
            }
            for field in cls.fields
        ],
        "methods": [
            {
                "name": method.name,
                "return_type": method.return_type,
                "line": method.line,
                "static": method.is_static,
            }
            for method in cls.methods
        ],
        "inner_classes": [_class_payload(inner) for inner in cls.inner_classes],
    }


def _annotations(root: JavaNode, imports: list[str]) -> list[dict[str, Any]]:
    imports_by_simple = {item.rsplit(".", 1)[-1]: item for item in imports}
    seen: list[dict[str, Any]] = []
    for node in root.find_all("annotation", "marker_annotation"):
        name = _annotation_name(node)
        if name is None:
            continue
        simple = name.rsplit(".", 1)[-1]
        full_name = name if "." in name else imports_by_simple.get(simple, simple)
        seen.append(
            {
                "name": name,
                "simple_name": simple,
                "full_name": full_name,
                "line": node.location.line,
                "text": _compact_text(node.text),
                "framework_candidate": simple in _FRAMEWORK_ANNOTATIONS
                or full_name.startswith(("org.springframework.", "jakarta.", "javax.")),
            }
        )
    return seen


def _annotation_name(annotation: JavaNode) -> str | None:
    name_node = annotation.child_by_field("name")
    if name_node is not None:
        return name_node.text
    for child in annotation.walk():
        if child.type in {"identifier", "scoped_identifier"}:
            return child.text
    return None


def _import_owner_index(symbols: Any) -> dict[str, str]:
    owners: dict[str, str] = {}
    for file_symbols in symbols:
        for cls in file_symbols.classes:
            qualified = f"{file_symbols.package}.{cls.name}" if file_symbols.package else cls.name
            owners[qualified] = str(file_symbols.path)
            owners[cls.name] = str(file_symbols.path)
    return owners


def _unresolved_import_candidates(
    symbols: FileSymbols,
    cfg: TranslationConfig,
    import_owner: dict[str, str],
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for item in symbols.imports:
        if item in cfg.drop_imports or item in cfg.import_map:
            continue
        if item in import_owner or item.rsplit(".", 1)[-1] in import_owner:
            continue
        candidates.append(
            {
                "import": item,
                "category": _import_category(item),
                "reason": "not covered by default drop_imports/import_map or project declarations",
            }
        )
    return sorted(candidates, key=lambda item: item["import"])


def _import_category(java_import: str) -> str:
    if java_import.startswith(
        (
            "org.springframework.",
            "jakarta.persistence.",
            "javax.persistence.",
            "jakarta.servlet.",
            "javax.servlet.",
        )
    ):
        return "framework-boundary"
    if java_import.startswith(("java.", "javax.", "jakarta.")):
        return "platform-boundary"
    return "external-import"


def _node_payload(node: JavaNode, *, reason: str) -> dict[str, Any]:
    return {
        "line": node.location.line,
        "node_type": node.type,
        "reason": reason,
        "text": _compact_text(node.text),
    }


def _validation_payload(validation: Any) -> dict[str, Any] | None:
    if validation is None:
        return None
    return {
        "ok": validation.ok,
        "syntax_ok": validation.syntax_ok,
        "ruff_ok": validation.ruff_ok,
        "mypy_ok": validation.mypy_ok,
        "errors": validation.syntax_errors + validation.ruff_errors + validation.mypy_errors,
    }


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _compact_text(text: str, *, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."

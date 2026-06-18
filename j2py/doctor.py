"""Project assessment report for migration planning."""

from __future__ import annotations

import json
import warnings
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from j2py.analyze.graph import build_dependency_graph, translation_order
from j2py.analyze.symbols import ClassSymbol, FileSymbols, extract_symbols
from j2py.config.loader import TranslationConfig
from j2py.parse.java_ast import JavaNode, parse_file
from j2py.pipeline import translate_file
from j2py.translate.annotation_emit import _FRAMEWORK_ANNOTATIONS
from j2py.translate.diagnostics import TranslationDiagnostic

DOCTOR_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DoctorAssessment:
    """JSON-serialisable project assessment."""

    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class DoctorDiff:
    """JSON-serialisable comparison between two doctor assessments."""

    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True) + "\n"


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


def write_assessment_json(path: Path, assessment: DoctorAssessment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(assessment.to_json(), encoding="utf-8")


def write_assessment_html(path: Path, assessment: DoctorAssessment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_assessment_html(assessment), encoding="utf-8")


def write_config_suggestions(path: Path, assessment: DoctorAssessment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config_suggestions(assessment), encoding="utf-8")


def load_assessment_json(path: Path) -> DoctorAssessment:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a doctor assessment object")
    return DoctorAssessment(payload=payload)


def diff_assessments(before: DoctorAssessment, after: DoctorAssessment) -> DoctorDiff:
    before_payload = before.payload
    after_payload = after.payload
    before_files = _files_by_path(before_payload)
    after_files = _files_by_path(after_payload)
    before_unresolved = _imports_by_name(before_payload.get("unresolved_imports", []))
    after_unresolved = _imports_by_name(after_payload.get("unresolved_imports", []))
    before_warnings = _diagnostic_keys(before_files, "semantic_warnings")
    after_warnings = _diagnostic_keys(after_files, "semantic_warnings")
    before_unhandled = _diagnostic_keys(before_files, "unhandled")
    after_unhandled = _diagnostic_keys(after_files, "unhandled")
    before_unresolved_keys = set(before_unresolved)
    after_unresolved_keys = set(after_unresolved)
    before_warning_keys = set(before_warnings)
    after_warning_keys = set(after_warnings)
    before_unhandled_keys = set(before_unhandled)
    after_unhandled_keys = set(after_unhandled)
    before_parse_failures = {path for path, item in before_files.items() if not item["parse_ok"]}
    after_parse_failures = {path for path, item in after_files.items() if not item["parse_ok"]}

    payload = {
        "schema_version": 1,
        "before_source": before_payload.get("source"),
        "after_source": after_payload.get("source"),
        "summary_delta": _summary_delta(
            before_payload.get("summary", {}),
            after_payload.get("summary", {}),
        ),
        "coverage_delta": (
            after_payload.get("summary", {}).get("average_rule_coverage", 0.0)
            - before_payload.get("summary", {}).get("average_rule_coverage", 0.0)
        ),
        "parse_failures": {
            "added": sorted(after_parse_failures - before_parse_failures),
            "removed": sorted(before_parse_failures - after_parse_failures),
        },
        "unresolved_imports": {
            "added": [
                after_unresolved[key]
                for key in sorted(after_unresolved_keys - before_unresolved_keys)
            ],
            "removed": [
                before_unresolved[key]
                for key in sorted(before_unresolved_keys - after_unresolved_keys)
            ],
        },
        "semantic_warnings": {
            "added": _diagnostic_entries(after_warnings, after_warning_keys - before_warning_keys),
            "removed": _diagnostic_entries(
                before_warnings,
                before_warning_keys - after_warning_keys,
            ),
        },
        "unhandled_diagnostics": {
            "added": _diagnostic_entries(
                after_unhandled,
                after_unhandled_keys - before_unhandled_keys,
            ),
            "removed": _diagnostic_entries(
                before_unhandled,
                before_unhandled_keys - after_unhandled_keys,
            ),
        },
        "file_changes": _file_changes(before_files, after_files),
    }
    return DoctorDiff(payload=payload)


def write_doctor_diff_json(path: Path, diff: DoctorDiff) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(diff.to_json(), encoding="utf-8")


def render_assessment_html(assessment: DoctorAssessment) -> str:
    payload = assessment.payload
    summary = payload["summary"]
    rows = "\n".join(_file_row(item) for item in payload["files"])
    hotspots = payload["hotspots"]
    annotations = "\n".join(
        f"<li><code>{escape(item['name'])}</code>: {item['count']}</li>"
        for item in payload["annotation_inventory"]
    )
    imports = "\n".join(
        f"<li><code>{escape(item['import'])}</code> <span>{escape(item['category'])}</span></li>"
        for item in payload["unresolved_imports"]
    )
    commands = "\n".join(
        f"<li><code>{escape(command)}</code></li>"
        for command in payload["recommended_next_commands"]
    )
    hotspot_columns = "\n".join(
        _hotspot_list(title, items, label_key)
        for title, items, label_key in (
            (
                "Unhandled Node Types",
                hotspots["unhandled_node_types"],
                "node_type",
            ),
            (
                "Warning Reasons",
                hotspots["semantic_warning_reasons"],
                "reason",
            ),
            (
                "Import Packages",
                hotspots["unresolved_import_packages"],
                "package",
            ),
            (
                "Lowest Coverage Files",
                hotspots["lowest_coverage_files"],
                "path",
            ),
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>j2py doctor assessment</title>
<style>
{_ASSESSMENT_CSS}
</style>
</head>
<body>
<header>
  <h1>j2py doctor assessment</h1>
  <span>{escape(str(payload["source"]))}</span>
</header>
<main>
  <section class="summary">
    {_metric("Files", summary["files"])}
    {_metric("Parse failures", summary["parse_failures"])}
    {_metric("Avg coverage", f"{summary['average_rule_coverage']:.0%}")}
    {_metric("Semantic warnings", summary["semantic_warnings"])}
    {_metric("Unhandled", summary["unhandled_diagnostics"])}
    {_metric("Unresolved imports", summary["unresolved_imports"])}
  </section>
  <section>
    <h2>Files</h2>
    <table>
      <thead>
        <tr>
          <th>File</th>
          <th>Package</th>
          <th>Parse</th>
          <th>Coverage</th>
          <th>Warnings</th>
          <th>Unhandled</th>
          <th>Unresolved Imports</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
  <section class="columns">
    <article>
      <h2>Annotations</h2>
      <ul>{annotations or "<li>No annotations found.</li>"}</ul>
    </article>
    <article>
      <h2>Boundary Candidates</h2>
      <ul>{imports or "<li>No unresolved imports found.</li>"}</ul>
    </article>
  </section>
  <section>
    <h2>Hotspots</h2>
    <div class="columns">{hotspot_columns}</div>
  </section>
  <section>
    <h2>Recommended Next Commands</h2>
    <ul>{commands}</ul>
  </section>
</main>
</body>
</html>
"""


def render_config_suggestions(assessment: DoctorAssessment) -> str:
    payload = assessment.payload
    suggestions = payload["config_suggestions"]
    lines = [
        "# Generated by j2py doctor.",
        "# Review these advisory suggestions before copying them into j2py config.",
        "schema_version: 1",
        f"source: {_yaml_scalar(str(payload['source']))}",
        "config_suggestions:",
    ]
    for key in ("import_map", "type_map", "annotation_map"):
        lines.append(f"  {key}:")
        items = suggestions[key]
        if not items:
            lines.append("    []")
            continue
        for item in items:
            lines.append("    -")
            for item_key in sorted(item):
                lines.append(f"      {item_key}: {_yaml_scalar(item[item_key])}")
    return "\n".join(lines) + "\n"


def render_doctor_diff_text(diff: DoctorDiff) -> str:
    payload = diff.payload
    summary_delta = payload["summary_delta"]
    lines = [
        "Doctor assessment diff",
        f"Before: {payload['before_source']}",
        f"After: {payload['after_source']}",
        "",
        "Summary delta:",
    ]
    for key in sorted(summary_delta):
        delta = summary_delta[key]
        if isinstance(delta, float):
            lines.append(f"  {key}: {delta:+.3f}")
        else:
            lines.append(f"  {key}: {delta:+}")
    lines.extend(
        [
            "",
            f"Parse failures: {len(payload['parse_failures']['removed'])} removed, "
            f"{len(payload['parse_failures']['added'])} added",
            f"Unresolved imports: {len(payload['unresolved_imports']['removed'])} removed, "
            f"{len(payload['unresolved_imports']['added'])} added",
            f"Semantic warnings: {len(payload['semantic_warnings']['removed'])} removed, "
            f"{len(payload['semantic_warnings']['added'])} added",
            f"Unhandled diagnostics: {len(payload['unhandled_diagnostics']['removed'])} removed, "
            f"{len(payload['unhandled_diagnostics']['added'])} added",
        ]
    )
    changed_files = payload["file_changes"]["changed"]
    if changed_files:
        lines.extend(["", "Changed files:"])
        for item in changed_files[:20]:
            lines.append(
                f"  {item['path']}: coverage {item['rule_coverage_delta']:+.3f}, "
                f"warnings {item['semantic_warnings_delta']:+}, "
                f"unhandled {item['unhandled_delta']:+}, "
                f"unresolved imports {item['unresolved_imports_delta']:+}"
            )
    return "\n".join(lines) + "\n"


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
            else [_diagnostic_payload(item) for item in diagnostics.warnings],
            "unhandled": []
            if diagnostics is None
            else [_diagnostic_payload(item) for item in diagnostics.unhandled],
            "todos": _todo_lines(result.python_source),
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


def _files_by_path(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["path"]: item for item in payload.get("files", [])}


def _imports_by_name(imports: Any) -> dict[str, dict[str, Any]]:
    return {item["import"]: item for item in imports}


def _summary_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(before) | set(after))
    return {
        key: after.get(key, 0) - before.get(key, 0)
        for key in keys
        if isinstance(before.get(key, 0), (int, float))
        and isinstance(after.get(key, 0), (int, float))
    }


def _diagnostic_keys(
    files: dict[str, dict[str, Any]],
    diagnostic_key: str,
) -> dict[tuple[str, int | None, str, str, str], dict[str, Any]]:
    diagnostics: dict[tuple[str, int | None, str, str, str], dict[str, Any]] = {}
    for path, item in files.items():
        for diagnostic in item["translation"][diagnostic_key]:
            key = (
                path,
                diagnostic["line"],
                diagnostic["node_type"],
                diagnostic["reason"],
                diagnostic["text"],
            )
            diagnostics[key] = {"path": path, **diagnostic}
    return diagnostics


def _diagnostic_entries(
    diagnostics: dict[tuple[str, int | None, str, str, str], dict[str, Any]],
    keys: set[tuple[str, int | None, str, str, str]],
) -> list[dict[str, Any]]:
    return [diagnostics[key] for key in sorted(keys)]


def _file_changes(
    before_files: dict[str, dict[str, Any]],
    after_files: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    added = sorted(set(after_files) - set(before_files))
    removed = sorted(set(before_files) - set(after_files))
    changed: list[dict[str, Any]] = []
    for path in sorted(set(before_files) & set(after_files)):
        before = before_files[path]
        after = after_files[path]
        item = {
            "path": path,
            "parse_ok_changed": before["parse_ok"] != after["parse_ok"],
            "rule_coverage_delta": after["translation"]["rule_coverage"]
            - before["translation"]["rule_coverage"],
            "semantic_warnings_delta": len(after["translation"]["semantic_warnings"])
            - len(before["translation"]["semantic_warnings"]),
            "unhandled_delta": len(after["translation"]["unhandled"])
            - len(before["translation"]["unhandled"]),
            "unresolved_imports_delta": len(after["unresolved_imports"])
            - len(before["unresolved_imports"]),
        }
        if any(value for key, value in item.items() if key != "path"):
            changed.append(item)
    return {
        "added": [{"path": path} for path in added],
        "removed": [{"path": path} for path in removed],
        "changed": changed,
    }


def _yaml_scalar(value: str) -> str:
    return json.dumps(value)


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
        "kind": _class_kind(cls),
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


def _class_kind(cls: ClassSymbol) -> str:
    if cls.is_interface:
        return "interface"
    if cls.is_enum:
        return "enum"
    if cls.is_record:
        return "record"
    return "class"


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


def _diagnostic_payload(item: TranslationDiagnostic) -> dict[str, Any]:
    return {
        "line": item.line,
        "node_type": item.node_type,
        "reason": item.reason,
        "text": item.text,
    }


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


def _todo_lines(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if "TODO(j2py)" in line or "__j2py_todo__" in line
    ]


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


def _metric(label: str, value: object) -> str:
    return f"<article><span>{escape(label)}</span><strong>{escape(str(value))}</strong></article>"


def _file_row(item: dict[str, Any]) -> str:
    translation = item["translation"]
    return f"""
<tr>
  <td>{escape(item["path"])}</td>
  <td>{escape(item["package"])}</td>
  <td>{"pass" if item["parse_ok"] else "fail"}</td>
  <td>{translation["rule_coverage"]:.0%}</td>
  <td>{len(translation["semantic_warnings"])}</td>
  <td>{len(translation["unhandled"])}</td>
  <td>{len(item["unresolved_imports"])}</td>
</tr>"""


def _hotspot_list(title: str, items: list[dict[str, Any]], label_key: str) -> str:
    rows = "\n".join(
        f"<li><code>{escape(str(item[label_key]))}</code>: "
        f"{escape(str(item.get('count', _hotspot_value(item))))}</li>"
        for item in items
    )
    return f"""
<article>
  <h3>{escape(title)}</h3>
  <ul>{rows or "<li>No hotspots found.</li>"}</ul>
</article>"""


def _hotspot_value(item: dict[str, Any]) -> str:
    if "rule_coverage" in item:
        return f"{item['rule_coverage']:.0%}"
    return ""


_ASSESSMENT_CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fa;
  --ink: #18202a;
  --muted: #667085;
  --line: #d9dee7;
  --panel: #ffffff;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: baseline;
  padding: 24px 32px;
  background: #111827;
  color: white;
}
h1, h2 { margin: 0; }
h3 { margin: 0 0 8px; }
main { padding: 24px 32px 40px; }
section {
  margin: 0 0 24px;
  padding: 20px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.summary article {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
}
.summary span { display: block; color: var(--muted); }
.summary strong { font-size: 22px; }
.columns {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 8px; }
th { color: var(--muted); font-weight: 600; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
li span { color: var(--muted); }
"""

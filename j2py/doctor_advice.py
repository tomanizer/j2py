"""Doctor advice generation helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from j2py.doctor_models import DoctorAssessment
from j2py.llm.prompts import ADVICE_PROMPT_VERSION

AdviceOutputFormat = Literal["json", "markdown"]


def _take(items: list[Any], limit: int | None) -> list[Any]:
    if limit is None:
        return items
    return items[: max(limit, 0)]


def build_doctor_advice_context(
    assessment: DoctorAssessment,
    *,
    max_evidence_items: int = 12,
) -> tuple[str, str, str]:
    """Build a compact evidence context for prompt construction.

    Returns:
        (context_json, context_fingerprint, source_label)
    """
    payload = assessment.payload
    summary = payload.get("summary", {})
    files = payload.get("files", [])
    hotspots = payload.get("hotspots", {})
    unresolved = payload.get("unresolved_imports", [])
    top_risk_files = summary.get("top_risk_files", [])
    clusters = payload.get("diagnostic_clusters", [])

    parse_failure_files = [
        {
            "path": item.get("path"),
            "reasons": [reason.get("reason") for reason in item.get("risk_reasons", [])],
        }
        for item in files
        if not item.get("parse_ok", True)
    ]
    parse_failure_files = [item for item in parse_failure_files if item["path"]]

    evidence = {
        "schema_version": payload.get("schema_version"),
        "source": payload.get("source"),
        "summary": {
            "files": summary.get("files", 0),
            "classes": summary.get("classes", 0),
            "parse_failures": summary.get("parse_failures", 0),
            "graph_warnings": summary.get("graph_warnings", 0),
            "semantic_warnings": summary.get("semantic_warnings", 0),
            "unhandled_diagnostics": summary.get("unhandled_diagnostics", 0),
            "todo_lines": summary.get("todo_lines", 0),
            "unresolved_imports": summary.get("unresolved_imports", 0),
            "average_rule_coverage": summary.get("average_rule_coverage", 0.0),
            "average_risk_score": summary.get("average_risk_score", 0.0),
            "max_risk_score": summary.get("max_risk_score", 0.0),
            "min_risk_score": summary.get("min_risk_score", 0.0),
            "readiness_distribution": summary.get("readiness_distribution", []),
            "top_risk_files": _take(top_risk_files, max_evidence_items),
        },
        "issue_slices": {
            "parse_failures": _take(parse_failure_files, max_evidence_items),
            "top_risk_files": _take(top_risk_files, max_evidence_items),
            "unresolved_imports": {
                "count": len(unresolved),
                "top_packages": _take(
                    sorted(
                        hotspots.get("unresolved_import_packages", []),
                        key=lambda item: (-item.get("count", 0), str(item.get("package", ""))),
                    ),
                    max_evidence_items,
                ),
            },
            "rule_gap_signal_files": _take(
                hotspots.get("lowest_coverage_files", []),
                max_evidence_items,
            ),
            "high_risk_files": _take(hotspots.get("highest_risk_files", []), max_evidence_items),
            "top_warning_nodes": _take(
                hotspots.get("unhandled_node_types", []), max_evidence_items
            ),
            "top_warning_reasons": _take(
                hotspots.get("semantic_warning_reasons", []), max_evidence_items
            ),
        },
        "clusters": _take(clusters, max_evidence_items),
        "config_suggestions": {
            "import_map": _take(
                payload.get("config_suggestions", {}).get("import_map", []), max_evidence_items
            ),
            "type_map": _take(
                payload.get("config_suggestions", {}).get("type_map", []), max_evidence_items
            ),
            "annotation_map": _take(
                payload.get("config_suggestions", {}).get("annotation_map", []),
                max_evidence_items,
            ),
        },
        "recommended_next_commands": _take(
            payload.get("recommended_next_commands", []), max_evidence_items
        ),
    }

    context = json.dumps(evidence, sort_keys=True)
    return context, _fingerprint(context), payload.get("source", "assessment")


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def render_doctor_advice_json(
    advice_markdown: str,
    *,
    assessment: DoctorAssessment,
    provider: str,
    model: str,
    output_format: AdviceOutputFormat,
    max_evidence_items: int,
    evidence_fingerprint: str,
) -> str:
    """Render machine-friendly advisor output."""
    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "prompt_version": ADVICE_PROMPT_VERSION,
        "output_format": output_format,
        "max_evidence_items": max_evidence_items,
        "input_fingerprint": evidence_fingerprint,
        "generated_at": datetime.now(UTC)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        ),
        "source": assessment.payload.get("source", ""),
        "schema_version": assessment.payload.get("schema_version"),
        "advice_markdown": advice_markdown,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"

"""File-level migration-readiness scoring for doctor assessments."""

from __future__ import annotations

from typing import Any

_RISK_REASONS_LIMIT = 6
_RISK_BAND_THRESHOLD_CRITICAL = 80.0
_RISK_BAND_THRESHOLD_HIGH = 55.0
_RISK_BAND_THRESHOLD_MEDIUM = 25.0
_RISK_RULE_COVERAGE_WEIGHT = 55.0
_RISK_WARNING_WEIGHT_PER_UNIT = 3.0
_RISK_UNHANDLED_WEIGHT_PER_UNIT = 4.0
_RISK_TODO_WEIGHT_PER_UNIT = 1.0
_RISK_UNRESOLVED_IMPORT_WEIGHT_PER_UNIT = 1.0
_RISK_FRAMEWORK_BOUNDARY_WEIGHT_PER_UNIT = 3.0
_RISK_VALIDATION_FAILURE_WEIGHT = 30.0

READINESS_BUCKETS: tuple[str, ...] = (
    "ready_to_translate",
    "needs_config",
    "needs_rule_work",
    "framework_boundary",
    "manual_port",
    "parse_blocked",
)

LEGACY_READINESS_BUCKETS: tuple[str, ...] = (
    "ready",
    "requires_manual_fixes",
    "not_ready",
)


def migration_readiness_profile(
    *,
    parse_ok: bool,
    parse_error_count: int,
    rule_coverage: float,
    semantic_warnings: list[dict[str, Any]],
    unhandled: list[dict[str, Any]],
    todo_count: int,
    unresolved_imports: list[dict[str, str]],
    annotations: list[dict[str, Any]],
    validation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the canonical file-level migration-readiness payload."""
    if not parse_ok:
        return _profile(
            bucket="parse_blocked",
            risk_score=100.0,
            reasons=[
                _reason(
                    "parse_errors",
                    parse_error_count,
                    100.0,
                    "Java parse errors must be fixed before migration assessment is reliable",
                )
            ],
        )

    reasons: list[dict[str, Any]] = []
    coverage_gap = max(0.0, 1.0 - max(0.0, min(1.0, rule_coverage)))
    coverage_weight = round(coverage_gap * _RISK_RULE_COVERAGE_WEIGHT, 3)
    if coverage_weight > 0.0:
        reasons.append(
            _reason(
                "low_rule_coverage",
                int(round(coverage_gap * 100)),
                coverage_weight,
                "Rule-layer translation coverage is below complete coverage",
            )
        )

    warning_count = len(semantic_warnings)
    warning_weight = round(min(warning_count, 24) * _RISK_WARNING_WEIGHT_PER_UNIT, 3)
    if warning_weight > 0.0:
        reasons.append(
            _reason(
                "semantic_warnings",
                warning_count,
                warning_weight,
                "Translation emitted semantic warnings that need review",
            )
        )

    unhandled_count = len(unhandled)
    unhandled_weight = round(min(unhandled_count, 20) * _RISK_UNHANDLED_WEIGHT_PER_UNIT, 3)
    if unhandled_weight > 0.0:
        reasons.append(
            _reason(
                "unhandled_nodes",
                unhandled_count,
                unhandled_weight,
                "Translation left unhandled Java constructs",
            )
        )

    todo_weight = round(min(max(0, todo_count), 20) * _RISK_TODO_WEIGHT_PER_UNIT, 3)
    if todo_weight > 0.0:
        reasons.append(
            _reason(
                "todo_markers",
                todo_count,
                todo_weight,
                "Generated Python contains TODO markers",
            )
        )

    config_imports = [
        item
        for item in unresolved_imports
        if item.get("category") not in {"framework-boundary", "platform-boundary"}
    ]
    config_weight = round(
        min(len(config_imports), 30) * _RISK_UNRESOLVED_IMPORT_WEIGHT_PER_UNIT,
        3,
    )
    if config_weight > 0.0:
        reasons.append(
            _reason(
                "unresolved_imports",
                len(config_imports),
                config_weight,
                "Unresolved imports need config mapping, stubs, or project-owned review",
            )
        )

    boundary_count = _boundary_count(unresolved_imports, annotations)
    boundary_weight = round(
        min(boundary_count, 20) * _RISK_FRAMEWORK_BOUNDARY_WEIGHT_PER_UNIT,
        3,
    )
    if boundary_weight > 0.0:
        reasons.append(
            _reason(
                "framework_boundaries",
                boundary_count,
                boundary_weight,
                "Framework or platform boundary needs explicit target-stack policy",
            )
        )

    validation_failed = _validation_failed(validation)
    if validation_failed:
        reasons.append(
            _reason(
                "validation_failures",
                len(validation.get("errors", [])) if validation else 1,
                _RISK_VALIDATION_FAILURE_WEIGHT,
                "Generated Python validation failed when validation was requested",
            )
        )

    risk_score = min(100.0, round(sum(float(item["weight"]) for item in reasons), 3))
    reasons = sorted(
        reasons,
        key=lambda item: (float(item["weight"]), int(item["count"]), str(item["reason"])),
        reverse=True,
    )[:_RISK_REASONS_LIMIT]
    return _profile(
        bucket=_readiness_bucket(
            parse_ok=parse_ok,
            coverage_gap=coverage_gap,
            unhandled_count=unhandled_count,
            validation_failed=validation_failed,
            boundary_count=boundary_count,
            config_import_count=len(config_imports),
            warning_count=warning_count,
            todo_count=todo_count,
            risk_score=risk_score,
        ),
        risk_score=risk_score,
        reasons=reasons,
    )


def legacy_readiness_bucket(bucket: str, risk_band: str) -> str:
    """Map granular readiness buckets to the original three summary buckets."""
    if bucket in {"ready_to_translate"}:
        return "ready"
    if bucket in {"parse_blocked", "needs_rule_work"} or risk_band in {"critical", "high"}:
        return "not_ready"
    return "requires_manual_fixes"


def risk_band(score: float) -> str:
    if score >= _RISK_BAND_THRESHOLD_CRITICAL:
        return "critical"
    if score >= _RISK_BAND_THRESHOLD_HIGH:
        return "high"
    if score >= _RISK_BAND_THRESHOLD_MEDIUM:
        return "medium"
    return "low"


def _profile(
    *,
    bucket: str,
    risk_score: float,
    reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    band = risk_band(risk_score)
    return {
        "bucket": bucket,
        "risk_score": risk_score,
        "risk_band": band,
        "reasons": reasons,
        "next_action": _next_action(bucket),
    }


def _readiness_bucket(
    *,
    parse_ok: bool,
    coverage_gap: float,
    unhandled_count: int,
    validation_failed: bool,
    boundary_count: int,
    config_import_count: int,
    warning_count: int,
    todo_count: int,
    risk_score: float,
) -> str:
    if not parse_ok:
        return "parse_blocked"
    if validation_failed or unhandled_count > 0 or coverage_gap >= 0.20 or risk_score >= 55.0:
        return "needs_rule_work"
    if boundary_count > 0:
        return "framework_boundary"
    if config_import_count > 0:
        return "needs_config"
    if warning_count > 0 or todo_count > 0:
        return "manual_port"
    return "ready_to_translate"


def _next_action(bucket: str) -> str:
    return {
        "ready_to_translate": "Translate without LLM first, then review generated Python",
        "needs_config": "Add explicit import/type config or stubs before bulk migration",
        "needs_rule_work": "Improve deterministic rule coverage before bulk migration",
        "framework_boundary": "Decide target-stack policy for framework/runtime boundaries",
        "manual_port": "Review generated TODOs and semantic warnings before trusting output",
        "parse_blocked": "Fix Java parse errors or unsupported source syntax first",
    }[bucket]


def _reason(reason: str, count: int, weight: float, detail: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "count": int(max(0, count)),
        "weight": round(float(weight), 3),
        "detail": detail,
    }


def _boundary_count(
    unresolved_imports: list[dict[str, str]],
    annotations: list[dict[str, Any]],
) -> int:
    import_boundaries = sum(
        1
        for item in unresolved_imports
        if item.get("category") in {"framework-boundary", "platform-boundary"}
    )
    annotation_boundaries = sum(1 for item in annotations if item.get("framework_candidate"))
    return import_boundaries + annotation_boundaries


def _validation_failed(validation: dict[str, Any] | None) -> bool:
    return validation is not None and not bool(validation.get("ok", True))

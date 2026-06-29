"""Deterministic gate evaluation for doctor assessments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from j2py.doctor_models import DoctorAssessment, DoctorGateResult

DOCTOR_GATE_SCHEMA_VERSION = 1
DOCTOR_GATE_PROFILES: tuple[str, ...] = (
    "strict",
    "one-zero",
    "migration-trial",
    "advisory",
)
_HIGH_RISK_BANDS = {"high", "critical"}
_SAMPLE_LIMIT_DETAIL = (
    "Assessment was sampled; gate result only covers the deterministic assessed subset."
)


@dataclass(frozen=True)
class DoctorGateThresholds:
    """Thresholds used by the doctor gate evaluator.

    ``None`` means the check is not enforced by the selected profile or overrides.
    """

    max_parse_failures: int | None = None
    min_average_coverage: float | None = None
    min_file_coverage: float | None = None
    max_files_below_coverage: int | None = None
    max_semantic_warnings: int | None = None
    max_unhandled_diagnostics: int | None = None
    max_todo_lines: int | None = None
    max_validation_failures: int | None = None
    max_high_risk_files: int | None = None
    max_unresolved_imports: int | None = None
    max_parse_blocked_files: int | None = None
    max_needs_rule_work_files: int | None = None
    max_needs_config_files: int | None = None
    max_framework_boundary_files: int | None = None
    max_manual_port_files: int | None = None

    def with_overrides(self, **overrides: int | float | None) -> DoctorGateThresholds:
        payload: dict[str, Any] = asdict(self)
        payload.update({key: value for key, value in overrides.items() if value is not None})
        return DoctorGateThresholds(**payload)


def doctor_gate_thresholds_for_profile(profile: str) -> DoctorGateThresholds:
    """Return built-in thresholds for a doctor gate profile."""
    normalized = profile.lower()
    if normalized == "strict":
        return DoctorGateThresholds(
            max_parse_failures=0,
            min_average_coverage=1.0,
            min_file_coverage=1.0,
            max_files_below_coverage=0,
            max_semantic_warnings=0,
            max_unhandled_diagnostics=0,
            max_todo_lines=0,
            max_validation_failures=0,
            max_high_risk_files=0,
            max_unresolved_imports=0,
            max_parse_blocked_files=0,
            max_needs_rule_work_files=0,
            max_needs_config_files=0,
            max_framework_boundary_files=0,
            max_manual_port_files=0,
        )
    if normalized == "one-zero":
        return DoctorGateThresholds(
            max_parse_failures=0,
            min_average_coverage=1.0,
            min_file_coverage=1.0,
            max_files_below_coverage=0,
            max_unhandled_diagnostics=0,
            max_todo_lines=0,
            max_validation_failures=0,
            max_high_risk_files=0,
            max_parse_blocked_files=0,
            max_needs_rule_work_files=0,
            max_framework_boundary_files=0,
        )
    if normalized == "migration-trial":
        return DoctorGateThresholds(
            max_parse_failures=0,
            min_average_coverage=0.80,
            min_file_coverage=0.50,
            max_files_below_coverage=0,
            max_unhandled_diagnostics=0,
            max_validation_failures=0,
            max_high_risk_files=0,
            max_parse_blocked_files=0,
            max_needs_rule_work_files=0,
        )
    if normalized == "advisory":
        return DoctorGateThresholds()
    raise ValueError(
        f"unsupported doctor gate profile {profile!r}; "
        f"expected one of {', '.join(DOCTOR_GATE_PROFILES)}"
    )


def evaluate_doctor_gate(
    assessment: DoctorAssessment,
    *,
    profile: str,
    thresholds: DoctorGateThresholds | None = None,
    sample_limit: int | None = None,
) -> DoctorGateResult:
    """Evaluate a doctor assessment against deterministic gate thresholds."""
    normalized_profile = profile.lower()
    base_thresholds = doctor_gate_thresholds_for_profile(normalized_profile)
    applied = thresholds or base_thresholds
    payload = assessment.payload
    summary = payload.get("summary", {})
    files = list(payload.get("files", []))
    checks = _gate_checks(summary, files, applied)
    failures = [item for item in checks if not item["passed"]]
    caveats = _gate_caveats(files, thresholds=applied, sample_limit=sample_limit)
    return DoctorGateResult(
        {
            "schema_version": DOCTOR_GATE_SCHEMA_VERSION,
            "source": payload.get("source"),
            "profile": normalized_profile,
            "passed": not failures,
            "summary": {
                "checks": len(checks),
                "failures": len(failures),
                "files": summary.get("files", len(files)),
                "sample_limit": sample_limit,
            },
            "thresholds": _threshold_payload(applied),
            "checks": checks,
            "failures": failures,
            "caveats": caveats,
        }
    )


def render_doctor_gate_text(result: DoctorGateResult) -> str:
    """Render a concise text summary for CLI output."""
    payload = result.payload
    status = "passed" if payload["passed"] else "failed"
    summary = payload["summary"]
    lines = [
        (
            f"Doctor gate {status}: profile={payload['profile']}, "
            f"checks={summary['checks']}, failures={summary['failures']}"
        )
    ]
    for failure in payload.get("failures", []):
        lines.append(
            "  - {check}: actual {actual} {operator} threshold {threshold}".format(
                check=failure["check"],
                actual=_format_value(failure.get("actual")),
                operator=failure["operator"],
                threshold=_format_value(failure.get("threshold")),
            )
        )
        detail = failure.get("detail")
        if detail:
            lines.append(f"    {detail}")
    for caveat in payload.get("caveats", []):
        lines.append(f"  caveat: {caveat['detail']}")
    return "\n".join(lines) + "\n"


def _gate_checks(
    summary: dict[str, Any],
    files: list[dict[str, Any]],
    thresholds: DoctorGateThresholds,
) -> list[dict[str, Any]]:
    readiness = _readiness_counts(summary)
    return [
        *_max_check(
            "parse_failures",
            summary.get("parse_failures", 0),
            thresholds.max_parse_failures,
            affected=_parse_failure_files(files),
        ),
        *_min_check(
            "average_rule_coverage",
            summary.get("average_rule_coverage", 0.0),
            thresholds.min_average_coverage,
        ),
        *_max_check(
            "files_below_coverage",
            _files_below_coverage(files, thresholds.min_file_coverage),
            _max_files_below_coverage_threshold(thresholds),
            threshold_detail=thresholds.min_file_coverage,
            affected=_coverage_file_details(files, thresholds.min_file_coverage),
        ),
        *_max_check(
            "semantic_warnings",
            summary.get("semantic_warnings", 0),
            thresholds.max_semantic_warnings,
        ),
        *_max_check(
            "unhandled_diagnostics",
            summary.get("unhandled_diagnostics", 0),
            thresholds.max_unhandled_diagnostics,
        ),
        *_max_check("todo_lines", summary.get("todo_lines", 0), thresholds.max_todo_lines),
        *_max_check(
            "validation_failures",
            _validation_failure_count(files),
            thresholds.max_validation_failures,
            affected=_validation_failure_files(files),
        ),
        *_max_check(
            "high_risk_files",
            _high_risk_file_count(files),
            thresholds.max_high_risk_files,
            affected=_high_risk_file_details(files),
        ),
        *_max_check(
            "unresolved_imports",
            summary.get("unresolved_imports", 0),
            thresholds.max_unresolved_imports,
        ),
        *_max_check(
            "parse_blocked_files",
            readiness["parse_blocked"],
            thresholds.max_parse_blocked_files,
        ),
        *_max_check(
            "needs_rule_work_files",
            readiness["needs_rule_work"],
            thresholds.max_needs_rule_work_files,
        ),
        *_max_check(
            "needs_config_files",
            readiness["needs_config"],
            thresholds.max_needs_config_files,
        ),
        *_max_check(
            "framework_boundary_files",
            readiness["framework_boundary"],
            thresholds.max_framework_boundary_files,
        ),
        *_max_check(
            "manual_port_files",
            readiness["manual_port"],
            thresholds.max_manual_port_files,
        ),
    ]


def _min_check(
    name: str,
    actual: Any,
    threshold: float | None,
) -> list[dict[str, Any]]:
    if threshold is None:
        return []
    value = float(actual)
    return [
        _check(
            name,
            actual=round(value, 6),
            operator=">=",
            threshold=threshold,
            passed=value >= threshold,
        )
    ]


def _max_check(
    name: str,
    actual: Any,
    threshold: int | None,
    *,
    threshold_detail: float | None = None,
    affected: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if threshold is None:
        return []
    value = int(actual)
    detail = None
    if threshold_detail is not None:
        detail = f"coverage threshold {threshold_detail:.3f}"
    return [
        _check(
            name,
            actual=value,
            operator="<=",
            threshold=threshold,
            passed=value <= threshold,
            detail=detail,
            affected=affected or [],
        )
    ]


def _check(
    name: str,
    *,
    actual: int | float,
    operator: str,
    threshold: int | float,
    passed: bool,
    detail: str | None = None,
    affected: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "check": name,
        "passed": passed,
        "actual": actual,
        "operator": operator,
        "threshold": threshold,
    }
    if detail:
        payload["detail"] = detail
    if affected:
        payload["affected"] = affected[:20]
    return payload


def _readiness_counts(summary: dict[str, Any]) -> dict[str, int]:
    counts = {
        "ready_to_translate": 0,
        "needs_config": 0,
        "needs_rule_work": 0,
        "framework_boundary": 0,
        "manual_port": 0,
        "parse_blocked": 0,
    }
    for item in summary.get("migration_readiness_distribution", []):
        bucket = item.get("bucket")
        if bucket in counts:
            counts[bucket] = int(item.get("files", 0))
    return counts


def _files_below_coverage(files: list[dict[str, Any]], threshold: float | None) -> int:
    if threshold is None:
        return 0
    return len(_coverage_file_details(files, threshold))


def _max_files_below_coverage_threshold(thresholds: DoctorGateThresholds) -> int | None:
    if thresholds.min_file_coverage is None:
        return None
    if thresholds.max_files_below_coverage is None:
        return 0
    return thresholds.max_files_below_coverage


def _coverage_file_details(
    files: list[dict[str, Any]], threshold: float | None
) -> list[dict[str, Any]]:
    if threshold is None:
        return []
    return [
        {
            "path": item.get("path"),
            "rule_coverage": _file_coverage(item),
            "risk_score": item.get("risk_score", 0.0),
        }
        for item in files
        if _file_coverage(item) < threshold
    ]


def _file_coverage(item: dict[str, Any]) -> float:
    translation = item.get("translation", {})
    return float(translation.get("rule_coverage", 0.0))


def _parse_failure_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": item.get("path"),
            "parse_errors": len(item.get("parse_errors", [])),
        }
        for item in files
        if item.get("parse_ok") is False
    ]


def _validation_failure_count(files: list[dict[str, Any]]) -> int:
    return len(_validation_failure_files(files))


def _validation_failure_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for item in files:
        validation = item.get("translation", {}).get("validation")
        if isinstance(validation, dict) and validation.get("ok") is False:
            failed.append(
                {
                    "path": item.get("path"),
                    "errors": len(validation.get("errors", [])),
                }
            )
    return failed


def _high_risk_file_count(files: list[dict[str, Any]]) -> int:
    return len(_high_risk_file_details(files))


def _high_risk_file_details(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": item.get("path"),
            "risk_score": item.get("risk_score", 0.0),
            "risk_band": item.get("risk_band", "low"),
            "readiness_bucket": item.get("readiness_bucket", ""),
            "migration_bucket": item.get("migration_readiness", {}).get("bucket", ""),
        }
        for item in files
        if item.get("risk_band") in _HIGH_RISK_BANDS
    ]


def _gate_caveats(
    files: list[dict[str, Any]],
    *,
    thresholds: DoctorGateThresholds,
    sample_limit: int | None,
) -> list[dict[str, str]]:
    caveats: list[dict[str, str]] = []
    if sample_limit is not None:
        caveats.append({"caveat": "sampled_assessment", "detail": _SAMPLE_LIMIT_DETAIL})
    if thresholds.max_validation_failures is not None and not any(
        isinstance(item.get("translation", {}).get("validation"), dict) for item in files
    ):
        caveats.append(
            {
                "caveat": "validation_not_included",
                "detail": "Validation failure checks only apply when --include-validation is used.",
            }
        )
    return caveats


def _threshold_payload(thresholds: DoctorGateThresholds) -> dict[str, int | float]:
    return {key: value for key, value in asdict(thresholds).items() if value is not None}


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)

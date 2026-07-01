"""Comparison helpers for doctor assessment payloads."""

from __future__ import annotations

from typing import Any

from j2py.doctor_models import DOCTOR_SCHEMA_VERSION, DoctorAssessment, DoctorDiff

_MIGRATION_BUCKET_RANK = {
    "ready_to_translate": 0,
    "manual_port": 1,
    "needs_config": 2,
    "framework_boundary": 3,
    "needs_rule_work": 4,
    "parse_blocked": 5,
}
_LEGACY_BUCKET_RANK = {
    "ready": 0,
    "ready_to_translate": 0,
    "requires_manual_fixes": 1,
    "manual_port": 1,
    "not_ready": 2,
}
_DIFF_RANK_LIMIT = 10


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

    file_changes = _file_changes(before_files, after_files)
    improved_files = _rank_improved_files(file_changes["changed"])
    regressed_files = _rank_regressed_files(file_changes["changed"])
    diagnostic_clusters = _cluster_delta(
        before_payload.get("diagnostic_clusters", []),
        after_payload.get("diagnostic_clusters", []),
    )
    config_suggestions = _config_suggestion_delta(
        before_payload.get("config_suggestions", {}),
        after_payload.get("config_suggestions", {}),
    )
    validation_status_changes = _validation_status_changes(before_files, after_files)
    summary_delta = _summary_delta(
        before_payload.get("summary", {}),
        after_payload.get("summary", {}),
    )
    readiness_delta = _readiness_delta(
        before_payload.get("summary", {}),
        after_payload.get("summary", {}),
    )
    risk_delta = _risk_delta(
        before_payload.get("summary", {}),
        after_payload.get("summary", {}),
        improved_files=improved_files,
        regressed_files=regressed_files,
    )
    payload = {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "before_source": before_payload.get("source"),
        "after_source": after_payload.get("source"),
        "summary_delta": summary_delta,
        "readiness_delta": readiness_delta,
        "risk_delta": risk_delta,
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
        "diagnostic_clusters": diagnostic_clusters,
        "config_suggestions": config_suggestions,
        "validation_status_changes": validation_status_changes,
        "file_changes": file_changes,
        "improved_files": improved_files,
        "regressed_files": regressed_files,
    }
    payload["regression_summary"] = _regression_summary(payload)
    return DoctorDiff(payload=payload)


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


def _readiness_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "legacy": _distribution_delta(
            before.get("readiness_distribution", []),
            after.get("readiness_distribution", []),
        ),
        "migration": _distribution_delta(
            before.get("migration_readiness_distribution", []),
            after.get("migration_readiness_distribution", []),
        ),
    }


def _distribution_delta(
    before_items: list[dict[str, Any]],
    after_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before = {str(item.get("bucket", "")): int(item.get("files", 0)) for item in before_items}
    after = {str(item.get("bucket", "")): int(item.get("files", 0)) for item in after_items}
    return [
        {
            "bucket": bucket,
            "before": before.get(bucket, 0),
            "after": after.get(bucket, 0),
            "delta": after.get(bucket, 0) - before.get(bucket, 0),
        }
        for bucket in sorted(set(before) | set(after))
    ]


def _risk_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    improved_files: list[dict[str, Any]],
    regressed_files: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "average_risk_score_delta": float(after.get("average_risk_score", 0.0))
        - float(before.get("average_risk_score", 0.0)),
        "max_risk_score_delta": float(after.get("max_risk_score", 0.0))
        - float(before.get("max_risk_score", 0.0)),
        "min_risk_score_delta": float(after.get("min_risk_score", 0.0))
        - float(before.get("min_risk_score", 0.0)),
        "improved_file_count": len(improved_files),
        "regressed_file_count": len(regressed_files),
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
    return [
        diagnostics[key]
        for key in sorted(
            keys,
            key=lambda k: (k[0], k[1] if k[1] is not None else -1, k[2], k[3], k[4]),
        )
    ]


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
            "risk_score_delta": float(after.get("risk_score", 0.0))
            - float(before.get("risk_score", 0.0)),
            "readiness_bucket_before": _legacy_bucket(before),
            "readiness_bucket_after": _legacy_bucket(after),
            "migration_bucket_before": _migration_bucket(before),
            "migration_bucket_after": _migration_bucket(after),
            "validation_status_before": _validation_status(before),
            "validation_status_after": _validation_status(after),
        }
        item["validation_status_changed"] = (
            item["validation_status_before"] != item["validation_status_after"]
        )
        if (
            any(
                value
                for key, value in item.items()
                if key
                not in {
                    "path",
                    "readiness_bucket_before",
                    "readiness_bucket_after",
                    "migration_bucket_before",
                    "migration_bucket_after",
                    "validation_status_before",
                    "validation_status_after",
                }
            )
            or item["readiness_bucket_before"] != item["readiness_bucket_after"]
            or item["migration_bucket_before"] != item["migration_bucket_after"]
            or item["validation_status_changed"]
        ):
            changed.append(item)
    return {
        "added": [{"path": path} for path in added],
        "removed": [{"path": path} for path in removed],
        "changed": changed,
    }


def _legacy_bucket(item: dict[str, Any]) -> str:
    return str(item.get("readiness_bucket", item.get("migration_readiness", {}).get("bucket", "")))


def _migration_bucket(item: dict[str, Any]) -> str:
    readiness = item.get("migration_readiness", {})
    if isinstance(readiness, dict) and readiness.get("bucket"):
        return str(readiness["bucket"])
    return _legacy_bucket(item)


def _validation_status(item: dict[str, Any]) -> str:
    validation = item.get("translation", {}).get("validation")
    if validation is None:
        return "not_included"
    if validation.get("ok") is True:
        return "passed"
    if validation.get("ok") is False:
        return "failed"
    return "unknown"


def _rank_improved_files(changed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    improved = [item for item in changed if _has_file_improvement(item)]
    return sorted(
        improved,
        key=lambda item: (
            item["risk_score_delta"],
            _bucket_rank(item["migration_bucket_after"], _MIGRATION_BUCKET_RANK)
            - _bucket_rank(item["migration_bucket_before"], _MIGRATION_BUCKET_RANK),
            -item["rule_coverage_delta"],
            item["path"],
        ),
    )[:_DIFF_RANK_LIMIT]


def _rank_regressed_files(changed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regressed = [item for item in changed if _has_file_regression(item)]
    return sorted(
        regressed,
        key=lambda item: (
            -item["risk_score_delta"],
            _bucket_rank(item["migration_bucket_after"], _MIGRATION_BUCKET_RANK)
            - _bucket_rank(item["migration_bucket_before"], _MIGRATION_BUCKET_RANK),
            item["rule_coverage_delta"],
            item["path"],
        ),
    )[:_DIFF_RANK_LIMIT]


def _has_file_improvement(item: dict[str, Any]) -> bool:
    return (
        item["risk_score_delta"] < 0
        or item["rule_coverage_delta"] > 0
        or _migration_bucket_delta(item) < 0
        or _legacy_bucket_delta(item) < 0
        or _blocker_delta(item) < 0
        or _validation_delta(item) < 0
    )


def _has_file_regression(item: dict[str, Any]) -> bool:
    return (
        item["risk_score_delta"] > 0
        or item["rule_coverage_delta"] < 0
        or _migration_bucket_delta(item) > 0
        or _legacy_bucket_delta(item) > 0
        or _blocker_delta(item) > 0
        or _validation_delta(item) > 0
    )


def _migration_bucket_delta(item: dict[str, Any]) -> int:
    return _bucket_rank(item["migration_bucket_after"], _MIGRATION_BUCKET_RANK) - _bucket_rank(
        item["migration_bucket_before"],
        _MIGRATION_BUCKET_RANK,
    )


def _legacy_bucket_delta(item: dict[str, Any]) -> int:
    return _bucket_rank(item["readiness_bucket_after"], _LEGACY_BUCKET_RANK) - _bucket_rank(
        item["readiness_bucket_before"],
        _LEGACY_BUCKET_RANK,
    )


def _blocker_delta(item: dict[str, Any]) -> int:
    return (
        int(item["parse_ok_changed"] and item["migration_bucket_after"] == "parse_blocked")
        - int(item["parse_ok_changed"] and item["migration_bucket_before"] == "parse_blocked")
        + int(item["semantic_warnings_delta"])
        + int(item["unhandled_delta"])
        + int(item["unresolved_imports_delta"])
    )


def _validation_delta(item: dict[str, Any]) -> int:
    return _validation_rank(item["validation_status_after"]) - _validation_rank(
        item["validation_status_before"]
    )


def _bucket_rank(bucket: str, ranking: dict[str, int]) -> int:
    return ranking.get(bucket, max(ranking.values()) + 1)


def _validation_rank(status: str) -> int:
    return {"passed": 0, "not_included": 1, "unknown": 2, "failed": 3}.get(status, 2)


def _cluster_delta(
    before_clusters: list[dict[str, Any]],
    after_clusters: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    before = _clusters_by_id(before_clusters)
    after = _clusters_by_id(after_clusters)
    before_ids = set(before)
    after_ids = set(after)
    changed = []
    for cluster_id in sorted(before_ids & after_ids):
        count_delta = int(after[cluster_id].get("count", 0)) - int(
            before[cluster_id].get("count", 0)
        )
        if count_delta:
            changed.append(
                {
                    "cluster_id": cluster_id,
                    "reason": after[cluster_id].get("reason", before[cluster_id].get("reason")),
                    "count_before": before[cluster_id].get("count", 0),
                    "count_after": after[cluster_id].get("count", 0),
                    "count_delta": count_delta,
                }
            )
    return {
        "added": [after[key] for key in sorted(after_ids - before_ids)],
        "removed": [before[key] for key in sorted(before_ids - after_ids)],
        "changed": sorted(
            changed,
            key=lambda item: (-abs(item["count_delta"]), item["cluster_id"]),
        ),
    }


def _clusters_by_id(clusters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("cluster_id", "")): item for item in clusters if item.get("cluster_id")}


def _config_suggestion_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    output: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for family, key_name in (
        ("import_map", "java_import"),
        ("type_map", "java_type"),
        ("annotation_map", "annotation"),
    ):
        before_items = _suggestions_by_key(before.get(family, []), key_name)
        after_items = _suggestions_by_key(after.get(family, []), key_name)
        before_keys = set(before_items)
        after_keys = set(after_items)
        output[family] = {
            "resolved": [before_items[key] for key in sorted(before_keys - after_keys)],
            "added": [after_items[key] for key in sorted(after_keys - before_keys)],
        }
    return output


def _suggestions_by_key(items: list[dict[str, Any]], key_name: str) -> dict[str, dict[str, Any]]:
    return {str(item.get(key_name, "")): item for item in items if item.get(key_name)}


def _validation_status_changes(
    before_files: dict[str, dict[str, Any]],
    after_files: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    changes = []
    for path in sorted(set(before_files) & set(after_files)):
        before_status = _validation_status(before_files[path])
        after_status = _validation_status(after_files[path])
        if before_status != after_status:
            changes.append(
                {
                    "path": path,
                    "before": before_status,
                    "after": after_status,
                }
            )
    return changes


def _regression_summary(payload: dict[str, Any]) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    if payload["parse_failures"]["added"]:
        reasons.append(
            {
                "reason": "parse_failures_added",
                "count": len(payload["parse_failures"]["added"]),
            }
        )
    for key in ("unresolved_imports", "semantic_warnings", "unhandled_diagnostics"):
        if payload[key]["added"]:
            reasons.append({"reason": f"{key}_added", "count": len(payload[key]["added"])})
    if payload["diagnostic_clusters"]["added"]:
        reasons.append(
            {
                "reason": "diagnostic_clusters_added",
                "count": len(payload["diagnostic_clusters"]["added"]),
            }
        )
    if payload["regressed_files"]:
        reasons.append({"reason": "files_regressed", "count": len(payload["regressed_files"])})
    failed_validations = [
        item for item in payload["validation_status_changes"] if item["after"] == "failed"
    ]
    if failed_validations:
        reasons.append({"reason": "validation_failures_added", "count": len(failed_validations)})
    return {
        "passed": not reasons,
        "reasons": reasons,
        "improved_file_count": len(payload["improved_files"]),
        "regressed_file_count": len(payload["regressed_files"]),
    }

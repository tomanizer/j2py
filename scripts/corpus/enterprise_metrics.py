"""Enterprise readiness metrics for corpus scoreboards.

Complements node ``coverage`` (handled/unhandled AST ticks) with signals that better
reflect Spring application-layer translation readiness: annotation surface area,
annotation-related semantic warnings, and files with real method bodies vs
annotation-only stubs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from annotation_filter import DEFAULT_ENTERPRISE_ANNOTATIONS, total_annotation_hits

from j2py.parse.java_ast import ParsedFile

_ANNOTATION_WARNING_RE = re.compile(r"\bannotation\b", re.IGNORECASE)
_METHOD_BODY_NODES = frozenset({"method_declaration", "constructor_declaration"})


def count_method_bodies(parsed: ParsedFile) -> int:
    """Count methods/constructors whose body block contains at least one statement."""
    count = 0
    for node in parsed.root.walk():
        if node.type not in _METHOD_BODY_NODES:
            continue
        body = node.child_by_field("body")
        if body is not None and body.named_children:
            count += 1
    return count


def count_annotation_warnings(warnings: tuple[Any, ...] | list[Any]) -> int:
    return sum(1 for warning in warnings if _ANNOTATION_WARNING_RE.search(warning.reason))


def count_annotation_uses(
    text: str,
    *,
    annotation_names: tuple[str, ...] = DEFAULT_ENTERPRISE_ANNOTATIONS,
) -> int:
    if not annotation_names:
        return 0
    return total_annotation_hits(text, annotation_names)


@dataclass(frozen=True)
class FileEnterpriseSignals:
    method_body_count: int
    annotation_use_count: int
    annotation_warning_count: int

    @property
    def is_annotation_only_stub(self) -> bool:
        return self.annotation_use_count > 0 and self.method_body_count == 0


def file_enterprise_signals(
    *,
    parsed: ParsedFile,
    source_text: str,
    warnings: tuple[Any, ...] | list[Any],
    annotation_names: tuple[str, ...] = DEFAULT_ENTERPRISE_ANNOTATIONS,
) -> FileEnterpriseSignals:
    return FileEnterpriseSignals(
        method_body_count=count_method_bodies(parsed),
        annotation_use_count=count_annotation_uses(source_text, annotation_names=annotation_names),
        annotation_warning_count=count_annotation_warnings(warnings),
    )


def summarize_enterprise(metrics: list[Any]) -> dict[str, Any]:
    """Aggregate per-file enterprise signals into a summary block."""
    if not metrics:
        return {}

    total = len(metrics)
    files_with_method_bodies = sum(m.method_body_count > 0 for m in metrics)
    annotation_only_stub_files = sum(
        m.annotation_use_count > 0 and m.method_body_count == 0 for m in metrics
    )
    total_annotation_uses = sum(m.annotation_use_count for m in metrics)
    total_annotation_warnings = sum(m.annotation_warning_count for m in metrics)
    files_with_annotation_warnings = sum(m.annotation_warning_count > 0 for m in metrics)

    return {
        "method_body_file_rate": _rate(files_with_method_bodies, total),
        "files_with_method_bodies": files_with_method_bodies,
        "annotation_only_stub_files": annotation_only_stub_files,
        "annotation_only_stub_rate": _rate(annotation_only_stub_files, total),
        "total_annotation_uses": total_annotation_uses,
        "avg_annotation_uses_per_file": total_annotation_uses / total,
        "total_annotation_warnings": total_annotation_warnings,
        "files_with_annotation_warnings": files_with_annotation_warnings,
        "annotation_warning_file_rate": _rate(files_with_annotation_warnings, total),
        "avg_annotation_warnings_per_file": total_annotation_warnings / total,
    }


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator

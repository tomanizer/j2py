"""Structured LLM review findings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal, cast

ReviewSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class LlmReviewFinding:
    """A non-mutating LLM review finding for translated output."""

    severity: ReviewSeverity
    category: str
    source_line: int | None
    output_line: int | None
    message: str
    recommendation: str | None = None


def parse_review_findings(text: str) -> list[LlmReviewFinding]:
    """Parse provider JSON into review findings, accepting a top-level list or object."""
    payload = json.loads(text)
    raw_findings = payload.get("findings", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_findings, list):
        raise ValueError("LLM review response must contain a findings list")
    return [_finding_from_payload(item) for item in raw_findings]


def review_findings_payload(findings: list[LlmReviewFinding]) -> list[dict[str, object]]:
    return [asdict(finding) for finding in findings]


def _finding_from_payload(raw: object) -> LlmReviewFinding:
    if not isinstance(raw, dict):
        raise ValueError("LLM review finding must be an object")
    severity = _severity(raw.get("severity"))
    category = _text(raw.get("category"), default="general")
    message = _text(raw.get("message"), default="")
    if not message:
        raise ValueError("LLM review finding is missing message")
    recommendation_value = raw.get("recommendation")
    recommendation = recommendation_value.strip() if isinstance(recommendation_value, str) else None
    return LlmReviewFinding(
        severity=severity,
        category=category,
        source_line=_optional_positive_int(raw.get("source_line")),
        output_line=_optional_positive_int(raw.get("output_line")),
        message=message,
        recommendation=recommendation or None,
    )


def _severity(value: object) -> ReviewSeverity:
    if isinstance(value, str) and value.lower() in {"info", "warning", "error"}:
        return cast(ReviewSeverity, value.lower())
    return "warning"


def _text(value: object, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    return value.strip() or default


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None

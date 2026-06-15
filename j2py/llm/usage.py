"""Log LLM token usage and estimated cost for Gemini (and cache hits)."""

from __future__ import annotations

import json
import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = "1"
DEFAULT_HARVEST_DIR = Path(".j2py") / "harvest"
USAGE_FILE_NAME = "usage.jsonl"

# Approximate USD per 1M tokens: (input, output). Estimates only — check Google pricing.
_GEMINI_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash": (0.075, 0.30),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.0-flash": (0.10, 0.40),
}

_source_path_ctx: ContextVar[str | None] = ContextVar("j2py_llm_usage_source_path", default=None)
_session_records: list[dict[str, object]] = []


@dataclass(frozen=True)
class UsageTotals:
    api_calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    cached_content_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0
    estimated_usd: float = 0.0


def llm_usage_logging_enabled() -> bool:
    return os.environ.get("J2PY_LLM_USAGE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def usage_log_path(*, repo_root: Path | None = None) -> Path:
    root = repo_root or Path.cwd()
    override = os.environ.get("J2PY_LLM_USAGE_PATH", "").strip()
    if override:
        return Path(override)
    return root / DEFAULT_HARVEST_DIR / USAGE_FILE_NAME


def bind_usage_source_path(path: Path | str | None) -> Token[str | None]:
    value = str(path) if path is not None else None
    return _source_path_ctx.set(value)


def reset_usage_source_path(token: Token[str | None]) -> None:
    _source_path_ctx.reset(token)


def begin_usage_session() -> None:
    _session_records.clear()


def session_record_count() -> int:
    return len(_session_records)


def summarize_usage_records(records: list[dict[str, object]]) -> UsageTotals:
    api_calls = 0
    cache_hits = 0
    prompt_tokens = 0
    candidates_tokens = 0
    cached_content_tokens = 0
    thoughts_tokens = 0
    total_tokens = 0
    estimated_usd = 0.0

    for record in records:
        kind = str(record.get("kind", "api_call"))
        if kind == "cache_hit":
            cache_hits += 1
            continue
        api_calls += 1
        prompt_tokens += _int_field(record, "prompt_tokens")
        candidates_tokens += _int_field(record, "candidates_tokens")
        cached_content_tokens += _int_field(record, "cached_content_tokens")
        thoughts_tokens += _int_field(record, "thoughts_tokens")
        total_tokens += _int_field(record, "total_tokens")
        raw_cost = record.get("estimated_usd")
        if isinstance(raw_cost, (int, float)):
            estimated_usd += float(raw_cost)

    return UsageTotals(
        api_calls=api_calls,
        cache_hits=cache_hits,
        prompt_tokens=prompt_tokens,
        candidates_tokens=candidates_tokens,
        cached_content_tokens=cached_content_tokens,
        thoughts_tokens=thoughts_tokens,
        total_tokens=total_tokens,
        estimated_usd=estimated_usd,
    )


def session_records_slice(start: int) -> list[dict[str, object]]:
    return list(_session_records[start:])


def session_usage_totals() -> UsageTotals:
    return summarize_usage_records(_session_records)


def format_usage_summary(totals: UsageTotals, *, prefix: str = "") -> str:
    lead = f"{prefix} " if prefix else ""
    parts = [
        f"{lead}api_calls={totals.api_calls}",
        f"cache_hits={totals.cache_hits}",
        f"tokens in={totals.prompt_tokens}",
        f"out={totals.candidates_tokens}",
        f"total={totals.total_tokens}",
    ]
    if totals.estimated_usd > 0:
        parts.append(f"est=${totals.estimated_usd:.4f}")
    return "usage: " + ", ".join(parts)


def extract_gemini_usage_metadata(response: object) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    return {
        "prompt_tokens": _coerce_int(getattr(usage, "prompt_token_count", None)),
        "candidates_tokens": _coerce_int(getattr(usage, "candidates_token_count", None)),
        "cached_content_tokens": _coerce_int(getattr(usage, "cached_content_token_count", None)),
        "thoughts_tokens": _coerce_int(getattr(usage, "thoughts_token_count", None)),
        "total_tokens": _coerce_int(getattr(usage, "total_token_count", None)),
    }


def estimate_gemini_cost_usd(
    model: str,
    *,
    prompt_tokens: int,
    candidates_tokens: int,
) -> float | None:
    rates = _pricing_for_model(model)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return (prompt_tokens * input_rate + candidates_tokens * output_rate) / 1_000_000


def record_llm_usage(
    *,
    provider: str,
    model: str,
    kind: str,
    prompt_tokens: int = 0,
    candidates_tokens: int = 0,
    cached_content_tokens: int = 0,
    thoughts_tokens: int = 0,
    total_tokens: int = 0,
    estimated_usd: float | None = None,
    repo_root: Path | None = None,
) -> Path | None:
    if not llm_usage_logging_enabled():
        return None

    if estimated_usd is None and provider == "gemini" and kind == "api_call":
        estimated_usd = estimate_gemini_cost_usd(
            model,
            prompt_tokens=prompt_tokens,
            candidates_tokens=candidates_tokens,
        )

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "recorded_at": datetime.now(tz=UTC).isoformat(),
        "provider": provider,
        "model": model,
        "kind": kind,
        "source_path": _source_path_ctx.get(),
        "prompt_tokens": prompt_tokens,
        "candidates_tokens": candidates_tokens,
        "cached_content_tokens": cached_content_tokens,
        "thoughts_tokens": thoughts_tokens,
        "total_tokens": total_tokens,
        "estimated_usd": estimated_usd,
    }

    path = usage_log_path(repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")

    _session_records.append(payload)
    return path


def record_gemini_api_usage(*, model: str, response: object, repo_root: Path | None = None) -> None:
    usage = extract_gemini_usage_metadata(response)
    record_llm_usage(
        provider="gemini",
        model=model,
        kind="api_call",
        prompt_tokens=usage.get("prompt_tokens", 0),
        candidates_tokens=usage.get("candidates_tokens", 0),
        cached_content_tokens=usage.get("cached_content_tokens", 0),
        thoughts_tokens=usage.get("thoughts_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        repo_root=repo_root,
    )


def record_gemini_cache_hit(*, model: str, repo_root: Path | None = None) -> None:
    record_llm_usage(
        provider="gemini",
        model=model,
        kind="cache_hit",
        repo_root=repo_root,
    )


def _pricing_for_model(model: str) -> tuple[float, float] | None:
    normalized = model.lower()
    if normalized in _GEMINI_USD_PER_MILLION:
        return _GEMINI_USD_PER_MILLION[normalized]
    for key, rates in _GEMINI_USD_PER_MILLION.items():
        if normalized.startswith(key):
            return rates
    return None


def _int_field(record: dict[str, object], key: str) -> int:
    return _coerce_int(record.get(key))


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0

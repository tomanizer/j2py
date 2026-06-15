"""Tests for LLM usage logging."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from j2py.llm import usage as usage_mod


@pytest.fixture(autouse=True)
def _reset_usage_session() -> None:
    usage_mod.begin_usage_session()
    yield
    usage_mod.begin_usage_session()


def test_extract_gemini_usage_metadata_reads_token_counts() -> None:
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=50,
            cached_content_token_count=0,
            thoughts_token_count=0,
            total_token_count=150,
        ),
    )
    assert usage_mod.extract_gemini_usage_metadata(response) == {
        "prompt_tokens": 100,
        "candidates_tokens": 50,
        "cached_content_tokens": 0,
        "thoughts_tokens": 0,
        "total_tokens": 150,
    }


def test_estimate_gemini_cost_usd_for_known_model() -> None:
    cost = usage_mod.estimate_gemini_cost_usd(
        "gemini-3.5-flash",
        prompt_tokens=1_000_000,
        candidates_tokens=0,
    )
    assert cost == pytest.approx(0.075)


def test_record_llm_usage_appends_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("J2PY_LLM_USAGE_PATH", str(log_path))
    token = usage_mod.bind_usage_source_path("/abs/Foo.java")

    try:
        written = usage_mod.record_llm_usage(
            provider="gemini",
            model="gemini-3.5-flash",
            kind="api_call",
            prompt_tokens=120,
            candidates_tokens=80,
            total_tokens=200,
        )
    finally:
        usage_mod.reset_usage_source_path(token)

    assert written == log_path
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["provider"] == "gemini"
    assert payload["kind"] == "api_call"
    assert payload["source_path"] == "/abs/Foo.java"
    assert payload["prompt_tokens"] == 120
    assert payload["estimated_usd"] == pytest.approx(0.000033)


def test_record_gemini_cache_hit_zero_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("J2PY_LLM_USAGE_PATH", str(log_path))

    usage_mod.record_gemini_cache_hit(model="gemini-3.5-flash")

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["kind"] == "cache_hit"
    assert payload["total_tokens"] == 0
    assert payload["estimated_usd"] is None


def test_summarize_usage_records_splits_api_and_cache() -> None:
    records = [
        {
            "kind": "api_call",
            "prompt_tokens": 100,
            "candidates_tokens": 40,
            "total_tokens": 140,
            "estimated_usd": 0.01,
        },
        {"kind": "cache_hit"},
        {
            "kind": "api_call",
            "prompt_tokens": 50,
            "candidates_tokens": 10,
            "total_tokens": 60,
            "estimated_usd": 0.005,
        },
    ]
    totals = usage_mod.summarize_usage_records(records)
    assert totals.api_calls == 2
    assert totals.cache_hits == 1
    assert totals.prompt_tokens == 150
    assert totals.candidates_tokens == 50
    assert totals.total_tokens == 200
    assert totals.estimated_usd == pytest.approx(0.015)


def test_llm_usage_logging_can_be_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setenv("J2PY_LLM_USAGE_PATH", str(log_path))
    monkeypatch.setenv("J2PY_LLM_USAGE", "0")

    assert (
        usage_mod.record_llm_usage(
            provider="gemini",
            model="gemini-3.5-flash",
            kind="api_call",
            prompt_tokens=10,
            candidates_tokens=5,
            total_tokens=15,
        )
        is None
    )
    assert not log_path.exists()

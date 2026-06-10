"""Tests for the Anthropic client wrapper without live API calls."""

from types import SimpleNamespace
from typing import Any

import anthropic
import pytest

import j2py.llm.client as client_mod


class FakeCache:
    def __init__(self, cached: str | None = None) -> None:
        self.cached = cached
        self.written: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.cached

    def __setitem__(self, key: str, value: str) -> None:
        self.written[key] = value


def test_translate_with_llm_returns_cached_value(monkeypatch) -> None:
    monkeypatch.setattr(client_mod, "_cache", FakeCache("cached python"))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        model="claude-test",
    )

    assert result == "cached python"


def test_translate_with_llm_calls_client_and_writes_cache(monkeypatch) -> None:
    cache = FakeCache()

    class Messages:
        def create(self, **kwargs: Any) -> SimpleNamespace:
            assert kwargs["model"] == "claude-test"
            return SimpleNamespace(
                content=[anthropic.types.TextBlock(type="text", text="translated python")],
            )

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        model="claude-test",
    )

    assert result == "translated python"
    assert list(cache.written.values()) == ["translated python"]


def test_get_client_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(client_mod, "_client", None)

    try:
        client_mod.get_client()
    except RuntimeError as exc:
        assert "ANTHROPIC_API_KEY" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected missing API key failure")


def test_translate_with_llm_cache_key_includes_config_fingerprint(monkeypatch) -> None:
    cache = FakeCache()

    class Messages:
        def create(self, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                content=[anthropic.types.TextBlock(type="text", text="translated python")],
            )

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        config_fingerprint="one",
        model="claude-test",
    )
    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        config_fingerprint="two",
        model="claude-test",
    )

    assert len(cache.written) == 2


def test_translate_with_llm_cache_key_includes_validation_feedback(monkeypatch) -> None:
    cache = FakeCache()

    class Messages:
        def create(self, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                content=[anthropic.types.TextBlock(type="text", text="translated python")],
            )

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        validation_feedback="SyntaxError: first",
        model="claude-test",
    )
    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        validation_feedback="SyntaxError: second",
        model="claude-test",
    )

    assert len(cache.written) == 2


def test_translate_with_llm_retries_transient_client_failure(monkeypatch) -> None:
    cache = FakeCache()
    calls = {"count": 0}

    class Messages:
        def create(self, **kwargs: Any) -> SimpleNamespace:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient")
            return SimpleNamespace(
                content=[anthropic.types.TextBlock(type="text", text="translated after retry")],
            )

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        model="claude-test",
        use_cache=False,
    )

    assert result == "translated after retry"
    assert calls["count"] == 2


@pytest.mark.parametrize(
    "raw,expected",
    [
        # plain python fence
        ("```python\nclass A:\n    pass\n```", "class A:\n    pass\n"),
        # bare fence
        ("```\nclass A:\n    pass\n```", "class A:\n    pass\n"),
        # no fence — passthrough
        ("class A:\n    pass\n", "class A:\n    pass\n"),
        # fence with trailing whitespace
        ("```python\nclass A:\n    pass\n```\n", "class A:\n    pass\n"),
    ],
)
def test_strip_fences(raw: str, expected: str) -> None:
    assert client_mod._strip_fences(raw) == expected


def test_translate_with_llm_strips_fenced_response(monkeypatch: Any) -> None:
    cache = FakeCache()

    class Messages:
        def create(self, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                content=[
                    anthropic.types.TextBlock(
                        type="text", text="```python\ntranslated python\n```"
                    )
                ],
            )

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        model="claude-test",
    )

    assert result == "translated python\n"
    assert list(cache.written.values()) == ["translated python\n"]

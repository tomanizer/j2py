"""Tests for LLM client wrappers without live API calls."""

import sys
from types import ModuleType, SimpleNamespace
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


class FakeStream:
    """Context-manager stand-in for ``client.messages.stream(...)``."""

    def __init__(self, message: Any) -> None:
        self._message = message

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get_final_message(self) -> Any:
        return self._message


class FakeGenerateContentConfig:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _message(text: str = "translated python", *, stop_reason: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[anthropic.types.TextBlock(type="text", text=text)],
    )


def _install_fake_google_genai_types(monkeypatch: pytest.MonkeyPatch) -> None:
    google_mod = ModuleType("google")
    genai_mod = ModuleType("google.genai")
    genai_types_mod = ModuleType("google.genai.types")
    genai_types_mod.GenerateContentConfig = FakeGenerateContentConfig  # type: ignore[attr-defined]
    genai_mod.types = genai_types_mod  # type: ignore[attr-defined]
    google_mod.genai = genai_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types_mod)


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
        def stream(self, **kwargs: Any) -> FakeStream:
            assert kwargs["model"] == "claude-test"
            assert kwargs["system"][0]["cache_control"] == {
                "type": "ephemeral",
            }
            return FakeStream(_message("translated python"))

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


def test_get_gemini_client_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(client_mod, "_gemini_client", None)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        client_mod.get_gemini_client()


def test_resolve_model_defaults_by_provider() -> None:
    assert client_mod.resolve_model("anthropic", None) == "claude-sonnet-4-6"
    assert client_mod.resolve_model("gemini", None) == "gemini-3.5-flash"
    assert client_mod.resolve_model("gemini", "custom-gemini") == "custom-gemini"


def test_translate_with_llm_cache_key_includes_config_fingerprint(monkeypatch) -> None:
    cache = FakeCache()

    class Messages:
        def stream(self, **kwargs: Any) -> FakeStream:
            return FakeStream(_message())

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


def test_translate_with_llm_cache_key_includes_provider(monkeypatch) -> None:
    cache = FakeCache()

    class Messages:
        def stream(self, **kwargs: Any) -> FakeStream:
            return FakeStream(_message("anthropic python"))

    class Models:
        def generate_content(self, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(text="gemini python", candidates=[])

    _install_fake_google_genai_types(monkeypatch)
    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))
    monkeypatch.setattr(client_mod, "get_gemini_client", lambda: SimpleNamespace(models=Models()))

    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        model="same-model",
        provider="anthropic",
    )
    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        model="same-model",
        provider="gemini",
    )

    assert sorted(cache.written.values()) == ["anthropic python", "gemini python"]


def test_translate_with_llm_cache_key_includes_validation_feedback(monkeypatch) -> None:
    cache = FakeCache()

    class Messages:
        def stream(self, **kwargs: Any) -> FakeStream:
            return FakeStream(_message())

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


def test_translate_with_llm_cache_key_includes_previous_python(monkeypatch) -> None:
    cache = FakeCache()

    class Messages:
        def stream(self, **kwargs: Any) -> FakeStream:
            return FakeStream(_message())

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        validation_feedback="SyntaxError: repair",
        previous_python="def broken_one(:\n",
        model="claude-test",
    )
    client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        validation_feedback="SyntaxError: repair",
        previous_python="def broken_two(:\n",
        model="claude-test",
    )

    assert len(cache.written) == 2


def test_translate_with_llm_retries_transient_client_failure(monkeypatch) -> None:
    cache = FakeCache()
    calls = {"count": 0}

    class Messages:
        def stream(self, **kwargs: Any) -> FakeStream:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient")
            return FakeStream(_message("translated after retry"))

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


def test_translate_with_llm_calls_gemini_and_writes_cache(monkeypatch) -> None:
    cache = FakeCache()
    observed: dict[str, Any] = {}

    class Models:
        def generate_content(self, **kwargs: Any) -> SimpleNamespace:
            observed.update(kwargs)
            return SimpleNamespace(text="translated python", candidates=[])

    _install_fake_google_genai_types(monkeypatch)
    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_gemini_client", lambda: SimpleNamespace(models=Models()))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        provider="gemini",
        model="gemini-test",
    )

    assert result == "translated python"
    assert observed["model"] == "gemini-test"
    assert "class A {}" in observed["contents"]
    assert "class A:" in observed["contents"]
    assert observed["config"].kwargs["max_output_tokens"] == client_mod.MAX_OUTPUT_TOKENS
    assert "expert Java-to-Python translator" in observed["config"].kwargs["system_instruction"]
    assert list(cache.written.values()) == ["translated python"]


def test_translate_with_llm_strips_gemini_fenced_response(monkeypatch: Any) -> None:
    cache = FakeCache()

    class Models:
        def generate_content(self, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(text="```python\ntranslated python\n```", candidates=[])

    _install_fake_google_genai_types(monkeypatch)
    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_gemini_client", lambda: SimpleNamespace(models=Models()))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        provider="gemini",
        model="gemini-test",
    )

    assert result == "translated python\n"
    assert list(cache.written.values()) == ["translated python\n"]


def test_translate_with_llm_retries_transient_gemini_failure(monkeypatch) -> None:
    calls = {"count": 0}

    class Models:
        def generate_content(self, **kwargs: Any) -> SimpleNamespace:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("transient")
            return SimpleNamespace(text="translated after retry", candidates=[])

    _install_fake_google_genai_types(monkeypatch)
    monkeypatch.setattr(client_mod, "get_gemini_client", lambda: SimpleNamespace(models=Models()))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        provider="gemini",
        model="gemini-test",
        use_cache=False,
    )

    assert result == "translated after retry"
    assert calls["count"] == 2


def test_translate_with_llm_raises_on_truncation(monkeypatch) -> None:
    cache = FakeCache()
    calls = {"count": 0}

    class Messages:
        def stream(self, **kwargs: Any) -> FakeStream:
            calls["count"] += 1
            return FakeStream(_message("truncated parti", stop_reason="max_tokens"))

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    with pytest.raises(client_mod.LLMTruncationError):
        client_mod.translate_with_llm(
            java_source="class A {}",
            partial_python="class A:\n    pass\n",
            model="claude-test",
            use_cache=True,
        )

    # truncation is not retried (deterministic) and the partial text is never cached
    assert calls["count"] == 1
    assert cache.written == {}


def test_translate_with_llm_raises_on_gemini_truncation(monkeypatch) -> None:
    cache = FakeCache()
    calls = {"count": 0}

    class Models:
        def generate_content(self, **kwargs: Any) -> SimpleNamespace:
            calls["count"] += 1
            reason = SimpleNamespace(name="MAX_TOKENS")
            return SimpleNamespace(
                text="truncated parti",
                candidates=[SimpleNamespace(finish_reason=reason)],
            )

    _install_fake_google_genai_types(monkeypatch)
    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_gemini_client", lambda: SimpleNamespace(models=Models()))

    with pytest.raises(client_mod.LLMTruncationError):
        client_mod.translate_with_llm(
            java_source="class A {}",
            partial_python="class A:\n    pass\n",
            provider="gemini",
            model="gemini-test",
            use_cache=True,
        )

    assert calls["count"] == 1
    assert cache.written == {}


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
        def stream(self, **kwargs: Any) -> FakeStream:
            return FakeStream(_message("```python\ntranslated python\n```"))

    monkeypatch.setattr(client_mod, "_cache", cache)
    monkeypatch.setattr(client_mod, "get_client", lambda: SimpleNamespace(messages=Messages()))

    result = client_mod.translate_with_llm(
        java_source="class A {}",
        partial_python="class A:\n    pass\n",
        model="claude-test",
    )

    assert result == "translated python\n"
    assert list(cache.written.values()) == ["translated python\n"]

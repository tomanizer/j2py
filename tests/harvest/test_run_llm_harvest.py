"""Tests for the LLM harvest runner CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import scripts.harvest.run_llm_harvest as runner
from j2py.config.loader import ConfigLoader
from j2py.pipeline import TranslationResult


def test_run_llm_harvest_passes_selected_provider_and_model(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Probe.java"
    source.write_text("public class Probe {}", encoding="utf-8")
    observed: dict[str, object] = {}

    def fake_translate_file(path: Path, **kwargs: object) -> TranslationResult:
        observed["path"] = path
        observed.update(kwargs)
        return TranslationResult(
            source_path=path,
            python_source="class Probe:\n    pass\n",
            confidence=1.0,
            used_llm=False,
        )

    monkeypatch.setenv("J2PY_LLM_HARVEST", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        runner,
        "HARVEST_PRESETS",
        {"local": (source,)},
    )
    monkeypatch.setattr(runner, "translate_file", fake_translate_file)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_llm_harvest.py",
            "--preset",
            "local",
            "--llm-provider",
            "gemini",
            "--model",
            "gemini-test",
        ],
    )

    assert runner.main() == 0
    assert observed["path"] == source
    assert observed["cfg"] == ConfigLoader().add_defaults().build()
    assert observed["use_llm"] is True
    assert observed["llm_provider"] == "gemini"
    assert observed["model"] == "gemini-test"
    assert observed["validate"] is True

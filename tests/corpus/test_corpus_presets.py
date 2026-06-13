"""Tests for multi-corpus preset definitions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_presets() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "corpus" / "corpus_presets.py"
    spec = importlib.util.spec_from_file_location("corpus_presets", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


presets = _load_presets()


def test_list_preset_names_includes_spring_and_guava() -> None:
    names = presets.list_preset_names()
    assert "spring-dense" in names
    assert "guava-dense" in names
    assert names == sorted(names)


def test_apply_preset_uses_sampling_parameters() -> None:
    preset = presets.get_preset("spring-dense")
    resolved = presets.apply_preset(
        preset,
        {
            "repo": None,
            "remote": None,
            "ref": None,
            "modules": None,
            "limit": None,
            "strategy": None,
            "max_loc": None,
            "min_constructs": None,
            "include_constructs": None,
            "include_tests": None,
            "baseline": None,
            "json_out": None,
            "csv_out": None,
        },
    )

    assert resolved["preset"] == "spring-dense"
    assert resolved["strategy"] == "density"
    assert resolved["max_loc"] == 250
    assert resolved["min_constructs"] == 5
    assert resolved["include_constructs"] is True
    assert resolved["baseline"] == preset.baseline


def test_apply_preset_allows_explicit_limit_override() -> None:
    preset = presets.get_preset("guava-dense")
    resolved = presets.apply_preset(
        preset,
        {
            "repo": None,
            "remote": None,
            "ref": None,
            "modules": None,
            "limit": 25,
            "strategy": None,
            "max_loc": None,
            "min_constructs": None,
            "include_constructs": None,
            "include_tests": None,
            "baseline": None,
            "json_out": None,
            "csv_out": None,
        },
    )

    assert resolved["limit"] == 25
    assert resolved["strategy"] == "density"
    assert "guava/src/com/google/common/collect" in resolved["modules"]


def test_corpus_checkout_root_defaults_to_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("J2PY_CORPUS_ROOT", raising=False)
    assert presets.corpus_checkout_root() == presets.REPO_ROOT / ".corpus"


def test_corpus_checkout_root_honors_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("J2PY_CORPUS_ROOT", str(tmp_path))
    assert presets.corpus_checkout_root() == tmp_path / ".corpus"


def test_corpus_checkout_root_honors_env_relative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("J2PY_CORPUS_ROOT", "relative_path")
    expected = (presets.REPO_ROOT / "relative_path").resolve() / ".corpus"
    assert presets.corpus_checkout_root() == expected


def test_repo_path_uses_corpus_checkout_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("J2PY_CORPUS_ROOT", str(tmp_path))
    preset = presets.get_preset("guava-dense")
    assert preset.repo_path == tmp_path / ".corpus" / "guava"


def test_clone_preset_names_are_unique_checkouts() -> None:
    checkout_dirs = {presets.get_preset(name).checkout_dir for name in presets.CLONE_PRESET_NAMES}
    assert checkout_dirs == {
        "spring-framework",
        "guava",
        "commons-lang",
        "jackson-databind",
        "caffeine",
    }

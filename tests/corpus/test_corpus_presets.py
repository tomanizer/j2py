"""Tests for multi-corpus preset definitions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


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

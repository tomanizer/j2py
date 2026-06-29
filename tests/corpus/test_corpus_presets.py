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
    assert "spring-app-dense" in names
    assert "petclinic" in names
    assert "openjdk-java-base" in names
    assert "guava-dense" in names
    assert "jsemver" in names
    assert names == sorted(names)


def test_jsemver_preset_pins_case_study_library() -> None:
    preset = presets.get_preset("jsemver")

    assert preset.remote == "https://github.com/zafarkhaja/jsemver.git"
    assert preset.ref == "v0.10.2"
    assert preset.checkout_dir == "jsemver"
    assert preset.modules == ("src/main/java",)
    assert preset.baseline.name == "jsemver-baseline.json"


def test_spring_app_dense_preset_targets_application_samples() -> None:
    preset = presets.get_preset("spring-app-dense")
    assert preset.checkout_dir == "spring-framework"
    assert preset.include_constructs is True
    assert preset.require_annotations
    assert preset.min_annotation_hits == 1
    assert any("context/index/sample" in module for module in preset.modules)
    assert preset.include_path_prefixes == (
        "spring-context-indexer/src/test/java/org/springframework/context/index/sample/",
    )


def test_petclinic_preset_targets_official_reference_application() -> None:
    preset = presets.get_preset("petclinic")

    assert preset.remote == "https://github.com/spring-projects/spring-petclinic.git"
    assert preset.ref == "a2c2ef994340d3970eb6db51247456a51bb161f8"
    assert preset.checkout_dir == "spring-petclinic"
    assert preset.modules == ("src/main/java",)
    assert preset.baseline.name == "petclinic-baseline.json"
    assert preset.include_constructs is False
    assert preset.min_loc == 0
    assert preset.min_constructs == 0


def test_openjdk_java_base_preset_is_manual_external_scoreboard() -> None:
    preset = presets.get_preset("openjdk-java-base")

    assert preset.remote == "https://github.com/openjdk/jdk.git"
    assert preset.ref == "jdk-21+35"
    assert preset.checkout_dir == "openjdk"
    assert preset.limit == 6
    assert preset.include_constructs is False
    assert preset.baseline.name == "openjdk-java-base-baseline.json"
    assert preset.include_path_prefixes == (
        "src/java.base/share/classes/java/util/Objects.java",
        "src/java.base/share/classes/java/util/Optional.java",
        "src/java.base/share/classes/java/util/StringJoiner.java",
        "src/java.base/share/classes/java/util/Comparator.java",
        "src/java.base/share/classes/java/nio/file/Path.java",
        "src/java.base/share/classes/java/time/Duration.java",
    )


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
    assert resolved["max_loc"] == 1000
    assert resolved["min_loc"] == 20
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
    assert resolved["exclude_paths"] == [
        "guava/src/com/google/common/base/Platform.java",
    ]
    assert "guava/src/com/google/common/collect" in resolved["modules"]


def test_guava_dense_excludes_platform_java_parser_gap() -> None:
    preset = presets.get_preset("guava-dense")
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
            "exclude_paths": None,
            "baseline": None,
            "json_out": None,
            "csv_out": None,
        },
    )

    assert resolved["exclude_paths"] == [
        "guava/src/com/google/common/base/Platform.java",
    ]


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
        "spring-petclinic",
        "guava",
        "commons-lang",
        "jackson-databind",
        "caffeine",
    }
    assert "openjdk" not in checkout_dirs

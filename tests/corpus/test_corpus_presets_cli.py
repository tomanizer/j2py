"""Additional tests for preset-aware corpus CLI resolution."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "corpus" / "translate_corpus.py"
    spec = importlib.util.spec_from_file_location("translate_corpus_presets", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


corpus = _load_script()


def test_resolve_args_spring_dense_preset_matches_dense_scoreboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["translate_corpus.py", "--preset", "spring-dense"],
    )
    args = corpus.resolve_args(corpus.parse_args())

    assert args.preset_name == "spring-dense"
    assert args.strategy == "density"
    assert args.max_loc == 1000
    assert args.min_loc == 20
    assert args.min_constructs == 5
    assert args.include_constructs is True
    assert args.limit == 200
    assert args.modules == [
        "spring-core/src/main/java",
        "spring-beans/src/main/java",
        "spring-beans/src/main/java/org/springframework/beans/factory/annotation",
        "spring-beans/src/main/java/org/springframework/beans/factory/config",
        "spring-context/src/main/java/org/springframework/context/annotation",
        "spring-context/src/main/java/org/springframework/stereotype",
    ]
    assert args.include_path_prefixes == (
        "spring-beans/src/main/java/org/springframework/beans/factory/annotation/",
        "spring-context/src/main/java/org/springframework/stereotype/",
    )
    assert args.skip_package_info is True
    assert args.baseline.name == "spring-dense-baseline.json"


def test_list_presets_exits_zero(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["translate_corpus.py", "--list-presets"])
    exit_code = corpus.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "spring-dense" in captured.out
    assert "guava-dense" in captured.out


def test_legacy_spring_named_entrypoint_delegates_to_generic_runner(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper_path = Path(__file__).parents[2] / "scripts" / "corpus" / "translate_spring_sample.py"
    spec = importlib.util.spec_from_file_location("translate_spring_sample_wrapper", wrapper_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(sys, "argv", ["translate_spring_sample.py", "--list-presets"])
    assert module.main() == 0
    captured = capsys.readouterr()
    assert "guava-dense" in captured.out
    assert "spring-dense" in captured.out

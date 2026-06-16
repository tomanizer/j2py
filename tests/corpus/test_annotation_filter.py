"""Tests for enterprise annotation pre-filtering in the corpus harness."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_module(name: str, filename: str) -> ModuleType:
    script_dir = Path(__file__).parents[2] / "scripts" / "corpus"
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    path = script_dir / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


annotation_filter = _load_module("annotation_filter", "annotation_filter.py")
corpus = _load_module("translate_corpus_filter", "translate_corpus.py")


def test_annotation_hits_matches_simple_and_scoped_names() -> None:
    text = """
    @RestController
    @org.springframework.web.bind.annotation.GetMapping("/x")
    public class Demo {}
    """
    hits = annotation_filter.annotation_hits(text, ("RestController", "GetMapping"))
    assert hits["RestController"] == 1
    assert hits["GetMapping"] == 1


def test_passes_annotation_filter_respects_min_hits() -> None:
    text = "@Service\nclass S {}"
    assert annotation_filter.passes_annotation_filter(
        text,
        require_annotations=("Service", "Repository"),
        min_annotation_hits=1,
    )
    assert not annotation_filter.passes_annotation_filter(
        text,
        require_annotations=("Service", "Repository"),
        min_annotation_hits=2,
    )


def test_collect_java_files_require_annotations(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    app_dir = repo / "app" / "src" / "main" / "java" / "example"
    app_dir.mkdir(parents=True)
    annotated = app_dir / "Service.java"
    plain = app_dir / "Plain.java"
    annotated.write_text("package example;\n@Service\nclass Service { void run() { } }\n")
    plain.write_text("package example;\nclass Plain { void run() { } }\n")

    selected = corpus.collect_java_files(
        repo,
        modules=("app/src/main/java",),
        limit=10,
        include_tests=False,
        strategy="lexical",
        require_annotations=("Service",),
        min_annotation_hits=1,
    )

    assert annotated in selected
    assert plain not in selected


def test_collect_java_files_priority_paths_bypass_annotation_filter(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    pinned_dir = repo / "module" / "src" / "main" / "java" / "pinned"
    other_dir = repo / "module" / "src" / "main" / "java" / "other"
    pinned_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    pinned = pinned_dir / "Pinned.java"
    other = other_dir / "Other.java"
    pinned.write_text("package pinned;\nclass Pinned { }\n")
    other.write_text("package other;\nclass Other { }\n")

    selected = corpus.collect_java_files(
        repo,
        modules=("module/src/main/java",),
        limit=1,
        include_tests=False,
        strategy="density",
        require_annotations=("Service",),
        min_annotation_hits=1,
        include_path_prefixes=("module/src/main/java/pinned/",),
    )

    assert pinned in selected
    assert other not in selected

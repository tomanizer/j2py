"""Roadmap and graduated target tests for Java-to-Python translation features."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.conftest import CORPUS_CONSTRUCT_FIXTURES, TARGET_FIXTURES

CFG = ConfigLoader().add_defaults().build()


@dataclass(frozen=True)
class TranslationTarget:
    fixture: str
    tracking: str
    reason: str
    expected_fragments: tuple[str, ...] = ()
    forbidden_fragments: tuple[str, ...] = (
        "TODO(j2py): unsupported",
        "__j2py_todo__",
    )
    fixture_root: Path = field(default=TARGET_FIXTURES)

    @property
    def path(self) -> Path:
        return self.fixture_root / self.fixture


FUTURE_TARGETS: tuple[TranslationTarget, ...] = ()
GRADUATED_TARGET_FIXTURES = tuple(
    path.name
    for path in sorted(TARGET_FIXTURES.glob("*.java"))
    if path.name not in {target.fixture for target in FUTURE_TARGETS}
)
CORPUS_GRADUATED_FIXTURES = tuple(
    path.name
    for path in sorted(CORPUS_CONSTRUCT_FIXTURES.glob("*.java"))
    if path.name not in {target.fixture for target in FUTURE_TARGETS}
)


def test_target_java_fixtures_parse_without_errors() -> None:
    """Target fixtures must be valid Java even when their translation target is xfail."""
    for path in sorted(TARGET_FIXTURES.glob("*.java")):
        parsed = parse_file(path)
        assert not parsed.has_errors, path


@pytest.mark.parametrize(
    "fixture_name",
    GRADUATED_TARGET_FIXTURES,
)
def test_graduated_target_fixture_translates_cleanly(fixture_name: str) -> None:
    """Previously-targeted fixtures now translate deterministically and stay green."""
    parsed = parse_file(TARGET_FIXTURES / fixture_name)
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "TODO(j2py): unsupported" not in result.source
    assert "__j2py_todo__" not in result.source


def test_corpus_construct_fixtures_parse_without_errors() -> None:
    """Corpus construct fixtures must be valid Java even when their translation is xfail."""
    for path in sorted(CORPUS_CONSTRUCT_FIXTURES.glob("*.java")):
        parsed = parse_file(path)
        assert not parsed.has_errors, path


@pytest.mark.parametrize(
    "fixture_name",
    CORPUS_GRADUATED_FIXTURES,
)
def test_graduated_corpus_construct_translates_cleanly(fixture_name: str) -> None:
    """Corpus mini-corpus constructs that now translate deterministically stay green."""
    parsed = parse_file(CORPUS_CONSTRUCT_FIXTURES / fixture_name)
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "TODO(j2py): unsupported" not in result.source
    assert "__j2py_todo__" not in result.source


if FUTURE_TARGETS:

    @pytest.mark.target_translation
    @pytest.mark.parametrize(
        "target",
        [
            pytest.param(
                target,
                id=f"{target.path.stem}-{target.tracking}",
                marks=pytest.mark.xfail(reason=target.reason, strict=True),
            )
            for target in FUTURE_TARGETS
        ],
    )
    def test_future_translation_target_output(target: TranslationTarget) -> None:
        """Future translation contracts for roadmap issues.

        These are strict xfail targets. When one starts passing, graduate the behavior into
        the normal fixture suite and remove or update the target.
        """
        parsed = parse_file(target.path)
        result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

        ast.parse(result.source)
        assert result.coverage == 1.0
        for fragment in target.expected_fragments:
            assert fragment in result.source
        for fragment in target.forbidden_fragments:
            assert fragment not in result.source

"""Roadmap target tests for unsupported Java-to-Python translation features."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics

TARGET_FIXTURES = Path(__file__).parent.parent / "fixtures" / "java" / "targets"
CFG = ConfigLoader().add_defaults().build()


@dataclass(frozen=True)
class TranslationTarget:
    fixture: str
    issue: int
    reason: str
    expected_fragments: tuple[str, ...]
    forbidden_fragments: tuple[str, ...] = (
        "TODO(j2py): unsupported",
        "__j2py_todo__",
    )

    @property
    def path(self) -> Path:
        return TARGET_FIXTURES / self.fixture


TARGETS: tuple[TranslationTarget, ...] = (
    TranslationTarget(
        fixture="CommentsAnnotations.java",
        issue=7,
        reason="comments and annotations are not yet preserved or elided cleanly",
        expected_fragments=(
            "# Build-time hint registrar.",
            "def register_reflection_hints(self, hints: RuntimeHints) -> None:",
            "hints.reflection().register_type(CommentsAnnotations)",
        ),
        forbidden_fragments=(
            "TODO(j2py): unsupported class member block_comment",
            "TODO(j2py): unsupported class member line_comment",
            "__j2py_todo__",
        ),
    ),
    TranslationTarget(
        fixture="ControlFlow.java",
        issue=4,
        reason="if/else and classic loop translation are not implemented",
        expected_fragments=(
            "if value > 10:",
            "elif value == 10:",
            "else:",
            "for i in range(0, limit):",
            "while total < 100:",
            "while True:",
        ),
    ),
    TranslationTarget(
        fixture="Exceptions.java",
        issue=2,
        reason="try/catch/finally and throw translation are not implemented",
        expected_fragments=(
            "try:",
            "except OSError as ex:",
            'raise RuntimeError("Failed to read")',
            "finally:",
            "resource.close()",
        ),
    ),
    TranslationTarget(
        fixture="Expressions.java",
        issue=6,
        reason="ternary, unary, class literal, and array expression support is incomplete",
        expected_fragments=(
            "fallback = Expressions",
            "return type_ if type_ is not None and len(values) > 0 else fallback",
            'return values[0] if values[0] else "default"',
        ),
    ),
    TranslationTarget(
        fixture="Functional.java",
        issue=6,
        reason="lambdas, method references, and stream pipelines are not implemented",
        expected_fragments=(
            "return [",
            "type_.get_name()",
            "for type_ in types",
            "if type_.get_name()",
        ),
    ),
    TranslationTarget(
        fixture="NestedTypes.java",
        issue=9,
        reason="nested declarations, interfaces, enums, and records are not implemented",
        expected_fragments=(
            "class Writer(Protocol):",
            "class Mode(Enum):",
            "FAST =",
            "@dataclass",
            "class Entry:",
            "class Builder:",
        ),
    ),
    TranslationTarget(
        fixture="Overloads.java",
        issue=8,
        reason="constructor chaining and overload dispatch are not implemented",
        expected_fragments=(
            "@overload",
            "def __init__(self, name: str = \"default\") -> None:",
            "self.name = name",
            "def add(self, left: str | int, right: str | int) -> str | int:",
        ),
        forbidden_fragments=(
            "TODO(j2py): overloaded method __init__ requires LLM completion",
            "TODO(j2py): overloaded method add requires LLM completion",
            "__j2py_todo__",
        ),
    ),
)


def test_target_java_fixtures_parse_without_errors() -> None:
    """Target fixtures must be valid Java even when their translation target is xfail."""
    for path in sorted(TARGET_FIXTURES.glob("*.java")):
        parsed = parse_file(path)
        assert not parsed.has_errors, path


@pytest.mark.target_translation
@pytest.mark.parametrize(
    "target",
    [
        pytest.param(
            target,
            id=f"{target.path.stem}-issue-{target.issue}",
            marks=pytest.mark.xfail(reason=target.reason, strict=True),
        )
        for target in TARGETS
    ],
)
def test_translation_target_output(target: TranslationTarget) -> None:
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

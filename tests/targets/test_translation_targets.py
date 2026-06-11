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
    tracking: str
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
        fixture="CastExpression.java",
        tracking="corpus-cast",
        reason="corpus backlog: translate cast expressions without TODOs",
        expected_fragments=("return value.get_canonical_name()",),
    ),
    TranslationTarget(
        fixture="InstanceofExpression.java",
        tracking="corpus-instanceof",
        reason="corpus backlog: translate instanceof pattern variables",
        expected_fragments=("isinstance(value, str)", "text = value", "return text.strip()"),
    ),
    TranslationTarget(
        fixture="BitwiseOperators.java",
        tracking="corpus-bitwise",
        reason="corpus backlog: translate bitwise and shift operators",
        expected_fragments=("left & right", "left ^ right", "value << 2", "value >> 1"),
    ),
    TranslationTarget(
        fixture="CompoundAssignment.java",
        tracking="corpus-compound-assignment",
        reason="corpus backlog: translate bitwise compound assignments",
        expected_fragments=("value &= mask", "value |= flag"),
    ),
    TranslationTarget(
        fixture="ArrayCreation.java",
        tracking="corpus-array-creation",
        reason="corpus backlog: translate sized array creation",
        expected_fragments=("return [0] * size",),
    ),
    TranslationTarget(
        fixture="TryWithResources.java",
        tracking="corpus-try-with-resources",
        reason="corpus backlog: translate try-with-resources",
        expected_fragments=("with factory.open() as resource:", "return resource.read()"),
    ),
    TranslationTarget(
        fixture="StaticAndSynchronized.java",
        tracking="corpus-static-synchronized",
        reason="corpus backlog: translate static initializers and synchronized blocks",
        expected_fragments=("initialize()", "with", "run()"),
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
            id=f"{target.path.stem}-{target.tracking}",
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

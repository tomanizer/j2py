"""End-to-end case-study harness for Guava ``Strings`` (issue #658).

The harness translates the scoped Guava source with the deterministic rule layer only
(``use_llm=False``), loads the translated class with minimal Guava/JDK stubs, and keeps
generated-output residual patches separate from those external dependency stubs.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path

import j2py.translate.runtime.j2py_runtime as _j2py_runtime_module
from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_file
from tests.equivalence.harness import (
    JavaCharSequence,
    JavaString,
    guava_strings_character_stub,
    guava_strings_platform_stub,
    install_stub_class,
)

sys.modules.setdefault("j2py_runtime", _j2py_runtime_module)

JAVA_DIR = Path(__file__).parent.parent / "fixtures" / "case_study" / "guava_base_strings" / "java"

_CFG = ConfigLoader().add_defaults().build()


@dataclass(frozen=True)
class TranslationMetric:
    file_name: str
    coverage: float
    confidence: float
    semantic_warnings: int
    todos: int


@dataclass(frozen=True)
class ResidualGap:
    gap_id: str
    module: str
    summary: str
    bad: str
    good: str


_RESIDUAL_GAP_PATCHES: tuple[ResidualGap, ...] = ()


class _Logger:
    @staticmethod
    def get_logger(_name: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(log=lambda *_args: None)


def _install_external_stubs() -> tuple[str, ...]:
    install_stub_class("java.util.logging.Logger", "Logger", _Logger)
    install_stub_class(
        "com.google.common.base.Platform",
        "Platform",
        guava_strings_platform_stub(),
    )
    install_stub_class(
        "com.google.common.base.Character",
        "Character",
        guava_strings_character_stub(),
    )
    return ("Character", "Logger", "Platform")


def translate_guava_base_strings() -> tuple[str, TranslationMetric]:
    """Return translated ``Strings`` source plus rule-layer metrics."""
    result = translate_file(JAVA_DIR / "Strings.java", cfg=_CFG, use_llm=False, validate=False)
    return result.python_source, TranslationMetric(
        file_name="Strings.java",
        coverage=result.diagnostics.coverage,
        confidence=result.confidence,
        semantic_warnings=result.diagnostics.semantic_warning_count,
        todos=result.python_source.count("TODO(j2py)"),
    )


def _apply_residual_gap_patches(source: str) -> tuple[str, list[str]]:
    applied: list[str] = []
    for gap in _RESIDUAL_GAP_PATCHES:
        if gap.bad not in source:
            raise AssertionError(f"{gap.gap_id} patch target missing from {gap.module}")
        source = source.replace(gap.bad, gap.good)
        applied.append(gap.gap_id)
    return source, applied


def link_guava_base_strings_namespace() -> types.SimpleNamespace:
    """Translate and load the scoped Guava ``Strings`` class."""
    source, metric = translate_guava_base_strings()
    source, applied_gaps = _apply_residual_gap_patches(source)
    external_stubs = _install_external_stubs()

    module = types.ModuleType("guava_base_strings_case_study")
    module.__file__ = "<guava_base_strings_case_study>"
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)  # noqa: S102

    return types.SimpleNamespace(
        Strings=module.Strings,
        JavaCharSequence=JavaCharSequence,
        JavaString=JavaString,
        applied_gaps=applied_gaps,
        external_stubs=external_stubs,
        metrics={"Strings": metric},
    )

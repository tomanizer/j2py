"""End-to-end case-study harness for Apache Commons Text ``CaseUtils`` (issue #657).

The harness translates the scoped Commons Text source with the deterministic rule layer
only (``use_llm=False``), links the translated class into one namespace, and supplies
small external stubs for JDK / commons-lang3 symbols outside the tested library behavior.

Residual translator patches are declared explicitly in ``_RESIDUAL_GAP_PATCHES``. Those
patches are not dependency stubs: each one is a generated-output defect that should become
a rule-layer fix before being removed from the inventory. See
``docs/CASE_STUDY_COMMONS_TEXT_CASEUTILS.md`` for the gap write-ups.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import j2py.translate.runtime.j2py_runtime as _j2py_runtime_module
from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_file

sys.modules.setdefault("j2py_runtime", _j2py_runtime_module)

JAVA_DIR = (
    Path(__file__).parent.parent / "fixtures" / "case_study" / "commons_text_caseutils" / "java"
)

_CFG = ConfigLoader().add_defaults().build()

_LINK_ORDER = ("CaseUtils",)


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


# Generated-output defects in the rule-layer translation of ``CaseUtils``. Each is a real
# translator bug, patched here only so the upstream-derived oracle can run end-to-end.
# CT-1 (String(int[], offset, count) lowering), CT-2 (locale-qualified toLowerCase), and
# CT-3 (String.codePointAt) have all been fixed at the rule layer, so no patches remain.
_RESIDUAL_GAP_PATCHES: tuple[ResidualGap, ...] = ()


class _StringUtils:
    """commons-lang3 StringUtils, scoped to the predicate CaseUtils uses."""

    @staticmethod
    def is_empty(value: str | None) -> bool:
        return not value


class _ArrayUtils:
    """commons-lang3 ArrayUtils, scoped to the predicate CaseUtils uses."""

    @staticmethod
    def is_empty(value: Any) -> bool:
        return value is None or len(value) == 0


class _Character:
    """java.lang.Character statics used by CaseUtils.

    Java models text as UTF-16 code units, so ``charCount`` returns 2 for supplementary
    code points. Python ``str`` is already a sequence of code points, so within this
    translation every element is one code point and ``char_count`` is always 1. The
    delimiter scan therefore advances in code-point space, matching the algorithm.
    """

    @staticmethod
    def char_count(code_point: int) -> int:
        return 1

    @staticmethod
    def to_title_case(code_point: int) -> int:
        return ord(chr(code_point).title()[0])

    @staticmethod
    def code_point_at(seq: Any, index: int) -> int:
        element = seq[index]
        return element if isinstance(element, int) else ord(element)


_EXTERNAL_STUBS: dict[str, Any] = {
    "ArrayUtils": _ArrayUtils,
    "Character": _Character,
    "StringUtils": _StringUtils,
}


def translate_commons_text_caseutils() -> tuple[dict[str, str], dict[str, TranslationMetric]]:
    """Return translated sources and metrics for the scoped Commons Text files."""
    sources: dict[str, str] = {}
    metrics: dict[str, TranslationMetric] = {}
    for name in _LINK_ORDER:
        result = translate_file(JAVA_DIR / f"{name}.java", cfg=_CFG, use_llm=False, validate=False)
        sources[name] = result.python_source
        metrics[name] = TranslationMetric(
            file_name=f"{name}.java",
            coverage=result.diagnostics.coverage,
            confidence=result.confidence,
            semantic_warnings=result.diagnostics.semantic_warning_count,
            todos=result.python_source.count("TODO(j2py)"),
        )
    return sources, metrics


def _strip_external_imports(source: str) -> str:
    kept: list[str] = []
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped == "if TYPE_CHECKING:":
            block: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith("    ") or not lines[index]):
                block.append(lines[index])
                index += 1
            linked_only = all(
                not item.strip()
                or item.strip().startswith(
                    (
                        "from java.",
                        "import java.",
                        "from org.apache.commons.",
                        "import org.apache.commons.",
                    ),
                )
                for item in block
            )
            if linked_only:
                continue
            kept.append(line)
            kept.extend(block)
            continue
        if stripped.startswith(("from java.", "import java.")):
            index += 1
            continue
        if stripped.startswith(("from org.apache.commons.", "import org.apache.commons.")):
            index += 1
            continue
        kept.append(line)
        index += 1
    return "\n".join(kept)


def _apply_residual_gap_patches(name: str, source: str) -> tuple[str, list[str]]:
    applied: list[str] = []
    for gap in _RESIDUAL_GAP_PATCHES:
        if gap.module != name:
            continue
        if gap.bad not in source:
            raise AssertionError(f"{gap.gap_id} patch target missing from {name}")
        source = source.replace(gap.bad, gap.good)
        applied.append(gap.gap_id)
    return source, applied


def link_commons_text_caseutils_namespace() -> types.SimpleNamespace:
    """Translate and link the scoped Commons Text CaseUtils class."""
    sources, metrics = translate_commons_text_caseutils()
    shared: dict[str, Any] = dict(_EXTERNAL_STUBS)
    applied_gaps: list[str] = []

    for name in _LINK_ORDER:
        source, applied = _apply_residual_gap_patches(name, sources[name])
        source = _strip_external_imports(source)
        applied_gaps.extend(applied)
        exec(compile(source, f"<commons_text_caseutils:{name}>", "exec"), shared)  # noqa: S102

    return types.SimpleNamespace(
        CaseUtils=shared["CaseUtils"],
        applied_gaps=applied_gaps,
        metrics=metrics,
        external_stubs=tuple(sorted(_EXTERNAL_STUBS)),
    )

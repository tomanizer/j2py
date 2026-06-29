"""End-to-end case-study harness for java-semver (issues #613 and #654).

Translates the vendored ``com.github.zafarkhaja.semver`` util and ``Version`` / parser
core files with the rule layer only (no LLM), then *links* the translated modules into
shared namespaces so the real translated classes can be exercised by ported upstream
JUnit assertions (``StreamTest`` plus the focused ``VersionTest`` core slice).

This is the first **external** end-to-end conversion case study: jsemver is a third-party
OSS library, not a curated j2py fixture. The goal is to measure — honestly — how far the
deterministic rule layer gets on real library code and to publish the residual gap list.

The harness keeps external scaffolding separate from any residual translator patches:

* ``_EXTERNAL_STUBS`` — JDK/runtime symbols that are *not under test* (for example,
  ``Arrays``). These are scaffolding, exactly like the dependency stubs in
  ``tests/case_study/harness.py`` and ``tests/equivalence/harness.py``.

* ``_RESIDUAL_GAP_PATCHES`` — concrete *translator defects* found in the rule-layer
  output. Each patch is a single, documented source rewrite tagged with a gap id. The
  list of these patches **is** the residual failure list the case study reports: every
  entry is a place where the current rule layer emits Python that does not faithfully
  preserve the Java. They are not silent fixes.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import j2py.translate.runtime.j2py_runtime as _j2py_runtime_module
from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_source
from j2py.pipeline import translate_file
from j2py.translate.class_members import (
    collect_file_class_declarations,
    collect_file_class_static_instance_aliases,
    merge_class_declaration_indexes,
    merge_class_static_instance_alias_indexes,
    merge_class_static_method_indexes,
)
from j2py.translate.classes import collect_file_class_static_methods
from j2py.translate.skeleton import translate_skeleton_with_diagnostics

# Translated files emit ``from j2py_runtime import overloaded``; register the module
# under the expected top-level name so the linked exec() can resolve it.
sys.modules.setdefault("j2py_runtime", _j2py_runtime_module)

JAVA_DIR = Path(__file__).parent.parent / "fixtures" / "case_study" / "jsemver" / "java"

_CFG = ConfigLoader().add_defaults().build()

# Dependency order: the exception type first, then Stream (which raises it).
_LINK_ORDER = ("UnexpectedElementException", "Stream")

_VERSION_CORE_LINK_ORDER = (
    "ParseException",
    "UnexpectedElementException",
    "Stream",
    "UnexpectedCharacterException",
    "Parser",
    "VersionParser",
    "Version",
)


@dataclass(frozen=True)
class ResidualGap:
    """A documented rule-layer translation defect found in the jsemver output."""

    gap_id: str
    module: str
    summary: str
    bad: str
    good: str


@dataclass(frozen=True)
class TranslationMetric:
    file_name: str
    coverage: float
    semantic_warnings: int
    todos: int


# Each entry is a real defect in the deterministic rule-layer output. ``bad`` is the
# exact text emitted by ``j2py translate --no-llm``; ``good`` is the minimal faithful
# rewrite. See docs/CASE_STUDY_JSEMVER.md for the analysis behind each gap id.
_RESIDUAL_GAP_PATCHES: tuple[ResidualGap, ...] = ()


class _OptionalValue:
    def __init__(self, value: Any) -> None:
        self.value = value

    def if_present(self, consumer: Any) -> None:
        if self.value is not None:
            consumer(self.value)


class _Optional:
    @staticmethod
    def empty() -> _OptionalValue:
        return _OptionalValue(None)

    @staticmethod
    def of(value: Any) -> _OptionalValue:
        return _OptionalValue(value)

    @staticmethod
    def of_nullable(value: Any) -> _OptionalValue:
        return _OptionalValue(value)


class _ExpressionParser:
    @staticmethod
    def new_instance() -> _ExpressionParser:
        return _ExpressionParser()


def _arrays_stub() -> types.SimpleNamespace:
    """Minimal ``java.util.Arrays`` (only ``toString`` is reachable post-patch)."""

    def to_string(values: Any) -> str:
        if values is None:
            return "null"
        return f"[{', '.join(str(v) for v in values)}]"

    return types.SimpleNamespace(to_string=to_string)


def translate_util_package() -> dict[str, str]:
    """Return ``{class_name: rule_layer_python_source}`` for the two util files."""
    sources: dict[str, str] = {}
    for name in _LINK_ORDER:
        result = translate_file(JAVA_DIR / f"{name}.java", cfg=_CFG, use_llm=False, validate=False)
        sources[name] = result.python_source
    return sources


def translate_version_core() -> tuple[dict[str, str], dict[str, TranslationMetric]]:
    """Return translated sources and metrics for the Version/parser closed loop."""
    parsed = {
        name: parse_source((JAVA_DIR / f"{name}.java").read_text())
        for name in _VERSION_CORE_LINK_ORDER
    }
    module_static_methods = merge_class_static_method_indexes(
        *(collect_file_class_static_methods(item.root, _CFG) for item in parsed.values()),
    )
    module_static_instance_aliases = merge_class_static_instance_alias_indexes(
        *(collect_file_class_static_instance_aliases(item.root, _CFG) for item in parsed.values()),
    )
    module_declarations = merge_class_declaration_indexes(
        *(collect_file_class_declarations(item.root) for item in parsed.values()),
    )

    sources: dict[str, str] = {}
    metrics: dict[str, TranslationMetric] = {}
    for name in _VERSION_CORE_LINK_ORDER:
        result = translate_skeleton_with_diagnostics(
            parsed[name],
            extract_symbols(parsed[name]),
            _CFG,
            module_class_static_methods=module_static_methods,
            module_class_static_instance_aliases=module_static_instance_aliases,
            module_class_declarations=module_declarations,
        )
        sources[name] = result.source
        metrics[name] = TranslationMetric(
            file_name=f"{name}.java",
            coverage=result.coverage,
            semantic_warnings=result.diagnostics.semantic_warning_count,
            todos=result.source.count("TODO(j2py)"),
        )
    return sources, metrics


def _apply_residual_gap_patches(name: str, source: str) -> tuple[str, list[str]]:
    """Apply the documented translator-gap patches for ``name``; return (src, applied)."""
    applied: list[str] = []
    for gap in _RESIDUAL_GAP_PATCHES:
        if gap.module != name or gap.bad not in source:
            continue
        source = source.replace(gap.bad, gap.good)
        applied.append(gap.gap_id)
    return source, applied


def link_util_namespace() -> types.SimpleNamespace:
    """Translate, patch, and link the util package, returning the exercised classes.

    The returned namespace exposes ``Stream``, ``UnexpectedElementException``, and the
    list of residual-gap ids that had to be applied for the loop to close.
    """
    sources = translate_util_package()
    shared: dict[str, Any] = {
        "__name__": "jsemver_util_link",
        "Arrays": _arrays_stub(),
    }
    applied_gaps: list[str] = []

    for name in _LINK_ORDER:
        stripped = _strip_linked_imports(sources[name])
        patched, applied = _apply_residual_gap_patches(name, stripped)
        applied_gaps.extend(applied)
        exec(compile(patched, f"<jsemver-util:{name}>", "exec"), shared)  # noqa: S102

    return types.SimpleNamespace(
        Stream=shared["Stream"],
        UnexpectedElementException=shared["UnexpectedElementException"],
        applied_gaps=applied_gaps,
    )


def link_version_core_namespace() -> types.SimpleNamespace:
    """Translate and link the Version/parser dependency closure."""
    sources, metrics = translate_version_core()
    shared: dict[str, Any] = {
        "__name__": "jsemver_core_link",
        "ExpressionParser": _ExpressionParser,
        "Optional": _Optional,
    }
    applied_gaps: list[str] = []

    for name in _VERSION_CORE_LINK_ORDER:
        stripped = _strip_linked_imports(sources[name])
        patched, applied = _apply_residual_gap_patches(name, stripped)
        applied_gaps.extend(applied)
        exec(compile(patched, f"<jsemver-core:{name}>", "exec"), shared)  # noqa: S102

    return types.SimpleNamespace(
        ParseException=shared["ParseException"],
        UnexpectedElementException=shared["UnexpectedElementException"],
        Stream=shared["Stream"],
        UnexpectedCharacterException=shared["UnexpectedCharacterException"],
        Parser=shared["Parser"],
        VersionParser=shared["VersionParser"],
        Version=shared["Version"],
        applied_gaps=applied_gaps,
        metrics=metrics,
    )


def _strip_linked_imports(source: str) -> str:
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
                        "from com.github.zafarkhaja.semver.",
                        "import com.github.zafarkhaja.semver.",
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
        if stripped.startswith(
            ("from com.github.zafarkhaja.semver.", "import com.github.zafarkhaja.semver.")
        ):
            index += 1
            continue
        kept.append(line)
        index += 1
    return "\n".join(kept)

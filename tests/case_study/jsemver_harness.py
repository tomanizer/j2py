"""End-to-end case-study harness for the java-semver ``util`` package (issue #613).

Translates the two vendored ``com.github.zafarkhaja.semver.util`` Java files with the
rule layer only (no LLM), then *links* the translated modules into one shared namespace
so the real translated classes can be exercised by the library's own ported JUnit suite
(``StreamTest``).

This is the first **external** end-to-end conversion case study: jsemver is a third-party
OSS library, not a curated j2py fixture. The goal is to measure — honestly — how far the
deterministic rule layer gets on real library code and to publish the residual gap list.

Two kinds of intervention are applied before the translated source can run, and the
case-study doc (docs/CASE_STUDY_JSEMVER.md) keeps them strictly separate:

* ``_EXTERNAL_STUBS`` — JDK/runtime symbols that are *not under test* (``Arrays``,
  ``RuntimeException`` base). These are scaffolding, exactly like the dependency stubs in
  ``tests/case_study/harness.py`` and ``tests/equivalence/harness.py``.

* ``_RESIDUAL_GAP_PATCHES`` — concrete *translator defects* found in the rule-layer
  output. Each patch is a single, documented source rewrite tagged with a gap id. The
  list of these patches **is** the residual failure list the case study reports: every
  entry is a place where the current rule layer emits Python that does not faithfully
  preserve the Java. They are applied here so the loop can close and the behavioural
  oracle can run; they are not silent fixes.
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

# Translated files emit ``from j2py_runtime import overloaded``; register the module
# under the expected top-level name so the linked exec() can resolve it.
sys.modules.setdefault("j2py_runtime", _j2py_runtime_module)

JAVA_DIR = Path(__file__).parent.parent / "fixtures" / "case_study" / "jsemver" / "java"

_CFG = ConfigLoader().add_defaults().build()

# Dependency order: the exception type first, then Stream (which raises it).
_LINK_ORDER = ("UnexpectedElementException", "Stream")


@dataclass(frozen=True)
class ResidualGap:
    """A documented rule-layer translation defect found in the jsemver output."""

    gap_id: str
    module: str
    summary: str
    bad: str
    good: str


# Each entry is a real defect in the deterministic rule-layer output. ``bad`` is the
# exact text emitted by ``j2py translate --no-llm``; ``good`` is the minimal faithful
# rewrite. See docs/CASE_STUDY_JSEMVER.md for the analysis behind each gap id.
_RESIDUAL_GAP_PATCHES: tuple[ResidualGap, ...] = (
    ResidualGap(
        gap_id="JSEMVER-1",
        module="UnexpectedElementException",
        summary="JDK builtin RuntimeException emitted as a sibling-package import",
        bad="from com.github.zafarkhaja.semver.util.RuntimeException import RuntimeException",
        good="",
    ),
    ResidualGap(
        gap_id="JSEMVER-2",
        module="Stream",
        summary="Java array .clone() not lowered to a Python copy",
        bad="self.elements = elements.clone()",
        good="self.elements = list(elements)",
    ),
    ResidualGap(
        gap_id="JSEMVER-3",
        module="Stream",
        summary="anonymous-class body reads enclosing field 'offset' as a bare name "
        "instead of capturing it from the enclosing instance",
        bad="self.index: int = offset",
        good="self.index: int = _outer_self.offset",
    ),
    ResidualGap(
        gap_id="JSEMVER-5",
        module="Stream",
        summary="java.util.Arrays.copyOfRange not lowered to a Python slice",
        bad="return Arrays.copy_of_range(self.elements, self.offset, len(self.elements))",
        good="return self.elements[self.offset:]",
    ),
    ResidualGap(
        gap_id="JSEMVER-6",
        module="Stream",
        summary="anonymous java.util.Iterator impl emits Java-style next_/has_next but "
        "inherits Python's Iterator ABC, so it cannot be instantiated (missing __next__)",
        bad="class _J2pyAnonymous1(Iterator):",
        good="class _J2pyAnonymous1:",
    ),
)


def _arrays_stub() -> types.SimpleNamespace:
    """Minimal ``java.util.Arrays`` (only ``toString`` is reachable post-patch)."""

    def to_string(values: Any) -> str:
        if values is None:
            return "null"
        return f"[{', '.join(str(v) for v in values)}]"

    return types.SimpleNamespace(to_string=to_string)


class _RuntimeException(Exception):
    """Stand-in for ``java.lang.RuntimeException`` with Throwable's ``getMessage``."""

    def get_message(self) -> str:
        return str(self)


def translate_util_package() -> dict[str, str]:
    """Return ``{class_name: rule_layer_python_source}`` for the two util files."""
    sources: dict[str, str] = {}
    for name in _LINK_ORDER:
        result = translate_file(JAVA_DIR / f"{name}.java", cfg=_CFG, use_llm=False, validate=False)
        sources[name] = result.python_source
    return sources


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
        "Arrays": _arrays_stub(),
        "RuntimeException": _RuntimeException,
    }
    applied_gaps: list[str] = []

    for name in _LINK_ORDER:
        patched, applied = _apply_residual_gap_patches(name, sources[name])
        applied_gaps.extend(applied)
        exec(compile(patched, f"<jsemver:{name}>", "exec"), shared)  # noqa: S102

    return types.SimpleNamespace(
        Stream=shared["Stream"],
        UnexpectedElementException=shared["UnexpectedElementException"],
        applied_gaps=applied_gaps,
    )

"""End-to-end case-study harness for the java-semver ``util`` package (issue #613).

Translates the two vendored ``com.github.zafarkhaja.semver.util`` Java files with the
rule layer only (no LLM), then *links* the translated modules into one shared namespace
so the real translated classes can be exercised by the library's own ported JUnit suite
(``StreamTest``).

This is the first **external** end-to-end conversion case study: jsemver is a third-party
OSS library, not a curated j2py fixture. The goal is to measure — honestly — how far the
deterministic rule layer gets on real library code and to publish the residual gap list.

One kind of intervention is applied before the translated source can run, and the
case-study doc (docs/CASE_STUDY_JSEMVER.md) keeps it separate from translator fixes:

* ``_EXTERNAL_STUBS`` — JDK/runtime symbols that are *not under test* (``Arrays``).
  These are scaffolding, exactly like the dependency stubs in
  ``tests/case_study/harness.py`` and ``tests/equivalence/harness.py``.

* ``_RESIDUAL_GAP_PATCHES`` — currently empty. It remains in the harness to lock the
  patch inventory at zero and to make future residual translator defects explicit.
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


# The inventory is intentionally empty after the JSEMVER-1..6 fixes. Future entries must
# remain explicit documented rule-layer defects, not silent harness rewrites.
_RESIDUAL_GAP_PATCHES: tuple[ResidualGap, ...] = ()


def _arrays_stub() -> types.SimpleNamespace:
    """Minimal ``java.util.Arrays`` (only ``toString`` is reachable)."""

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


def _apply_residual_gap_patches(name: str, source: str) -> tuple[str, list[str]]:
    """Apply documented translator-gap patches for ``name``; currently a no-op."""
    applied: list[str] = []
    for gap in _RESIDUAL_GAP_PATCHES:
        if gap.module != name or gap.bad not in source:
            continue
        source = source.replace(gap.bad, gap.good)
        applied.append(gap.gap_id)
    return source, applied


def link_util_namespace() -> types.SimpleNamespace:
    """Translate and link the util package, returning the exercised classes.

    The returned namespace exposes ``Stream``, ``UnexpectedElementException``, and the
    list of residual-gap ids that were applied while linking.
    """
    sources = translate_util_package()
    shared: dict[str, Any] = {
        "Arrays": _arrays_stub(),
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

"""End-to-end case-study harness for Apache Commons Codec ``Hex`` (issue #656).

The harness translates the scoped Commons Codec sources with the deterministic rule layer
only (``use_llm=False``), links the translated classes into one namespace, and supplies
small external stubs for JDK symbols outside the tested library behavior.

Residual translator patches are declared explicitly in ``_RESIDUAL_GAP_PATCHES``. Those
patches are not dependency stubs: each one is a generated-output defect that should become
a rule-layer fix before being removed from the inventory.
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

JAVA_DIR = Path(__file__).parent.parent / "fixtures" / "case_study" / "commons_codec_hex" / "java"

_CFG = ConfigLoader().add_defaults().build()

_LINK_ORDER = (
    "BinaryDecoder",
    "BinaryEncoder",
    "DecoderException",
    "EncoderException",
    "Hex",
)


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


_ENCODE_HEX_TO_OUT_CALL = (
    "            Hex.encode_hex("
    "data, data_offset, data_len, Hex.to_alphabet(to_lower_case), out, out_offset)\n"
)

_RESIDUAL_GAP_PATCHES: tuple[ResidualGap, ...] = (
    ResidualGap(
        "CODEC-HEX-5",
        "Hex",
        "Java decimal grouping format tokens are not normalized for Python formatting",
        "%,d",
        "%d",
    ),
    ResidualGap(
        "CODEC-HEX-14",
        "Hex",
        "void overload dispatcher branch falls through after delegated encodeHex call",
        _ENCODE_HEX_TO_OUT_CALL,
        _ENCODE_HEX_TO_OUT_CALL + "            return None\n",
    ),
)


class _Charset:
    def __init__(self, name: str) -> None:
        self._name = name

    @classmethod
    def for_name(cls, name: str) -> _Charset:
        if name.upper().replace("_", "-") != "UTF-8":
            raise LookupError(name)
        return cls("UTF-8")

    def name(self) -> str:
        return self._name

    def __str__(self) -> str:
        return self._name


class _ByteBuffer:
    pass


class _Character:
    @staticmethod
    def digit(ch: str, radix: int) -> int:
        if len(ch) != 1:
            return -1
        try:
            value = int(ch, radix)
        except ValueError:
            return -1
        return value if 0 <= value < radix else -1


_EXTERNAL_STUBS: dict[str, Any] = {
    "ByteBuffer": _ByteBuffer,
    "Character": _Character,
    "Charset": _Charset,
    "CharEncoding": types.SimpleNamespace(UTF_8="UTF-8"),
    "StandardCharsets": types.SimpleNamespace(UTF_8=_Charset("UTF-8")),
}


def translate_commons_codec_hex() -> tuple[dict[str, str], dict[str, TranslationMetric]]:
    """Return translated sources and metrics for the scoped Commons Codec files."""
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
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("from java.", "import java.")):
            continue
        if stripped.startswith(
            ("from org.apache.commons.codec.", "import org.apache.commons.codec.")
        ):
            continue
        kept.append(line)
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


def link_commons_codec_hex_namespace() -> types.SimpleNamespace:
    """Translate and link the scoped Commons Codec Hex classes."""
    sources, metrics = translate_commons_codec_hex()
    shared: dict[str, Any] = dict(_EXTERNAL_STUBS)
    applied_gaps: list[str] = []

    for name in _LINK_ORDER:
        source, applied = _apply_residual_gap_patches(name, sources[name])
        source = _strip_external_imports(source)
        applied_gaps.extend(applied)
        exec(compile(source, f"<commons_codec_hex:{name}>", "exec"), shared)  # noqa: S102

    return types.SimpleNamespace(
        BinaryDecoder=shared["BinaryDecoder"],
        BinaryEncoder=shared["BinaryEncoder"],
        DecoderException=shared["DecoderException"],
        EncoderException=shared["EncoderException"],
        Hex=shared["Hex"],
        applied_gaps=applied_gaps,
        metrics=metrics,
        external_stubs=tuple(sorted(_EXTERNAL_STUBS)),
    )

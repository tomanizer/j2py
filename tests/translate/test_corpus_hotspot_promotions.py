"""Fast contracts promoted from recurring corpus hotspot failures."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.conftest import TARGET_FIXTURES
from tests.translate.skeleton.helpers import CFG

HOTSPOT_FIXTURES = TARGET_FIXTURES


@dataclass(frozen=True)
class PromotedHotspot:
    fixture: str
    source: str
    hotspot: str
    expected_fragments: tuple[str, ...]
    forbidden_fragments: tuple[str, ...] = (
        "TODO(j2py): unsupported",
        "__j2py_todo__",
    )


GRADUATED_HOTSPOTS = (
    PromotedHotspot(
        fixture="CorpusArrayTypeMapProbe.java",
        source="Spring PropertyEditorRegistrySupport.java",
        hotspot="unsupported expression array_type",
        expected_fragments=(
            "editors.put(list[type], object())",
            "editors.put(list[str], object())",
            "editors.put(list[int], object())",
        ),
        forbidden_fragments=("unsupported expression array_type", "__j2py_todo__"),
    ),
    PromotedHotspot(
        fixture="CorpusAssertStatementProbe.java",
        source="Commons Lang CachedRandomBits.java",
        hotspot="unsupported statement assert_statement",
        expected_fragments=("assert bit_index == len(cache) * 8",),
        forbidden_fragments=("unsupported statement assert_statement", "__j2py_todo__"),
    ),
    PromotedHotspot(
        fixture="CorpusMalformedTernaryProbe.java",
        source="Jackson InetSocketAddressSerializer.java",
        hotspot="malformed ternary expression",
        expected_fragments=('str_ = f"[{str_[1:]}]" if isinstance(addr, object) else str_[1:]',),
        forbidden_fragments=("malformed ternary expression", "__j2py_todo__"),
    ),
)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=f"{Path(case.fixture).stem}-{case.hotspot}")
        for case in GRADUATED_HOTSPOTS
    ],
)
def test_promoted_corpus_hotspot_translates_cleanly(case: PromotedHotspot) -> None:
    """Corpus hotspot exemplars that are now fast make-check regressions."""
    parsed = parse_file(HOTSPOT_FIXTURES / case.fixture)
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert result.coverage == 1.0, case.source
    assert not result.diagnostics.unhandled, case.hotspot
    for fragment in case.expected_fragments:
        assert fragment in result.source
    for fragment in case.forbidden_fragments:
        assert fragment not in result.source

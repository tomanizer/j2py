"""Tests for the top-level translation pipeline."""

import ast
from pathlib import Path

from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_file

FIXTURES = Path(__file__).parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()


def test_translate_file_no_llm_preserves_full_confidence_fixture() -> None:
    result = translate_file(FIXTURES / "java" / "HelloWorld.java", cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence == 1.0
    assert result.python_source == (FIXTURES / "python" / "HelloWorld.py").read_text()
    ast.parse(result.python_source)


def test_translate_file_no_llm_returns_partial_confidence_fixture() -> None:
    result = translate_file(FIXTURES / "java" / "Fields.java", cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence < 1.0
    assert "TODO(j2py): verify default value for field enabled" in result.python_source
    assert result.python_source == (FIXTURES / "python" / "Fields.py").read_text()
    ast.parse(result.python_source)

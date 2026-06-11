"""Shared helpers for skeleton translator tests."""

import ast
from pathlib import Path

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_source
from j2py.translate.skeleton import translate_skeleton, translate_skeleton_with_diagnostics

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()


def translate_source(source: str, cfg=CFG) -> tuple[str, float]:
    parsed = parse_source(source)
    return translate_skeleton(parsed, extract_symbols(parsed), cfg)


def translate_source_with_diagnostics(source: str, cfg=CFG):
    parsed = parse_source(source)
    return translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), cfg)


def assert_valid_python(source: str) -> None:
    ast.parse(source)

"""Shared helpers for skeleton translator tests."""

import ast
import importlib
import sys
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


def assert_module_executes(source: str) -> None:
    """Execute *source* as a module body, resolving imports and top-level defs.

    Stronger than :func:`assert_valid_python` (which only parses): this runs the
    ``from __future__``/import lines — including the vendored ``from j2py_runtime
    import ...`` the skeleton emits — and the class/function definitions, so it
    catches undefined names emitted at module scope (e.g. a mistranslated ``new
    Object()`` leaking an undefined ``Object``). Method/constructor bodies are not
    invoked, so undefined free functions referenced only inside them are tolerated.
    """
    runtime = importlib.import_module("j2py.translate.runtime.j2py_runtime")
    sys.modules.setdefault("j2py_runtime", runtime)
    namespace: dict[str, object] = {}
    exec(compile(source, "<translated>", "exec"), namespace)

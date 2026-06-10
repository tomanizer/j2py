#!/usr/bin/env python3
"""On-demand exploratory tool: run tree-sitter skeleton + LLM completion on a Java file.

This lets you quickly check "how far we can get when the parser + rules send what
they already have to the LLM".

Usage examples:

    # Run on a specific file (requires ANTHROPIC_API_KEY)
    ANTHROPIC_API_KEY=... uv run python scripts/explore_llm.py path/to/Some.java

    # Run on the synthetic example from the e2e test
    ANTHROPIC_API_KEY=... uv run python scripts/explore_llm.py --synthetic

    # With a different model or no cache
    ANTHROPIC_API_KEY=... uv run python scripts/explore_llm.py path/to/File.java \
        --model claude-sonnet-4-6 --no-cache

The script always:
- Parses with tree-sitter
- Runs the full deterministic rule skeleton (exactly what production does)
- Captures diagnostics / coverage / context
- Sends the real partial_python + diagnostics to the LLM
- Prints the skeleton, the unhandled items, and the final LLM output
- Verifies the result is valid Python

This is the "live" path and is intentionally not part of the normal test suite.
See tests/llm/test_e2e_llm.py and make test-llm-e2e for the test version.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path
from textwrap import dedent

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.llm.client import translate_with_llm
from j2py.parse.java_ast import parse_file, parse_source
from j2py.pipeline import _diagnostics_context, _project_context
from j2py.translate.skeleton import translate_skeleton_with_diagnostics


def _synthetic_java() -> str:
    return dedent("""
        package com.example;

        public class Greeter {
            private final String name;

            public Greeter(String name) {
                this.name = name;
            }

            public String greet() {
                return "Hello, " + name + "!";
            }
        }
    """).strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explore skeleton + LLM quality on arbitrary Java (on demand only)."
    )
    parser.add_argument(
        "java_file",
        type=Path,
        nargs="?",
        help="Path to a .java file. Omit when using --synthetic.",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use the built-in tiny Greeter example instead of a file.",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Claude model to use for the completion step.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable disk cache for this run (recommended for exploration).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print the final LLM output (useful for piping or quick checks).",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable is required.", file=sys.stderr)
        return 2

    cfg = ConfigLoader().add_defaults().build()

    if args.synthetic:
        java_source = _synthetic_java()
        source_path = Path("<synthetic Greeter.java>")
        parsed = parse_source(java_source.encode("utf-8"), path=source_path)
    else:
        if not args.java_file:
            parser.error("java_file is required unless --synthetic is used")
        if not args.java_file.exists():
            print(f"ERROR: File not found: {args.java_file}", file=sys.stderr)
            return 2
        source_path = args.java_file
        java_source = source_path.read_text(encoding="utf-8")
        parsed = parse_file(source_path)

    symbols = extract_symbols(parsed)
    skeleton_result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)

    diagnostics_str = _diagnostics_context(skeleton_result.diagnostics)
    context_str = _project_context(symbols)

    if not args.quiet:
        print("=" * 60)
        print(f"FILE: {source_path}")
        print("=" * 60)
        print("\n--- RULE SKELETON (what tree-sitter + rules produced) ---")
        print(skeleton_result.source)
        print(f"\n--- SKELETON COVERAGE: {skeleton_result.coverage:.2%} ---")
        if skeleton_result.diagnostics.unhandled:
            print("\n--- UNHANDLED (will be sent to LLM) ---")
            print(diagnostics_str)
        else:
            print("\n--- UNHANDLED: none (LLM should not be needed) ---")
        print("\n--- CALLING LLM (partial skeleton + diagnostics) ---")
        print(f"model: {args.model}")
        print(f"use_cache: {not args.no_cache}")
        print("-" * 60)

    final_python = translate_with_llm(
        java_source=java_source,
        partial_python=skeleton_result.source,
        context=context_str,
        diagnostics=diagnostics_str,
        model=args.model,
        use_cache=not args.no_cache,
    )

    if args.quiet:
        print(final_python)
    else:
        print("\n--- FINAL LLM OUTPUT ---")
        print(final_python)
        print("\n" + "=" * 60)

    # Always do basic validation
    try:
        ast.parse(final_python)
        print("✓ Result is valid Python (ast.parse succeeded)")
    except SyntaxError as e:
        print(f"✗ Result has syntax errors: {e}")
        return 1

    # Light structural smoke checks (very loose, for quick feedback)
    if "class " in final_python or "def " in final_python:
        print("✓ Contains at least one class or def (very basic sanity)")
    else:
        print("? Output is unusually small — inspect manually")

    if not args.quiet:
        print("\nTip: re-run with --no-cache to force a fresh LLM call.")
        print("     Use --synthetic for the tiny built-in example.")
        print("     This script is for exploration only — not part of make check.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

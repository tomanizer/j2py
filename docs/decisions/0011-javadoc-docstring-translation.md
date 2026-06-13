# ADR 0011 — Javadoc docstring translation

**Date:** 2026-06-13
**Status:** Accepted

## Context

j2py previously preserved Java block comments as `#` line comments. That kept source text
visible, but Javadoc-heavy classes produced large comment walls that separated API
documentation from the translated class or method it described.

The product goal is side-by-side reviewability. For API documentation, reviewability is
better served by placing Javadoc on the translated Python declaration as a docstring while
keeping ordinary block and line comments as comments.

## Decision

Javadoc blocks (`/** ... */`) immediately preceding a class, nested class, constructor,
or method translate to Python docstrings by default. The rule layer converts common
Javadoc tags to Google-style docstring sections:

- `@param` -> `Args:`
- `@return` -> `Returns:`
- `@throws` / `@exception` -> `Raises:`
- `@deprecated` -> `.. deprecated::`
- `@since` is dropped

Inline `{@code ...}` and `{@link ...}` tags become simple backtick references. Ordinary
comments are unchanged. `emit_docstrings=False` keeps Javadocs on the existing comment
path, and `emit_line_comments=False` suppresses comment-derived output entirely.

## Consequences

+ Javadoc appears at the Python declaration reviewers expect.
+ The rule-layer output is more readable for Javadoc-heavy Java APIs.
+ The LLM prompt rule, "Do NOT add docstrings unless the Java had Javadoc," stays aligned
  with deterministic output.
- The conversion is intentionally shallow; complex HTML tables and rich Javadoc markup
  are normalized to plain text rather than preserved exactly.

## References

- [Issue #121](https://github.com/tomanizer/j2py/issues/121)
- [ADR 0003](0003-layered-translation-pipeline.md)

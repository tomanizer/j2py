# ADR 0003 — Layered translation pipeline with line-level correspondence goal

**Date:** 2026-06-10
**Status:** Accepted

## Context

There are two broad strategies for Java→Python conversion:

**LLM-only:** Send the Java source directly to an LLM, receive Python back.
- Pro: handles anything, including complex logic
- Con: non-deterministic, expensive on large codebases, no structural guarantee,
  hard to review incrementally, cannot be cached reliably at file granularity

**Rule-only:** Mechanical AST-to-AST transformation.
- Pro: deterministic, fast, cacheable, reviewable
- Con: cannot handle complex logic (stream chains, reflective patterns, generics-heavy
  code); requires a rule for every Java construct

Neither alone is adequate for a large, real-world Java project.

The target quality bar is **line-level structural correspondence**: the Python output
should have the same method ordering, same control-flow structure, and same naming
(snake_cased) as the Java source, so a reviewer can audit them side-by-side without
re-learning the logic.

## Decision

Use a **layered pipeline**:

1. **Rule-based skeleton** (`translate/skeleton.py`): mechanically translate the
   structural parts of a class — type annotations, method signatures, imports,
   control-flow scaffolding. Target: ~70% coverage on typical business-logic classes.
   Returns `(skeleton_source: str, coverage: float)`.

2. **LLM completion** (`llm/`): when `coverage < 1.0`, pass the Java source + skeleton
   to the configured LLM provider with a structured prompt. The LLM sees the
   partially-translated skeleton as context and fills in what the rule layer left as
   `# TODO(j2py)` stubs. This is significantly cheaper and more accurate than
   translating from scratch.

3. **Confidence score**: `TranslationResult.confidence` is the surfaced review-trust
   score. Raw node coverage remains available as `diagnostics.coverage`, but confidence
   is clamped below 1.00 when parse errors, post-validation failures, structural
   verification failures, or semantic warnings make full trust dishonest. Semantic
   warnings cap confidence at 0.99; validation and structural failures cap it at 0.79,
   below the low-confidence threshold. Files with `confidence < 0.8` are flagged in the
   CLI output for priority human review.

**Structural correspondence is a first-class requirement**, not a nice-to-have:
- Preserve Java method order
- Preserve Java control-flow structure (no algorithmic rewrites)
- camelCase → snake_case naming (same identifiers, different convention)
- Do not add Python idioms that obscure the Java structure (no comprehension rewrites
  of explicit for-loops unless the Java used streams)

## Consequences

+ Rule layer is deterministic and fast; large portions of mechanical code need no LLM
+ LLM layer has a partially-translated skeleton as context — better accuracy, fewer tokens
+ Coverage metric drives human review priority
+ Reviewable output: same structure as Java means the reviewer doesn't re-read logic
− Status note: the rule layer is now an implemented and incomplete deterministic
  visitor layer. Current work should extend
  `classes.py`, `statements.py`, `expressions.py`, and pure helpers in `rules/`.
− Two-layer system is more complex than LLM-only; coverage estimate must be honest
  (inflating it to skip the LLM defeats the purpose)
− LLM output is non-deterministic for the portions it handles; disk cache mitigates
  this for unchanged files

## References

- java2python (2008-2015): the precedent for a rule-based approach; archived but useful
  for studying rule set design
- [PRODUCT_REQUIREMENTS.md](../PRODUCT_REQUIREMENTS.md) F2, F3, F4

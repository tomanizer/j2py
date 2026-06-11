# ADR 0010 — Post-LLM structural verification and default validation

**Date:** 2026-06-11
**Status:** Accepted

## Context

The LLM completion layer is useful for constructs the deterministic skeleton cannot
finish, but a syntactically valid Python file can still be a bad translation if the LLM
drops a method, reorders declarations, or reshapes the Java program in ways that break
side-by-side review.

The project already runs Python validation (`ast.parse`, ruff, mypy) when requested, and
the CLI translate path defaulted validation on. The Python API and compare generation path
still defaulted validation off, and no deterministic post-LLM check enforced class/method
presence or ordering.

## Decision

Add a post-LLM structural verifier:

- Compare the Java symbol table against the returned Python AST.
- Verify expected top-level and nested classes are present and keep Java order.
- Verify expected methods are present and keep Java order, mapping constructors to
  `__init__` and Java method names through the normal snake_case naming rule.
- Store the result on `TranslationResult.structural_verification`.
- Feed structural verifier errors into the existing single LLM retry, together with
  Python validation feedback.

Turn validation on by default for the public translation API and compare generation path:

- `translate_file(..., validate=True)` by default.
- `translate_directory(..., validate=True)` by default.
- `j2py compare` generated translations validate by default, with `--no-validate` as the
  opt-out.

## Consequences

+ The LLM can no longer silently drop a class or method without the pipeline recording a
  structural failure and attempting one correction.
+ Default API behavior now matches the safer CLI translation path.
+ Structural checks are deterministic, cheap, and aligned with the line-level
  correspondence requirement.
− The verifier is intentionally shallow: it does not prove behavioral equivalence or
  compare statement-level semantics.
− Validation defaults may make API calls slower unless callers explicitly pass
  `validate=False`.

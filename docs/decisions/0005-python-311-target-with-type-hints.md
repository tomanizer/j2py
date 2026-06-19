# ADR 0005 — Python 3.11+ output target with full type annotations

**Date:** 2026-06-10
**Status:** Accepted

## Context

The translated Python output needs a target version. Key considerations:

- **Type annotation syntax**: Python 3.9 enabled `list[str]` and `dict[K, V]` as
  built-in generic syntax (PEP 585). Python 3.10 added `X | Y` union syntax (PEP 604).
  Python 3.11 added `Self`, `Never`, and `LiteralString` to `typing`.
- **Java type annotation richness**: Java has `List<String>`, `Map<K,V>`,
  `Optional<T>`, etc. — all translatable to Python only with modern annotation syntax
- **Line-level correspondence goal**: type annotations on every variable declaration,
  parameter, and return type are necessary to preserve the Java type information visible
  to a reviewer
- **Adoption**: Python 3.11 is broadly supported as of 2026; 3.12/3.13 add nothing
  needed for translation output

## Decision

Target **Python 3.11+**. All translated output must:

1. Use PEP 585 built-in generic syntax: `list[str]`, `dict[K, V]`, `tuple[int, ...]`
   — never `List[str]` from `typing`
2. Use PEP 604 union syntax: `str | None` — never `Optional[str]`
3. Use `from __future__ import annotations` at the top of every output file to enable
   forward references and defer annotation evaluation
4. Emit type annotations on:
   - All method parameters (including `self`)
   - All method return types
   - All field declarations where the type is statically known
   - Local variable declarations where the type is non-obvious

The j2py source code itself also targets Python 3.11 and passes `mypy --strict`.

## Consequences

+ Output is fully typed — reviewers can run mypy on translated files as a correctness check
+ Modern syntax is more readable (`str | None` vs `Optional[str]`)
+ `from __future__ import annotations` handles forward references without runtime cost
− Output cannot be used on Python 3.8/3.9/3.10 without modification; this is acceptable
  since the goal is a new Python codebase, not a backport
− `typing.Any` is still needed for wildcard generics (`?` in Java); it is imported
  lazily only when needed

## References

- PEP 585: https://peps.python.org/pep-0585/
- PEP 604: https://peps.python.org/pep-0604/
- [PRODUCT_REQUIREMENTS.md](../PRODUCT_REQUIREMENTS.md) F2 (rule-based skeleton must emit type annotations)

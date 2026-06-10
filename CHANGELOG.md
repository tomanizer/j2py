# Changelog

All notable changes to j2py will be documented in this file.

The format follows the repository commit types: `feat`, `fix`, `refactor`, `test`,
`docs`, `chore`, and `adr`.

## Unreleased

### Added

- Initial deterministic skeleton translator for simple Java classes.
- Structured rule-layer diagnostics and coverage reporting.
- Spring corpus scoreboard with a pinned baseline.
- Roadmap target tests for unsupported Java-to-Python constructs.
- Dependency-ordered directory translation with package-relative output paths.
- Config-driven import emission, type maps, collection maps, exception maps, and
  translation flags.
- Deterministic translation for common control flow, exception handling, comments,
  nested type declarations, overload stubs, constructor delegation, and common
  expression shapes.
- Deterministic translation for standalone expression lambdas and basic method
  references, with block lambdas kept as explicit unresolved regions.
- Deterministic translation for safe traditional switch cases and switch expressions,
  with fall-through and complex switch blocks left as diagnostics.
- Deterministic translation for simple stream `map`/`filter`/`toList` pipelines when
  mapper and predicate expressions are supported.
- LLM prompt context for project symbols, rule diagnostics, config fingerprints, and
  validation feedback.
- On-demand LLM exploration helper for manually inspecting the tree-sitter skeleton,
  diagnostics, final LLM output, and validation results outside the normal test suite.

### Changed

- Split skeleton translation into class, statement, expression, diagnostic, and node helper
  modules.
- Updated contributor and architecture docs to describe the implemented deterministic
  visitor layer and the remaining unsupported constructs.
- Generalized CLI help text for configured LLM usage without changing the Anthropic
  backend contract.

### Fixed

- Preserved Java `Map.get` missing-key semantics, translated `.equals(...)`, and made
  integer division and ambiguous `get` calls honest through diagnostics.
- Preserved Java left-to-right evaluation for string concatenation with leading numeric
  operands.
- Removed tracked `.pyc` and `__pycache__` files from version control.

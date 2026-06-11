# Changelog

All notable changes to j2py will be documented in this file.

The format follows the repository commit types: `feat`, `fix`, `refactor`, `test`,
`docs`, `chore`, and `adr`.

## Unreleased

### Added
- Deterministic translation for `instanceof` expressions, `instanceof` pattern
  variable bindings, cast expressions with review warnings, and bitwise/shift
  operators including compound bitwise assignment.
- Block lambdas (`x -> { statements; return v; }`) are now supported deterministically. They are turned into a local nested helper (`_j2py_lambda_N`) emitted near the top of the enclosing method; the helper name is used at the call site. The block body structure is preserved for reviewability.
- Complex stream pipelines/collectors: extended deterministic support for toSet, basic joining, .distinct(), .sorted() (simple or with key via method ref), and basic groupingBy (via emitted accumulation helpers using defaultdict). Builds on prior block lambda work; many cases now rewrite to clean comps or stdlib helpers (per review feedback favoring itertools/functools where used).

### Fixed
- `_stream_item_name`: improved plural stripping with explicit map for common cases ("statuses"→"status", "types"→"type", "classes"→"class" etc.) to avoid "statu"/"addres"/"typ" etc. in stream listcomps.
- Integer division (`int / int`): now uses `diagnostics.warn()` (visible for review) instead of `record(supported=False)`. Correct `//` output no longer forces LLM or lowers coverage.
- Lambda/alias context in expressions: added `try/finally` around mutable `TranslationContext` updates (`local_names`, `variable_types`, `expression_aliases`) so exceptions during body translation cannot leak state to callers.
- Overload merge paths: no longer downgrade `class_field_types` to all `"object"`. Real field types (including collections) are now preserved in the shared implementation body, enabling correct specializations (e.g. list `get`).
- Removed misleading claim that the `switch_expression` dispatch in `translate_statement` was dead; kept it (with expanded comment) because tree-sitter-java uses the same node type for traditional colon switch *statements*. Added clarifying comments + tests.

### Added (historical)

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

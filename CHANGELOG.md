# Changelog

All notable changes to j2py will be documented in this file.

The format follows the repository commit types: `feat`, `fix`, `refactor`, `test`,
`docs`, `chore`, and `adr`.

## Unreleased

### Fixed
- LLM calls now send the system prompt as an Anthropic prompt-cache block, enabling
  warm calls to reuse the cached prompt instead of resending the fixed instructions (#116).
- Java cast expressions now add reviewer-visible trailing `# cast: (...)` comments when
  line comments are enabled, with numeric narrowing casts marked explicitly (#112).
- Java unsigned right shift (`>>>` and `>>>=`) lowers to masked Python shifts for
  known `int`/`long` widths, with an explicit 32-bit assumption warning only when the
  operand width is unknown (#109).

## 0.3.0a1 - 2026-06-13

### Added
- Stream pipelines with `flatMap(List::stream)` rewrite to nested comprehensions
  instead of falling back to a translated `flat_map` chain (#92).
- `Collectors.groupingBy(key, Collectors.mapping(identity, Collectors.toList()))`
  rewrites via the existing `_j2py_groupby_*` helper pattern (#93).
- `AdvancedStreams` graduated from future xfail target to the deterministic corpus
  construct regression suite after flatMap and groupingBy downstream support (#75).

### Changed
- README, PyPI package description, and contributor/corpus docs describe j2py as a
  general Java-to-Python library; Spring Framework is documented as an external
  benchmark corpus only.

### Fixed
- `List.get(index)` and map-like map receivers (`MultiValueMap`, `AnnotationAttributes`,
  `*Map` types) resolve without ambiguous-get diagnostics when receiver types are
  known from declarations or parameters (#87).
- Static class fields, nested holder field access (`holder.field.get`), union-typed
  receivers, and API calls (`Field.get`, `Future.get`, `ScheduledFuture.get`) are
  inferred so benchmark-corpus `get(...)` diagnostics drop to zero (#87).
- LLM structural repair retries hardened for transient API failures (#96).
- `make test-targets` succeeds when no future xfail roadmap contracts remain.

## 0.2.0a1 - 2026-06-11

### Added
- Java `@interface` declarations translate to inert `@dataclass(frozen=True)` metadata
  classes with element fields, tuple array types, and preserved meta-annotation warnings (#83).
- `SuperMethodCalls` graduated from future xfail target to the deterministic corpus
  construct regression suite.

### Changed
- Java `super` used as a method/field receiver translates to `super()` in expressions (#82).

### Fixed
- Traditional `for` loops without an update clause lower to initializer plus
  `while condition` instead of `malformed for statement` (#81).
- Annotation element defaults are selected after the Java `default` token so element
  modifiers such as `@AliasFor` no longer produce `unsupported expression modifiers` (#89).
- Unary annotation element defaults such as `default -1` translate as valid Python
  defaults instead of unresolved annotation members (#89).
- Release distribution checks validate only wheel and sdist artifacts, so auxiliary
  files under `dist/` do not fail `make release-check`.

## 0.1.0a1 - 2026-06-11

### Added
- GitHub Actions corpus workflow (`.github/workflows/corpus.yml`) comparing the pinned
  Spring sample against the committed baseline on translation/corpus path changes.
- `j2py analyze` dependency graph and translation-order output for file and directory modes.
- Skeleton translator tests split under `tests/translate/skeleton/` by concern (#69).
- ADR 0010: `synchronized(this)` translates to `self._j2py_lock` with `threading.Lock()`
  initialization in constructors or synthetic `__init__`.
- Preferred dense Spring + curated-construct corpus baseline workflow:
  `corpus-spring-dense-check`, `corpus-spring-dense-update-baseline`, and
  `tests/fixtures/corpus/spring-dense-baseline.json`.
- Future corpus target for `super.method(...)` receiver calls identified by the dense
  Spring corpus.
- Shared `tests/conftest.py` with session `cfg` fixture and fixture path constants.
- `TranslationDiagnostics.semantic_warning_count` and `rule_coverage` alias documenting
  that warnings do not reduce node coverage.
- Strict xfail `FUTURE_TARGETS` for two corpus constructs still below full rule coverage
  (`AdvancedStreams`, `SuperMethodCalls`).
- Graduated corpus construct regression tests in `make check` for eight constructs that
  reach full skeleton coverage (`AdvancedEnum`, `ComplexRecords`, `InterfaceDefaults`,
  `SealedClasses`, `TextBlocks`, `VarKeyword`, `SwitchFallthrough`, `AnonymousAndInner`).
- Record declarations (`record_declaration`) in the symbol table: component fields,
  body methods, inner records, and `is_record` on `ClassSymbol`.
- `TranslationResult.parse_ok` and `PARSE_ERROR_LLM_SKIP_MSG`: malformed Java with
  tree-sitter `ERROR`/`MISSING` nodes skips LLM completion and reports `confidence=0.0`.

### Changed
- Anonymous class instance fields translate to helper-class `__init__` assignments with
  `self.` field access in methods (#74).
- Switch fall-through translates to reviewable prefix `elif`/`if` chains with explicit
  default guards (`elif subject not in (...)` after fall-through blocks) (#73).
- Local `var` declarations infer Python types from initializers; enhanced-for `var` binds
  element types from iterable annotations (#72).
- Prepared the first MIT-licensed PyPI alpha release as distribution `j2py-converter`
  with import package and CLI name `j2py`.
- README known gaps refreshed to match graduated targets/corpus constructs and remaining
  `FUTURE_TARGETS` xfail items (#69).
- Non-`this` synchronized blocks keep `with <expr>:` but warn that lock semantics need review.
- LLM system prompt aligned with the `_j2py_lock` instance-monitor pattern.
- Dependency graph resolves simple type names only when unambiguous; ambiguous `User`-style
  collisions no longer pick an arbitrary file.
- `j2py analyze` prints class inventory plus dependency graph and translation order (#69).
- `TranslationResult.confidence` documented as rule-layer coverage (unchanged after LLM).
- Agent docs (`AGENTS.md`, `CLAUDE.md`) updated for graduated vs xfail test tiers.
- Graduated target fixtures (`tests/fixtures/java/targets/`) now run in `make check` and
  CI; `make test-targets` is reserved for strict `xfail` entries in `FUTURE_TARGETS`.
- CLI `analyze` reports record types, nested declarations, and parse-error status.
- CLI translate summaries surface `parse_ok=False` and parse-error warnings.
- Directory translation aggregates per-file parse-error warnings in `batch.warnings`.

### Added
- Two-tier overload translation (ADR 0009, issue #44): chained `this(...)`
  constructor delegation and builder-style forwarding method overloads now merge
  into default parameters (immutable literals inline; constructed values become
  `None` sentinels with normalization lines). Overload groups that genuinely
  dispatch on parameter types emit each Java overload as a same-named def behind
  a vendored `@overloaded` runtime dispatcher (`j2py_runtime.py`, stdlib-only,
  written next to translated output by the CLI). The manual-dispatch
  `NotImplementedError` fallback now only remains for static overload groups and
  erased-signature collisions (e.g. `int` vs `long`).
- Java varargs parameters (`Type... name`) now translate to `*name: Type` in
  method signatures instead of being dropped.
- Deterministic translation for `instanceof` expressions, `instanceof` pattern
  variable bindings, cast expressions with review warnings, and bitwise/shift
  operators including compound bitwise assignment.
- Block lambdas (`x -> { statements; return v; }`) are now supported deterministically. They are turned into a local nested helper (`_j2py_lambda_N`) emitted near the top of the enclosing method; the helper name is used at the call site. The block body structure is preserved for reviewability.
- Complex stream pipelines/collectors: extended deterministic support for toSet, basic joining, .distinct(), .sorted() (simple or with key via method ref), and basic groupingBy (via emitted accumulation helpers using defaultdict). Builds on prior block lambda work; many cases now rewrite to clean comps or stdlib helpers (per review feedback favoring itertools/functools where used).

### Fixed
- Constructor overload merging no longer emits invalid self-referential defaults
  (`name: str = name`) or raw Java generic types in annotations when a delegating
  constructor passes its own parameters through alongside constructed values; the
  pass-through prefix rule in ADR 0009 rejects or correctly composes these.
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

- Clarified the target-test workflow: current roadmap fixtures now run as graduated
  deterministic regression checks, while future unsupported targets remain strict xfails.
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

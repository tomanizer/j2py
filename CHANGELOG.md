# Changelog

All notable changes to j2py will be documented in this file.

The format follows the repository commit types: `feat`, `fix`, `refactor`, `test`,
`docs`, `chore`, and `adr`.

## Unreleased

### Added
- Equivalence harvester now recognizes JUnit 5 trailing failure-message arguments
  (`assertEquals(expected, actual, "msg")`), keeps trailing numeric `delta` args so
  approximate float comparisons are skipped rather than mis-harvested as exact equality,
  and refuses to guess when a message position is ambiguous. Lifts NumberUtils harvest
  yield from 19 to 32 literal-oracle assertions.

### Fixed
- `String.charAt(i)` now lowers to Python indexing `s[i]` instead of an undefined
  `s.char_at(i)` method call, and is typed as returning `str`. Lands
  `StringUtils.isBlank` on the equivalence-verified surface (32/97 → 33/97).
- `charAt(i)`-returned chars are now recognized as Java `char` in expression-type
  inference, so a `charAt(i) == 'x'` comparison stays a str comparison instead of
  wrapping only the literal in `ord()` (which silently compared `str` to `int`, always
  False). Fixes `NumberUtils.isParsable` trailing-dot handling and lands it on the
  equivalence-verified surface (33/97 → 34/97).
- `String.substring(start)` and `String.substring(start, end)` now lower to Python
  slices `s[start:]` and `s[start:end]` respectively, unblocking `StringUtils.strip`
  translation. Lands `StringUtils.strip` on the equivalence-verified surface (34/97 → 35/97).

## 0.5.0b3 - 2026-06-17

Third beta pre-release. Extends rule-layer overload translation (generalized erased value
dispatch, fixed-arity vs varargs routing, broader dispatcher families), adds same-package
sibling body-local imports to break base↔derived cycles ([ADR 0021](docs/decisions/0021-sibling-type-refs-as-body-local-imports.md)),
interface static factory adapters, and assignment-as-expression desugaring; resolves
residual `Character`/`Objects` JDK static imports and an interface generic `TypeVar`
variance bug. Engineering hygiene tightens — the equivalence-verified surface and line/branch
coverage are now ratcheting CI floors — and the Spring → FastAPI/SQLAlchemy mapping cookbook
documents opt-in `annotation_map` recipes. Correctness gaps from 0.5.0b1 remain open (overload
manual-dispatch for erased-signature collisions, division numeric certainty, some JDK static
imports; ~33% of the verified equivalence surface); see **Known limitations** under 0.5.0b1.

### Added
- Positioning documentation clarifies j2py's useful scope, enterprise framework
  boundaries, and how to read Spring corpus metrics without treating node coverage as
  Spring Boot/Hibernate migration readiness (#333).
- Original JDK surface behavior fixtures demonstrate ADR 0020 deterministic lowering for
  common `String`, `Math`/`Integer`, and `List`/`Collections` usage without vendoring JDK
  source or implying a Python JDK runtime (#363).
- Optional `openjdk-java-base` corpus preset and manual Makefile target sample selected
  OpenJDK `java.base` API files from a gitignored external checkout as a scoreboard/demo,
  with no committed OpenJDK source or runtime-compatibility claim (#364).
- Expanded the `NumberUtils` equivalence surface with literal-oracle tests for
  `toFloat`/`toByte`/`toShort` (both overloads each), lifting the fixture from 6/61 to
  12/61 verified signatures and the total verified surface from 22.7% to 28.9% (#377,
  case study #372).
- Added literal-oracle equivalence assertions for `NumberUtils.compare(byte/short/int/long)`,
  lifting the fixture from 12/61 to 16/61 verified signatures and the total verified
  surface from 28/97 to 32/97, with further compare-overload cases added afterwards
  (#372, #379, #396).
- Same-package sibling type references inside method/constructor bodies now emit as
  function-local imports (`from pkg.Sibling import Sibling`) instead of module-level
  imports, breaking the base↔derived circular-import cycle (e.g. `ImmutablePair extends
  Pair` while `Pair.of()` delegates to `ImmutablePair`) that Java tolerates via lazy class
  loading but eager Python imports cannot (ADR 0021, #325, #362).
- Interfaces that declare `static` factory methods now emit working static factory
  adapters (#351).
- Assignment-as-expression desugaring: Java assignments and `++`/`--` updates in
  expression positions (return values, `while`/`if` conditions, binary/unary operands,
  ternary branches) now lower to Python walrus assignments or hoisted pre-statements;
  plus syntax-safe static imports, overload deduplication, a confidence cap, and a new
  corpus gate (#353–#357, #358).
- Erased-overload value dispatch generalized to handle numeric widening across overload
  members (#366).
- Value dispatch for fixed-arity vs varargs overload groups: runtime-checkable groups now
  route fixed signatures before varargs, while erasure collisions stay manual-dispatch
  (#408, #410).
- Extended overload dispatcher families: split static/instance name collisions, collapse
  equivalent arity-guard overloads for value dispatch, and thread cross-file inheritance
  indexes through skeleton translation (#390, #412).
- Spring → FastAPI/SQLAlchemy mapping cookbook documents opt-in `annotation_map` recipes
  (controllers, DI, JPA entities, `@Transactional`) with verified before/after pairs and
  explicit manual-port callouts (#339, #384).
- The equivalence-verified surface is now a ratcheting CI gate: the surface report writes
  `equivalence-surface.json` and `check_surface_floor.py` fails the build if the verified
  public-method count drops below the committed floor (#370, #375).
- Line-coverage floor is now enforced in required CI (`make test-cov`, `fail_under = 90`)
  rather than only reported (#371, #381).

### Changed
- Gemini SDK support now installs through the optional `gemini` extra
  (`pip install "j2py-converter[gemini]"`) instead of the default dependency set; selecting
  `--llm-provider gemini` without the extra now reports the install command (#278).

### Fixed
- Java Stream `flatMap(...)` chains with simple lambdas returning `.stream()` now lower
  to nested Python comprehensions for list and set collectors instead of falling back to
  an unsupported stream-intermediate diagnostic (#391).
- Numeric `compare(byte/short/int/long)` overload families that erase to one Python
  signature now collapse to a single method instead of emitting an impossible
  manual-dispatch TODO: the difference form (`x - y`) and the explicit sign form
  (`x < y ? -1 : 1`) are recognised as provably equivalent under unbounded Python `int`,
  and the explicit sign form is kept as the representative. A group reduced to one member
  is emitted as a plain method rather than a lone `@overloaded` registration, which would
  raise an ambiguous-dispatch error at call time (#379).
- Same-class static field reads in method bodies now qualify through the containing
  class, bitwise `|`/`&`/`^` operands preserve Java comparison precedence, and generic
  `typing.cast(...)` targets for translated classes are runtime-safe strings; the
  Commons Lang tuple case-study gaps C, D, and E now pass as regressions (#322, #323,
  #324).
- Interface generic `TypeVar` emission: when one type-parameter name (e.g. `T`) appears in
  two interfaces with conflicting variance, j2py now emits `T_co`/`T_contra` suffixed
  `TypeVar`s per interface instead of a single invariant `TypeVar("T")` that mypy rejected
  on both `Protocol` bases; unambiguous names are unchanged (#359).
- Residual JDK static imports for `Character` and `Objects` now resolve — single-char
  `Character` predicates such as `isLetter` lower without unknown-import diagnostics
  (#401, #411).

## 0.5.0b2 - 2026-06-16

Second beta pre-release. Extends rule-layer translation breadth — framework annotation
visibility and opt-in lowering, broader static-overload dispatch, and more deterministic
`.get(...)` receiver typing — plus a new enterprise corpus measurement preset. Correctness
gaps from 0.5.0b1 remain open (overload manual-dispatch, division numeric certainty, some
JDK static imports); see **Known limitations** under 0.5.0b1.

### Added
- Opt-in `annotation_map` config for framework annotation lowering: mapped annotations can
  emit decorators, imports, class bases, field comments, and constructor-injection
  parameters while unmapped annotations keep Tier 1 visibility behavior
  ([ADR 0019](docs/decisions/0019-annotation-map-framework-lowering.md), #335, #343).
- Tier 1 **annotation visibility**: stripped framework annotations on class, field, and
  method declarations now emit diagnostics and `# @...` line comments so reviewers and
  downstream tooling can see what wiring was lost; multi-line annotations stay
  syntactically valid Python comments (#334, #341).
- New **`spring-app-dense` corpus preset** sampling Spring application-layer Java filtered
  by enterprise annotation usage (`@RestController`, `@Service`, `@Entity`, …), with
  `annotation_filter.py` / `enterprise_metrics.py` reporting method-body coverage,
  annotation-only stub rate, and annotation-warning rate alongside node coverage; includes
  a CI corpus job, Makefile targets, and committed baselines (#336, #348).
- **Static `ObjectName.getInstance(...)` overload dispatcher**: emits `typing.overload`
  stubs plus one concrete `*args` implementation instead of a `j2py_runtime.overloaded`
  user method, and promotes `ObjectName` / `MalformedObjectNameException` to vendored
  runtime placeholder classes (#347, closes #300).
- **char/String `append(...)` overload dispatch**: deterministic rule-layer path for
  `StringBuilder.append(char|String)` pairs that erase to Python `str`, routing
  one-character strings through the `char` body and other values through the `String` body
  via `@overload` stubs and one concrete dispatcher (#344, closes #290).

### Changed
- **Centralized platform import policy** (`translate/rules/imports.py`): evidence-backed
  JDK/platform/external imports route through one rule-layer helper shared by skeleton
  import emission and name-resolution type bindings, preventing fake Python module paths
  like `from com.example.Integer import Integer`; adds an `Integer.compare(a, b)` shim
  ([ADR 0019](docs/decisions/0019-annotation-map-framework-lowering.md), #340, closes #298).
- `java.util.Comparator` now maps to a vendored runtime `Comparator[T]` Protocol; anonymous
  Comparator helper classes emit as concrete, instantiable local classes that satisfy the
  protocol structurally rather than subclassing an uninstantiable `typing.Protocol` (#349,
  closes #296).

### Fixed
- Static `.get(...)` receiver typing no longer flags reviewable factory/registry chains as
  ambiguous collection access:
  - `MergedAnnotations.from(annotation).get(annotationType)` stays a method call via a
    static-factory return-type table (#332, closes #306).
  - `registry.get(Customizer.class)` on a class-keyed registry stays a method call (#330,
    closes #307).
  - `this.mapping.getAttributes().get(index)` infers the declared `List<Method>` return
    type and lowers the final `.get(index)` to Python indexing (#329, closes #304).
- `java.lang.annotation.ElementType` static enum constants (`METHOD`, `CONSTRUCTOR`,
  `TYPE`) resolve through the static-field alias table, so `@Target({METHOD, …})` stays a
  reviewable comment without emitting static-import TODOs (#342, closes #289).
- Deduplicate mapped annotation class bases so a class is not emitted with a repeated base
  from overlapping `annotation_map` entries (#346).

## 0.5.0b1 - 2026-06-16

First beta pre-release. Feature set and rule-layer breadth are largely in place for
reviewable multi-file translation, but correctness gaps remain — see **Known limitations**
below. Closes the beta-readiness checklist ([#268](https://github.com/tomanizer/j2py/issues/268)).

### Changed
- PyPI trove classifier `Development Status :: 3 - Alpha` → `4 - Beta`.
- Exclude `.cursor/**` from source distributions so tracked agent skill docs do not ship on PyPI.

### Added
- End-to-end **case study** translating the multi-file Apache Commons Lang
  `org.apache.commons.lang3.tuple` package (6 files) with rule-layer-only output, linked
  and exercised by ported unit tests ([docs/CASE_STUDY.md](docs/CASE_STUDY.md),
  `tests/case_study/`, #311). 100% node coverage / 0 `__j2py_todo__`; 19 passing ported
  assertions and 3 strict xfails pinning surfaced translation gaps.
- LLM harvest **promotion pipeline**: `make harvest-promote`, `harvest-promote-issues`,
  and `harvest-promote-dry` orchestrate queue build, Gemini batch harvest, prune,
  triage, and pattern-family GitHub issue drafts (`scripts/harvest/run_harvest_promotion.py`,
  `promote_harvest_signals.py`, `signal_patterns.py`).
- Tier-A **queue builder** (`make harvest-queue`, `scripts/harvest/build_harvest_queue.py`)
  from `corpus-reports/*.json` (coverage == 1.0, syntax fail, no unhandled nodes).
- Harvest **content cache** skips re-translating unchanged sources (`java_sha256` match in
  `records.jsonl`); promotion state in `.j2py/harvest/state.json`.
- Cursor agent skill `.cursor/skills/harvest-promote/SKILL.md` for the promotion workflow.
- Gemini Flash LLM provider support via `--llm-provider gemini` and `GEMINI_API_KEY`
  ([ADR 0017](docs/decisions/0017-multi-provider-llm-backend.md), #275); Anthropic
  remains the default.
- Live Gemini Flash e2e probe via `make test-llm-gemini-e2e` (#276).
- Project config defaults for LLM provider/model selection via `llm_provider` and `model`,
  with explicit CLI flags taking precedence (#279).
- Gemini LLM completion now streams responses for large translation prompts while
  preserving cache keys, retries, fence stripping, and truncation detection (#280).
- Gemini batch harvest via `make harvest-gemini`: queue file (`--file-list`),
  `--offset` / `--limit` resume, `--skip-package-info`, throttling, and graceful 429
  quota handling in `scripts/harvest/run_llm_harvest.py`.
- Gemini token usage logging to `.j2py/harvest/usage.jsonl` with per-file and session
  summaries (`j2py/llm/usage.py`); disable with `J2PY_LLM_USAGE=0`.
- Surfaced confidence now stays below 1.00 when validation fails, structural checks fail,
  parse errors occur, or semantic warnings require review (#271).

### Fixed
- Generic cross-file superclasses (`class ImmutablePair<L, R> extends Pair<L, R>`) are no
  longer dropped: the base class is kept and its import requested via the name resolver
  ([ADR 0018](docs/decisions/0018-cross-file-class-hierarchies.md), #311).
- Static fields whose initializer references the class being defined (e.g. a `NULL`
  singleton) are deferred to a post-class module assignment instead of a class-body
  statement that raised `NameError` at import ([ADR 0018](docs/decisions/0018-cross-file-class-hierarchies.md), #311).
- Line comments inside expression lists now translate without unsupported-expression
  diagnostics or `__j2py_todo__` placeholders (#286).
- `Calendar.get(...)` now stays a Java API method call instead of being reported as an
  ambiguous collection `.get(...)` invocation (#288).

### Known limitations

The multi-file Commons Lang `tuple` case study ([docs/CASE_STUDY.md](docs/CASE_STUDY.md))
translates at 100% node coverage with zero `__j2py_todo__` markers, yet end-to-end
execution surfaced correctness gaps that coverage alone cannot see. The following remain
open at this release:

- **Static field reads inside methods** are emitted as bare names instead of
  class-qualified references (`return NULL` vs `return ImmutablePair.NULL`) — #322.
- **Bitwise `|`, `&`, and `^` with comparison operands** can drop Java precedence when
  lowered to Python (`!=` tighter than `|` in Java; `|` tighter than `is not` in Python)
  — #323.
- **`cast()` to a generic translated class** evaluates a subscripted type at runtime;
  translated classes without `Generic[...]` / `__class_getitem__` raise `TypeError` — #324.
- **Cross-file base⇄derived class hierarchies** can form circular imports when a base
  factory delegates to a concrete subclass and the subclass extends the base (e.g.
  `Pair` ↔ `ImmutablePair`). Directory translation emits eager module-level imports on
  both edges; multi-file inheritance projects may need manual import fixups until
  function-local sibling imports land — #325.

Multi-file translation is **not** flawless at beta: the case study harness links modules
into a single namespace to exercise the output; that is test scaffolding, not a general
import fix.

## 0.4.0a1 - 2026-06-15

### Changed
- Refresh [docs/PRD.md](docs/PRD.md) — confidence semantics, expanded CLI, `verify/` stage,
  regression suites (F9–F10), updated success criteria.
- Add [docs/decisions/AUDIT-2026-06-15.md](docs/decisions/AUDIT-2026-06-15.md) maturity
  audit and [docs/README.md](docs/README.md) documentation index.
- Split `j2py/translate/classes.py` into focused `class_*` modules (`class_enums`,
  `class_interfaces`, `class_annotations`, `class_members`, `class_methods`,
  `class_nested`) with `classes.py` as the public facade; behavior-neutral refactor.
- Split `j2py/translate/expressions.py` into focused `expr_*` modules (`expr_access`,
  `expr_calls`, `expr_lambdas`, `expr_objects`, `expr_ops`, `expr_streams`,
  `expr_types`) with `expressions.py` as the public facade; behavior-neutral refactor
  (#232).
- Documentation reframes the benchmark corpus as a multi-library measurement harness
  (Guava, Commons Lang, Jackson, Caffeine, Spring, and construct fixtures) instead of
  centering Spring Framework as the primary scoreboard (#201).
- Corpus scoreboard docs, CI, and PR template now treat `make corpus-hotspots` as the
  multi-library dashboard; `spring-broad` is documented as exploratory without a
  committed baseline (#205).
- Future translation target guidance now documents the intentionally empty state and the
  manual triage responsibility for adding strict xfail contracts (#253).

### Added
- YAML/TOML/`pyproject.toml` configuration loading with strict schema validation,
  helpful unknown-key suggestions, and documented config schema (#125).
- Incremental directory translation state, `j2py watch`, dashboard generation,
  machine-readable `--json` output, and parallel directory translation worker controls
  for developer-experience workflows (#126, #127, #128, #129).
- Behavior-equivalence corpus: ~60 curated Java programs under `tests/fixtures/behavior/`
  that compile + run with Java, translate rule-layer-only (no LLM), then run as Python and
  assert byte-identical stdout/stderr/return-code. The corpus is auto-discovered (drop a
  `<case>/Main.java` directory to add one), guarded by a minimum-size check in the normal
  suite, and runs as a JDK-backed CI gate (`.github/workflows/behavior.yml`) and a release
  gate (`make release-check`). Documents the deterministic rule layer's runtime-correct
  envelope (#120).
- Abstract Java classes now translate to Python `ABC` subclasses, with abstract methods
  emitted as `@abstractmethod` ellipsis stubs (#115).
- Common Java standard-library static calls and constants now translate to Python
  equivalents, including `Math.*`, numeric parse/string helpers, collection helpers,
  array factories, and `Objects.isNull/nonNull` (#113).

### Fixed
- Parenthesized ternary and switch expressions used as division operands now retain
  grouping, avoiding Python precedence drift in generated output (#249).
- Auto-discovery now ignores executable `j2py_config.py` files; Python config remains
  available only through explicit trusted `--config j2py_config.py` use (#180).
- Receiverless calls from static methods to sibling static methods now emit
  class-qualified calls instead of bare function names, avoiding runtime `NameError`
  in utility classes (#187).
- Class references in expression position now retain class-name casing and request
  generated or configured imports instead of emitting lowercased unbound identifiers
  (#188).
- LLM-enabled directory translation now avoids per-file ruff/mypy prevalidation for
  full-coverage rule-layer outputs, relying on syntax-only routing plus batched final
  validation instead (#181).
- Guava dense corpus excludes `Platform.java` because tree-sitter-java leaves ERROR nodes
  on Jspecify type-use `@Nullable` annotations before varargs; the file still translates
  at full coverage but would otherwise be the sole `parse_ok=false` entry (#160).
- Anonymous classes in static and instance field initializers now emit nested helper
  classes at class or `__init__` scope instead of the local-helper diagnostic (#159).
- Static two-argument `equals` helpers (`Objects.equals`, `Arrays.equals`, static-import
  `equals`, and similar utility calls) now translate to Python `==` instead of emitting
  an unexpected-argument-count diagnostic (#156).
- Static overload groups with distinguishable Python signatures now translate through the
  vendored runtime dispatcher, receiverless same-group static calls are class-qualified,
  and boxed primitive forwarding overloads merge without manual-dispatch diagnostics
  (#88).
- Comment-only method/constructor bodies and metadata-only nested classes now emit
  `pass`, and multiline Java wildcard generic signatures normalize to valid Python
  annotations instead of leaking `?` syntax (#153).
- LLM calls now send the system prompt as an Anthropic prompt-cache block, enabling
  warm calls to reuse the cached prompt instead of resending the fixed instructions (#116).
- Static imports for known Java members now resolve at use sites, including
  `Math` constants/functions and `Collections.unmodifiableList`; unknown static imports
  emit an explicit `TODO(j2py)` diagnostic instead of silently producing an undefined
  name (#114).
- Directory translation now batches final validation into one ruff run and one mypy run,
  avoiding per-file subprocess fan-out while preserving per-file validation results (#117).
- Directory translation now passes compact signatures from already-translated directly
  imported sibling classes into subsequent LLM completion context (#118).
- Rule-layer import emission now uses tracked import requirements instead of scanning
  rendered Python text, avoiding false-positive imports from comments and strings (#119).
- Java cast expressions now add reviewer-visible trailing `# cast: (...)` comments when
  line comments are enabled, with numeric narrowing casts marked explicitly (#112).
- Java unsigned right shift (`>>>` and `>>>=`) lowers to masked Python shifts for
  known `int`/`long` widths, with an explicit 32-bit assumption warning only when the
  operand width is unknown (#109).
- Java bitwise complement (`~`) now translates for integral operands while preserving
  explicit grouping around lower-precedence operands (#158).

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
- ADR 0015: `synchronized(this)` translates to `self._j2py_lock` with `threading.Lock()`
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

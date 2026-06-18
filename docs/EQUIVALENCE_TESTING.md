# Equivalence testing — design and phased plan

Status: **Active — Phase 1 (complete)** (decision recorded in [ADR 0014](decisions/0014-equivalence-differential-testing.md)).

**What is running now.** `tests/equivalence/` is live and runs in `make check` (no JDK,
no LLM). The current surface covers Commons-Lang fixtures (`BooleanUtils`, `CharUtils`,
`NumberUtils`, and focused `StringUtils` literal-oracle checks), Guava `Strings`, plus a
Guava-style `GuavaPrecedenceMath` fixture that exercises the Phase-1 operator-precedence
exit criterion. The harness infrastructure lives in `tests/equivalence/harness.py`
(translate → load → stub) and `tests/equivalence/comparator.py` (normalisation spec —
float approximation, integer overflow semantics, exception mapping). Overloaded methods
that are now backed by deterministic dispatcher behavior are included in the public
surface; any remaining skipped rows are explicit fixture-level exclusions. `make
test-equivalence` currently selects **1,738 equivalence items**: 1,732 passing and six
`NumberUtils.createNumber` edge cases skipped. Run alone with:

```bash
make test-equivalence         # just the equivalence gate
make equivalence-report       # equivalence gate + verified-surface JSON/table
make harvest-equivalence TEST_SOURCE=... TARGET_CLASS=... JAVA_FIXTURE=... WRITE=/tmp/draft.py
make check                    # includes equivalence (along with all other tests)
```

This document describes how j2py verifies that translated Python is **behaviourally
equivalent** to the original Java, at scale, on real libraries — closing the gap left by
the node-coverage scoreboards, which measure mechanical completion and syntactic validity
but never execute the output.

## 1. Problem and goals

**Problem.** Node coverage and syntax success cannot see silent behavioural bugs. A real
example: Guava `MinMaxPriorityQueue` translates `(oldCapacity + 1) * 2` to
`old_capacity + 1 * 2` (22 → 12) while scoring full coverage, valid syntax, zero
warnings.

**Goal.** A gate that, on real library code, runs translated Python and the original Java
on the same inputs and flags every behavioural divergence — and that runs cheaply enough
to gate every commit.

**Non-goals.**
- Proving equivalence (undecidable). We produce strong, input-bounded evidence.
- Verifying untranslatable surface (reflection, JNI, threads, time, randomness, I/O).
  These are explicitly bucketed and counted, not tested.
- Replacing node-coverage scoreboards. Those stay as **breadth** metrics; this adds the
  **correctness** metric.

## 2. Core principle: the transpiler must not grade its own homework

A unit test is an equivalence check only if its oracle is **independent of j2py**. If the
same transpiler produces both the code under test and the expected value, a single bug can
corrupt both sides and cancel:

```
// Java production:  int grow(int x) { return (x + 1) * 2; }

assertEquals(22,        grow(10));   // literal oracle   → assert grow(10) == 22  → FAILS (bug caught)
assertEquals((x+1)*2,   grow(x));    // expression oracle → x + 1*2 == x + 1*2     → PASSES (bug hidden)
```

Two independence requirements follow:

- **Oracle values come from Java, not from re-transpiled expressions.** Literals are
  already JVM-independent. Computed expecteds must be folded to JVM-captured constants or
  dropped.
- **The assertion/harness layer is a trusted hand-written shim**, deterministic and
  independently tested, never routed through the rule layer or LLM. It is the harness's
  single trust anchor and carries an outsized test burden.

## 3. Architecture — two speeds

```
        ┌──────────────────── ORACLE PASS (slow, needs JDK + corpus build) ─────────────────┐
        │  upstream JUnit suite                                                              │
        │       │ run under Java, instrumented                                               │
        │       ▼                                                                            │
        │  capture: expected constants + (method, args→result) tuples + method coverage      │
        │       │                                                                            │
        │       ▼                                                                            │
        │  golden vectors  ──────────────────────────► committed JSON fixtures               │
        └────────────────────────────────────────────────────────────────────────────────-─┘
                                              │
        ┌───────────────── VERIFICATION PASS (fast, CPython only, every commit) ─────────────┐
        │  harvested test scaffold (j2py) + JUnit→pytest shim (trusted)                       │
        │       │ run against translated Python, asserts use golden constants                 │
        │       ▼                                                                            │
        │  pass / DIVERGENCE  ──────────────────────► equivalence-verified surface metric     │
        └────────────────────────────────────────────────────────────────────────────────-─┘
```

The slow pass refreshes fixtures nightly/on-demand. The fast pass is ordinary pytest, no
JVM, and gates PRs like the existing behaviour corpus.

## 4. Components

| Component | Responsibility | Trust level |
|---|---|---|
| **Test harvester** | Select cleanly-translatable upstream unit tests; classify each by oracle type (literal vs expression) and testability (pure vs excluded). | Normal |
| **JUnit→pytest shim** | Fixed mapping of assertion/lifecycle constructs. Deterministic, hand-written, independently unit-tested, never LLM-routed. | **Trusted (max)** |
| **Oracle runner** | Run the instrumented Java suite; capture expected constants, optional arg→result tuples, and Java method coverage. | Normal |
| **Correspondence manifest** | Emitted by j2py at translation time: `Java FQN + signature → Python module + qualname`. Links oracle to verifier. | Normal |
| **Dependency resolver / stubber** | Make a translated class importable in isolation: translate its dependency closure, or inject stubs for helpers the tested methods don't exercise, and supply any reference the translation left unimported. Surfaced as mandatory by the tracer bullet (§8). | Normal |
| **Comparator / normalizer** | The written equivalence relation: numeric/overflow, collection ordering, exception mapping, null/None. | High |
| **Surface metric** | Compute equivalence-verified surface % and size the untestable bucket. | Normal |

## 5. Test tiers and the dropped-expression decision

| Tier | Example | Treatment |
|---|---|---|
| **Literal-oracle** | `assertEquals(3, IntMath.log2(8))` | Translate directly. Oracle is JVM-independent. **Phase 1.** |
| **Expression-oracle** | `assertEquals((x+1)*2, grow(x))` | **Dropped initially.** Build JVM constant-folding *only if* coverage shows important methods unverified (ADR 0014 §5). |
| **Excluded** | needs Mockito / reflection / I/O / threads / time | Not harvested; counted in the untestable bucket. |
| **Fuzzed (additive)** | generated inputs over a pure method | Property-based; oracle = direct Java invocation. Secondary breadth source. |

Rationale for dropping expression-oracle first: it removes the correlated-failure risk
with zero extra infrastructure, and keeps the first verified-surface number honest. The
fold step is demand-driven — we let coverage data, not speculation, justify the cost.

## 6. Semantic traps the comparator must encode

These are real Java↔Python differences; surfacing them is the point of the gate, not a
nuisance. Each is a normalization rule (or a confirmed translation bug):

- **Integer width / overflow** — Java `int`/`long` wrap at 2³¹-1/2⁶³-1; Python ints are
  unbounded. Decide per ADR follow-up whether the comparator models Java modular
  arithmetic or treats every overflow divergence as a j2py bug to fix.
- **Integer division and `%` sign** — already a known rule-layer bug class.
- **char/byte arithmetic, float formatting, NaN.**
- **Unordered collections** — `HashMap`/`HashSet` iteration order differs; compare as
  map/set, not sequence.
- **Exceptions** — compare mapped exception *class* (`IllegalArgumentException` ↔
  `ValueError`) and optionally message, not just return values.
- **null vs None, autoboxing identity, String.hashCode order effects.**

The comparator is a reviewable spec module — it documents what "equivalent" means.

## 7. Phased plan

### Phase 0 — Bridge (cheap, immediate)
Mechanically mine known bug-class patterns (parenthesized arithmetic, compound int-div,
enum/static refs) from the real corpora into the **existing** `tests/fixtures/behavior/`
corpus as small `main`-wrapped programs. No new infrastructure; immediately widens the
runtime gate around classes we already know fail. Bridges to the real harness.

### Phase 1 — Walk: literal-oracle harvest on the pure surface
Target **dependency-light pure utility classes** — the tracer bullet (§8) showed even a
coverage=1.0 class is unimportable until its cross-class dependencies are resolved, and
that Guava's math tests are mostly expression-oracle (`BigInteger` cross-checks), so
**Commons-Lang `CharUtils`/`NumberUtils`/`StringUtils` are better first targets than Guava
math**.

**Done:**
- ✅ Harness infrastructure (`tests/equivalence/harness.py`): `translate_rule_layer`,
  `load_translated_module`, `install_stub_class`, `install_java_lang_stubs`
- ✅ `CharUtils` fixture + 1,622 literal-oracle assertions running in `make check`
- ✅ `equivalence` pytest marker registered and excluded from `behavior`/`live_llm` filter
- ✅ Generalised dependency stubber: `install_stub_class(fqn, name, stub)` replaces the
  hardcoded `install_array_utils_stub_package`; `install_java_lang_stubs()` covers the
  10 module chains needed by `NumberUtils`
- ✅ `NumberUtils` fixture with structural and behavioral literal-oracle assertions
- ✅ Comparator normalization module (`tests/equivalence/comparator.py`): integer overflow
  spec, float approximation helpers, exception mapping helper — independently unit-tested
- ✅ Guava-style operator-precedence fixture: `GuavaPrecedenceMath` catches the
  `(a+b)*c -> a+b*c` regression at the equivalence level with literal-oracle assertions
- ✅ Literal-oracle draft harvester (`scripts/harvest/harvest_equivalence_tests.py`),
  with `make harvest-equivalence`, for conservative upstream JUnit-to-pytest draft
  generation against declared static fixture methods
- ✅ CharUtils overload coverage, NumberUtils min/max/isNumber, create-family methods,
  BigDecimal conversions, `createNumber`, plus new BooleanUtils and Guava Strings
  fixture coverage are now represented in the public-surface floor. The current floor is
  **120/152 public signatures**.

**Remaining:**
- Emit the correspondence manifest from the translator (Java FQN → Python qualname map)
  — Phase 2 prerequisite; not blocking current gate

### Phase 2 — Measure and decide on folding
- ✅ Add Java method-coverage capture to the oracle pass.
- ✅ Report equivalence-verified surface % per library and size the untestable bucket.
- **Decision gate:** if coverage shows important methods unverified *because* their tests
  were expression-oracle, build the JVM constant-folding step. Otherwise, don't.

### Phase 3 — Run: scale and golden vectors
- Generalize input handling to value objects/records; expand record-replay across whole
  suites.
- Freeze golden vectors as committed fixtures so the every-commit path is CPython-only.
- Make equivalence-verified surface a headline scoreboard alongside node coverage.
- Add property-based fuzzing as the additive breadth source.

## 8. Tracer-bullet validation (2026-06-14)

Before committing to the harness build, the loop was proven end-to-end by hand on one real
class: Commons-Lang `CharUtils` translated rule-layer-only, with six literal-oracle
assertions hand-ported from `CharUtilsTest.java` and run as pytest.

Under the production config (`add_defaults().build()`) `CharUtils` scores **coverage ≈
0.67**, and *all* of the unhandled third is overload manual-dispatch (`toChar`,
`toIntValue`, … — loud, by-design `NotImplementedError` fallbacks). Crucially, the two
**silent** bugs below live in the *handled* 67% — counted as success, emitted wrong. That
is the whole thesis: handled ≠ correct, and node coverage cannot see it.

**Result: 3 pass / 3 fail.** Correct translations passed (`compare`, `isAscii`,
`isAsciiNumeric`); three real divergences were caught:

| Method | Divergence |
|---|---|
| `isAsciiAlpha` | `NameError` — sibling static methods called as **bare unqualified names** (`is_ascii_alpha_upper(ch)` instead of `CharUtils.is_ascii_alpha_upper(ch)`) |
| `toIntValue` | `NotImplementedError: j2py overload dispatch required` — overload group falls back to a runtime-raising stub |
| `toChar` | same overload-dispatch stub (legitimate where Java types erase to the same Python type; see open question 1) |

**Obstacles the harness must handle (the real payoff — found by doing, not guessing):**

1. **Dependency closure is mandatory.** `CharUtils` will not import without
   `ArrayUtils.setAll`; single-file translation is not runnable in isolation.
2. **Unresolved references are emitted without imports.** The translation referenced
   `array_utils.set_all(...)` but emitted no `import` for it.
3. **Rule-layer-only ≠ importable for real classes — but the cause is dependencies, not
   coverage.** The earlier "needs LLM" conclusion from `StringUtils` was an output-size
   artifact (9.6k LOC exceeds the LLM token budget), not a general truth. `CharUtils`
   imports from rule-layer output alone once its one dependency is stubbed, despite scoring
   only ~0.67 (the unhandled third is all overload manual-dispatch, which does not block
   the non-overloaded tested methods).
4. **Overloaded methods raise at runtime**, so any harvested test hitting one fails on the
   stub, not on logic. Exclude overloaded methods from the first surface or resolve dispatch.

A manual reference implementation of this loop was produced in this session (translate
`CharUtils` → stub `ArrayUtils` → run six ported literal-oracle assertions); it should be
committed under `tests/fixtures/equivalence/` as the Phase 1 harvester seed.

## 9. Metrics (the new scoreboard)

Per library, per run:
- **Equivalence-verified surface %** — public methods with ≥1 passing differential test ÷
  all public Java method signatures in the measured fixture.
- **Untestable bucket** — count and reasons (reflection / threads / time / random / I/O).
- **Inputs per verified method** — confidence grows with volume.
- **Divergences** — the gold; each opens a bug ticket. Trend to zero.

The implemented report publishes both denominators:

- **Verified public surface %** — public Java method signatures with ≥1 passing
  literal-oracle pytest item ÷ all public Java method signatures in the fixture.
- **Verified testable surface %** — the same numerator ÷ public signatures minus the
  explicitly untestable bucket.

Run `make equivalence-report` to generate `corpus-reports/equivalence-surface.json` and
print the per-fixture table. The target also checks the generated report against the
checked-in ratchet floor at
`tests/fixtures/equivalence/equivalence-surface-floor.json`. CI writes the same JSON
artifact from the Python 3.11 test job, checks it against that floor, and uploads the
artifact. Tests opt into the numerator with
`@pytest.mark.equivalence_surface("<Fixture>.java", "<Class.method(Signature)>")`; the
pytest hook records only markers from passing test items, so strict xfail divergences and
failed assertions do not inflate the metric.

### Ratchet workflow

The floor enforces both verified method counts and the verified public/testable ratios for
the total surface and each library. A PR can increase the denominator by adding measured
surface, but it must either add enough passing literal-oracle tests to preserve the floor
or intentionally update the floor after review.

To raise the floor after new equivalence tests land:

```bash
make equivalence-report
uv run --extra dev python scripts/equivalence/check_surface_floor.py \
  corpus-reports/equivalence-surface.json --update-floor
git diff tests/fixtures/equivalence/equivalence-surface-floor.json
```

Do not lower the floor in ordinary feature work. If the measured Java fixture surface
changes for a legitimate reason, call that out in the PR and keep the generated
`equivalence-surface.json` artifact as evidence.

Current public-surface snapshot:

By library:

| Library | Verified / public | Public surface | Verified / testable | Untestable |
|---|---:|---:|---:|---:|
| `commons-lang` | 109/141 | 77.3% | 109/141 (77.3%) | 0 |
| `guava` | 11/11 | 100.0% | 11/11 (100.0%) | 0 |
| **Total** | 120/152 | 78.9% | 120/152 (78.9%) | 0 |

By fixture:

| Fixture | Verified / public | Public surface | Verified / testable | Untestable |
|---|---:|---:|---:|---:|
| `BooleanUtils.java` | 15/46 | 32.6% | 15/46 (32.6%) | 0 |
| `CharUtils.java` | 23/23 | 100.0% | 23/23 (100.0%) | 0 |
| `GuavaPrecedenceMath.java` | 2/2 | 100.0% | 2/2 (100.0%) | 0 |
| `NumberUtils.java` | 60/61 | 98.4% | 60/61 (98.4%) | 0 |
| `StringUtils.java` | 11/11 | 100.0% | 11/11 (100.0%) | 0 |
| `Strings.java` | 9/9 | 100.0% | 9/9 (100.0%) | 0 |
| **Total** | 120/152 | 78.9% | 120/152 (78.9%) | 0 |

## 10. Open questions

1. **Overflow semantics** — comparator models Java modular arithmetic, or every overflow
   divergence is a j2py bug to fix? (Affects whether translated output is idiomatic
   Python or width-faithful.)
2. **Expression-oracle folding** — confirmed deferred (ADR 0014 §5); revisit only on
   Phase 2 coverage evidence.
3. **Assertion-library surface** — Guava/Jackson use Truth/AssertJ; decide shim coverage
   vs. restricting harvest to plain JUnit assertions.
4. **Fixture refresh cadence** — nightly vs. on-translation-change; who owns the JDK
   oracle environment in CI.

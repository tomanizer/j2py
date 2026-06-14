# Equivalence testing — design and phased plan

Status: **Design** (decision recorded in [ADR 0014](decisions/0014-equivalence-differential-testing.md)).

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
- Build the trusted JUnit→pytest shim and its independent unit tests first.
- Emit the correspondence manifest from the translator.
- Harvest literal-oracle unit tests for pure utility classes (Guava `IntMath`/`Strings`/`Preconditions`,
  Commons `StringUtils`). Run translated tests against translated code.
- Stand up the comparator's first normalization rules (numeric, exceptions).
- **Exit criterion:** the Guava precedence bug (and the 5 tracked xfails) are caught by
  this gate, not just the toy corpus.

### Phase 2 — Measure and decide on folding
- Add Java method-coverage capture to the oracle pass.
- Report equivalence-verified surface % per library and size the untestable bucket.
- **Decision gate:** if coverage shows important methods unverified *because* their tests
  were expression-oracle, build the JVM constant-folding step. Otherwise, don't.

### Phase 3 — Run: scale and golden vectors
- Generalize input handling to value objects/records; expand record-replay across whole
  suites.
- Freeze golden vectors as committed fixtures so the every-commit path is CPython-only.
- Make equivalence-verified surface a headline scoreboard alongside node coverage.
- Add property-based fuzzing as the additive breadth source.

## 8. Metrics (the new scoreboard)

Per library, per run:
- **Equivalence-verified surface %** — public methods with ≥1 passing differential test ÷
  testable public methods.
- **Untestable bucket** — count and reasons (reflection / threads / time / random / I/O).
- **Inputs per verified method** — confidence grows with volume.
- **Divergences** — the gold; each opens a bug ticket. Trend to zero.

## 9. Open questions

1. **Overflow semantics** — comparator models Java modular arithmetic, or every overflow
   divergence is a j2py bug to fix? (Affects whether translated output is idiomatic
   Python or width-faithful.)
2. **Expression-oracle folding** — confirmed deferred (ADR 0014 §5); revisit only on
   Phase 2 coverage evidence.
3. **Assertion-library surface** — Guava/Jackson use Truth/AssertJ; decide shim coverage
   vs. restricting harvest to plain JUnit assertions.
4. **Fixture refresh cadence** — nightly vs. on-translation-change; who owns the JDK
   oracle environment in CI.

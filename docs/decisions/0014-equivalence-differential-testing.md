# ADR 0014 — Equivalence verification via harvested-test differential testing

**Date:** 2026-06-14
**Status:** Accepted (implementation phased — see [docs/EQUIVALENCE_TESTING.md](../EQUIVALENCE_TESTING.md))

## Context

j2py's product promise is **semantic and functional equivalence** between the Java
source and the translated Python (PRD). Today nothing measures that at scale:

- The corpus scoreboards (Spring, Guava, Jackson, Commons-Lang, Caffeine) measure
  **rule-layer node coverage + does-the-output-parse**, not runtime behaviour. A file
  can score `coverage = 1.0`, `syntax_ok = True`, zero warnings, and still be wrong.
- This is not hypothetical. On real Guava
  (`MinMaxPriorityQueue.java`), `(oldCapacity + 1) * 2` translates to
  `old_capacity + 1 * 2` — a silent precedence bug (22 vs 12) inside a file the dense
  baseline rates at full coverage. The flagship metric is blind to the exact bug class
  the tool exists to avoid, because the scoreboard rewards *handled* nodes, and the bug
  lives in the handled bucket.
- The only gate that exercises real behaviour is the behaviour-equivalence corpus
  (`tests/fixtures/behavior/`, ~78 hand-written programs ≤ ~20 LOC). It is valuable but
  tiny, and deliberately avoids the buggy envelope (5 cases are tracked strict-xfails).

We need an equivalence gate that (a) runs on real library code, (b) scales in CI, and
(c) cannot be fooled by the transpiler's own blind spots.

## Decision

Adopt **cross-language differential testing at method granularity**, with Java as the
oracle, sourced primarily by **harvesting real upstream unit tests** and running their
translations against the translated code.

1. **Granularity is the method, not the program.** Equivalence is checked per
   translated method/function: same inputs in, compare outputs. Whole-program
   stdout-diffing does not apply to libraries with no entry point.

2. **Java is the oracle.** We never assert Python correctness in the abstract — only
   that Python matches what Java does on given inputs.

3. **Primary input source is harvested upstream tests.** Established libraries ship
   thousands of high-quality unit tests carrying maintainer intent and edge cases. We
   translate the test *scaffold* with j2py and run it against the translated production
   code. Property-based fuzzing is a secondary, additive source for breadth.

4. **Oracle independence is mandatory — the transpiler must not grade its own
   homework.** Using j2py to translate both the code and a test whose *expected value is
   an expression* lets one transpiler bug corrupt both sides and cancel (e.g.
   `assertEquals((x+1)*2, grow(x))` → `x + 1*2 == x + 1*2`, a false pass). Therefore:
   - **Literal-oracle tests** (`assertEquals(22, grow(10))`) are safe to translate
     directly — the literal is a JVM-independent oracle.
   - **Expression-oracle tests** must have their expected values replaced with constants
     captured from a real Java run, or be excluded. They are **never** verified by a
     re-transpiled expression.

5. **Expression-oracle tests are dropped initially.** We start with literal-oracle tests
   plus fuzzing. We build the Java-run constant-folding step **only if** coverage
   measurement shows we are losing important production methods by dropping them. This
   keeps the first increment cheap and the verified surface honest.

6. **The JUnit→pytest assertion shim is a trusted, hand-written core.** Assertion and
   harness translation (`assertEquals`→`assert ==`, `assertThrows`→`pytest.raises`,
   `@Test`→function, `@Before`→fixture) is a small fixed mapping implemented
   deterministically, unit-tested independently, and **never routed through the rule
   layer or the LLM**. A bug here would mask code bugs, so it is the most-audited code in
   the harness.

7. **Two-speed execution via golden vectors.** A slow **oracle pass** (needs a JDK and
   the corpus's own build) captures expected values / recorded I/O as committed JSON
   fixtures. A fast **verification pass** replays them against the translated Python in
   plain CPython, runnable on every commit with no JVM in the hot path.

8. **New headline metric: equivalence-verified surface.** Report, per library, the
   fraction of the translated public method surface that has ≥1 passing differential
   test, alongside the size and reasons of the **untestable bucket** (reflection,
   threads, time, randomness, I/O). This metric — not node coverage — becomes the
   correctness scoreboard. Node coverage stays as a breadth metric.

## Consequences

+ Produces a real equivalence signal on real library code; each divergence is a concrete
  transpiler bug (would have caught the Guava precedence bug mechanically).
+ Scales in CI: the every-commit path is CPython-only golden-vector replay.
+ Harvested tests bring realistic, edge-case-rich inputs for free and encode the surface
  that actually matters.
+ The verified-surface metric is defensible against the product's stated mission in a way
  node coverage is not.
− The oracle pass requires a JDK and building each corpus library; it runs occasionally
  (nightly / on-demand), not per-PR.
− The trusted shim is a single point of trust; a defect there silently weakens the gate,
  so it carries an outsized testing burden.
− Initial coverage is limited to the cleanly-harvestable, mostly-pure method subset;
  tests needing Mockito/reflection/I/O are excluded, and expression-oracle tests are
  dropped until proven necessary.
− A passing literal/JVM-oracle test proves equivalence on the tested inputs only — it is
  evidence, not a proof. Confidence grows with input volume, not certainty.

## Validation

A 2026-06-14 tracer bullet proved the loop end-to-end on Commons-Lang `CharUtils`
(rule-layer-only): six literal-oracle assertions hand-ported from `CharUtilsTest` ran as
pytest, passing on correct translations and catching three real divergences (bare
static-call `NameError`; two overload-dispatch stubs). The two silent bugs sit in the
*handled* portion of the rule layer's output — `CharUtils` scores ~0.67 coverage under the
production config, the unhandled third being overload manual-dispatch — so node coverage
rates the buggy code as success. The exercise also surfaced that the harness must resolve a
class's dependency closure before it can import, which reshaped Phase 1. See
[docs/EQUIVALENCE_TESTING.md §8](../EQUIVALENCE_TESTING.md).

## References

- Project audit, 2026-06-14 (measurement–mission gap; confirmed Guava precedence
  divergence)
- [docs/EQUIVALENCE_TESTING.md](../EQUIVALENCE_TESTING.md) — phased design and milestones
- [docs/BEHAVIOR_CORPUS.md](../BEHAVIOR_CORPUS.md) — the existing runtime gate this extends
- [docs/CORPUS_SCOREBOARD.md](../CORPUS_SCOREBOARD.md) — the node-coverage scoreboard this
  complements
- [PRD.md](../PRD.md) — semantic-equivalence goal; execution-equivalence listed as a
  prior non-goal this ADR consciously revisits

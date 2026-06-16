# Case study — translating Apache Commons Lang `tuple` end-to-end

Status: **Active** (issue [#311](https://github.com/tomanizer/j2py/issues/311), beta-readiness
checklist item from [#268](https://github.com/tomanizer/j2py/issues/268)).

This is the first real-world, multi-file case study: a coherent open-source Java module
translated by the rule layer, linked, and exercised by unit tests ported from the
upstream test suite. Its purpose is the beta throughline — *not just "can we translate
it" but "can we tell, honestly, which of the output is correct."*

## The subject

`org.apache.commons.lang3.tuple` from Apache Commons Lang — six interdependent files:

| File | Role | Cross-file dependency |
|---|---|---|
| `Pair.java` | abstract base; implements `Map.Entry`, `Comparable` | — |
| `Triple.java` | abstract base; implements `Comparable` | — |
| `ImmutablePair.java` | concrete, `extends Pair<L, R>` | inherits `Pair` |
| `MutablePair.java` | concrete, `extends Pair<L, R>` | inherits `Pair` |
| `ImmutableTriple.java` | concrete, `extends Triple<L, M, R>` | inherits `Triple` |
| `MutableTriple.java` | concrete, `extends Triple<L, M, R>` | inherits `Triple` |

Chosen because it is small and reviewable, yet genuinely non-trivial: two inheritance
hierarchies, a base factory that delegates to a concrete subclass (`Pair.of` →
`ImmutablePair.of`), `equals`/`hashCode`/`compareTo`/`toString`, and the `Map.Entry`
view. The sources are vendored under
[`tests/fixtures/case_study/commons_lang_tuple/java/`](../tests/fixtures/case_study/commons_lang_tuple/java)
(Apache License 2.0, headers intact) so the case study runs hermetically in `make check`
without a corpus checkout.

## What the rule layer produced

Rule layer only, no LLM (`translate_file(..., use_llm=False)`):

| File | Node coverage | Unhandled | `__j2py_todo__` | Semantic warnings | Surfaced confidence |
|---|---|---|---|---|---|
| Pair | 100.0% | 0 | 0 | 30 | 0.99 |
| Triple | 100.0% | 0 | 0 | 23 | 0.99 |
| ImmutablePair | 100.0% | 0 | 0 | 23 | 0.99 |
| MutablePair | 100.0% | 0 | 0 | 20 | 0.99 |
| ImmutableTriple | 100.0% | 0 | 0 | 21 | 0.99 |
| MutableTriple | 100.0% | 0 | 0 | 21 | 0.99 |
| **Total** | **100.0%** | **0** | **0** | **138** | — |

Every node is handled and no `__j2py_todo__` markers are emitted. The confidence reads
**0.99, not 1.00**, because the [#309](https://github.com/tomanizer/j2py/issues/309)
confidence clamp lowers it whenever semantic warnings are present — exactly the honest
signal beta requires: *handled is not the same as correct.*

## The throughline: 100% node coverage ≠ runnable

Node coverage measures mechanical completion. Executing the output is a different bar. The
case study surfaced **five** real correctness gaps that a coverage scoreboard cannot see.
Two were fixed in this change; three are documented below as follow-ups.

### Fixed in this change

**Gap A — class-body forward self-reference.** `private static final ImmutablePair NULL =
new ImmutablePair<>(null, null)` translated to a class-body statement
`NULL = ImmutablePair(None, None)` that runs *before* the class name is bound →
`NameError` at import. Fixed: a static field whose initializer references the class being
defined is now deferred to a post-class module assignment,
`ImmutablePair.NULL = ImmutablePair(None, None)`.

**Gap B — generic cross-file superclass dropped.** `class ImmutablePair<L, R> extends
Pair<L, R>` translated to `class ImmutablePair:` — the base class was silently dropped
because the `extends` clause wraps the type name in a `generic_type` node the extractor
did not descend into. With no base, every inherited method (`getKey`, `getValue`,
`equals`, `hashCode`, `compareTo`, `toString`) was lost. Fixed: generic supertypes are
extracted and the base class import requested via the deterministic name resolver
(`class ImmutablePair(Pair):` + `from ...tuple.Pair import Pair`).

Both fixes have rule-layer fixture tests in
[`tests/translate/skeleton/test_cross_file_classes.py`](../tests/translate/skeleton/test_cross_file_classes.py).

### Surfaced, tracked as follow-ups

**Gap C — static field reads emitted unqualified.** Inside a method, `return NULL` is
emitted as a bare name rather than `return ImmutablePair.NULL`, so it cannot see the class
attribute (`NameError`). Affects `null_pair()` and `empty_array()`.

**Gap D — bitwise `|`/`&`/`^` precedence with comparison operands.** `ImmutableTriple.of`
contains (verbatim from commons-lang) `left != null | middle != null || right != null`.
Java binds `!=` tighter than `|`; Python binds `|` tighter than `is not`, so the
translation `left is not None | middle is not None` mis-parses into a chained comparison
and raises `TypeError`. Same precedence-preservation class as the Guava `(a+b)*c` work
([#310](https://github.com/tomanizer/j2py/issues/310)).

**Gap E — `cast()` to a generic translated class.** `Triple.equals` emits
`cast(Triple[Any, Any, Any], obj)`; `cast`'s first argument is evaluated at runtime and
the translated `Triple` is not subscriptable → `TypeError`. (`Pair.equals` avoids this
because its cast target is the external `Map.Entry`.)

**Circular import (directory level).** With cross-file inheritance fixed (Gap B), the
package no longer imports as separate modules: `Pair` imports `ImmutablePair` (factory
delegation) while `ImmutablePair` imports `Pair` (inheritance). Eager Python
`from X import Y` makes this a circular import that Java tolerates via lazy class loading.
The fix is to emit cross-file *sibling* references used only in method bodies as
function-local imports while keeping superclass imports eager — a larger change that
deserves its own ADR.

## Running the ported tests

[`tests/case_study/test_tuple_case_study.py`](../tests/case_study/test_tuple_case_study.py)
translates the six files, links them, and runs assertions ported from the Commons-Lang
test suite. To sidestep the circular import (above), the harness
([`tests/case_study/harness.py`](../tests/case_study/harness.py)) *links* the translated
modules into a single namespace in dependency order — analogous to how
`tests/equivalence/harness.py` injects dependency stubs that are "not under test". The
only external, non-translated dependencies are small stubs for `java.util.Objects`,
`Map.Entry`, and `CompareToBuilder`; the oracle is the translated tuple logic itself.

```bash
uv run pytest tests/case_study/ -v      # runs in make check; no corpus, no LLM, no JDK
```

**Result: 19 passing assertions** over the working surface and **3 strict xfails**
pinning Gaps C, D, and E. The xfails flip and force their own removal when the underlying
bug is fixed.

The passing surface exercises real translated behaviour end-to-end:

- `ImmutablePair.of(...)`, constructors, `getLeft`/`getRight`
- inherited `Map.Entry` view: `getKey`/`getValue`
- `equals`, `hashCode`, `toString`, `compareTo` on pairs
- base→derived factory delegation: `Pair.of(...)` returning an `ImmutablePair`
- `MutablePair` setters and `setValue`
- `ImmutableTriple`/`MutableTriple` constructors, accessors, `toString`, `compareTo`,
  and mutable setters

## Takeaways

- The rule layer translates a real, multi-file inheritance hierarchy to **100% node
  coverage with zero `__j2py_todo__` markers** — the mechanical breadth is real.
- End-to-end execution is a strictly higher bar that surfaced **five** correctness gaps
  invisible to node coverage. This is the case for the equivalence and confidence-honesty
  work in [#268](https://github.com/tomanizer/j2py/issues/268).
- Two gaps (cross-file inheritance, forward self-reference) are now fixed with regression
  fixtures; three plus the import cycle are documented and tracked.

# ADR 0009 — Two-tier overload translation with runtime dispatch

**Date:** 2026-06-11
**Status:** Accepted (extends ADR 0006; extended by
[ADR 0013](0013-static-overload-dispatch.md))

## Context

Overload fallback is the largest structural blocker in the Spring corpus: 21
constructor groups and the biggest method groups (`registerType` ×10,
`toAttributes` ×7, `registerReflectionHints` ×5, …) all ended in `@overload`
stubs plus a `NotImplementedError` body.

The corpus shows three distinct overload families:

1. **Chained constructor delegation** (`ClassNameGenerator`): `this(t, "")` →
   `this(t, p, new ConcurrentHashMap<>())` → implementation. ADR 0006's merge
   only handled a single hop where every delegator forwards the implementation's
   full argument list, and it silently produced invalid defaults
   (`name: str = name`) when delegators passed their own parameters through.
2. **Builder-style forwarding methods**: a shorter overload whose body is
   exactly `return name(args);` (or a bare call) forwarding to a longer
   overload with extra literal arguments.
3. **True type dispatch** (`ReflectionHints.registerType`): same arity,
   different parameter types, genuinely different bodies. No merge heuristic
   can ever represent these as one Python def.

Line-level structural correspondence is the project quality bar: reviewers must
be able to compare each Java overload against its Python counterpart.

## Decision

Overloaded constructors and methods translate through a two-tier strategy.
Tiers are tried in order; the ADR 0006 fallback survives only at the end.

**Tier 1 — safe merging (extends ADR 0006 rules 3–4).**

- Delegation chains are composed transitively down to a single non-forwarding
  implementation. Eligibility: exactly one implementation, pairwise-distinct
  arities, each delegator passes its own parameters through positionally and
  forwards only closed expressions (no parameter references) for the rest, and
  overlapping defaults agree across delegators.
- Forwarded immutable literals become Python default parameter values.
  Any other forwarded expression (constructor calls, collection literals)
  becomes a `None` sentinel default plus an `if x is None: x = <expr>`
  normalization line, so mutable defaults are never shared across calls.
- The same chain logic applies to builder-style forwarding method overloads
  (single-statement `return name(...)`/`name(...)` bodies on the same name).

**Tier 2 — runtime dispatch via a vendored decorator.**

- Groups that cannot merge emit every Java overload as a separate, same-named
  `def` with its body translated 1:1, each decorated with `@overloaded` from a
  vendored `j2py_runtime.py` module (stdlib-only, ~200 lines) that the CLI
  writes next to the translated output whenever it is used.
- The dispatcher keys same-named defs by qualified name, filters candidates by
  arity (varargs-aware), and scores each positional argument: exact type (2)
  beats subclass (1) beats wildcard (0). Unresolvable annotations (erased
  generics, untranslated Java types) are wildcards; `Callable[...]` means
  "any callable". Non-varargs beats varargs on equal scores, mirroring Java.
  A remaining tie raises `TypeError` instead of silently picking the wrong
  overload.
- `this(...)` delegation inside dispatched constructor bodies becomes
  `self.__init__(...)`, and receiverless calls to the same overload group
  become `self.<name>(...)` so they re-enter the dispatcher.
- Redefinitions carry `# type: ignore[no-redef]  # noqa: F811` so mypy and
  ruff accept the intentional same-name defs. Tier 2 emits no `@overload`
  stubs: the same-named defs themselves preserve every Java signature.
- Eligibility: instance methods and constructors only (static overload groups
  keep the fallback), and the *erased* Python signatures must stay pairwise
  distinct. Erasure keeps the base type (`dict[str, int]` → `dict`,
  `Callable[...]` → `Callable`, `*T` marks varargs); groups that collapse
  (`int`/`long` → `int`, `String`/`CharSequence` → `str`) keep the ADR 0006
  fallback with a diagnostic.

**Fallback (ADR 0006 rule 5)** remains for static groups and erasure
collisions: stubs plus a `TODO(j2py)` and `NotImplementedError`.

## Consequences

+ The dominant corpus overload failures translate deterministically; each Java
  overload keeps a same-named, same-order Python counterpart — better
  line-level correspondence than merged bodies.
+ Mutable-default bugs are impossible by construction (`None` sentinel rule).
+ The previous invalid output for pass-through delegators (`name: str = name`,
  raw Java types in annotations) is fixed by the pass-through prefix rule.
+ Translated output stays dependency-free: `j2py_runtime.py` is vendored, not
  a pip dependency.
− Java resolves overloads statically; the dispatcher resolves on runtime
  types. When an argument's declared type differs from its runtime type
  (`Object o = "x"; call(o)`), Java picks the `Object` overload while the
  dispatcher picks the `String` one. Translated call sites pass the same
  values as the Java original, so this is rarely observable.
− Dispatch over annotations that do not resolve in the output module degrades
  to wildcards; calls that remain ambiguous raise `TypeError` at runtime
  rather than misdispatch. Reviewers see the failure at the call, not wrong
  behavior.
− mypy checks call sites against only the first same-named def (later defs are
  `no-redef`-ignored). Type-checking fidelity is traded for body-level
  correspondence.

## References

- [Issue #44](https://github.com/tomanizer/j2py/issues/44)
- [ADR 0006](0006-overload-translation-policy.md)
- Corpus evidence: `org.springframework.aot.generate.ClassNameGenerator`,
  `org.springframework.aot.generate.DefaultGenerationContext`,
  `org.springframework.aot.hint.ReflectionHints`

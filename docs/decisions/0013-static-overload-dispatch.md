# ADR 0013 — Static overload dispatch for distinguishable signatures

**Date:** 2026-06-14
**Status:** Accepted

## Context

ADR 0009 introduced runtime overload dispatch for constructors and instance
methods, but kept static overload groups on the manual-dispatch fallback. The
multi-corpus baselines now show static overload families as the largest
remaining overload cluster: Spring factories such as
`ObjectNameManager.getInstance(...)`, forwarding helpers such as
`BshScriptUtils.createBshObject(...)`, and Commons range factories such as
`DoubleRange.of(...)`.

Leaving all static groups unhandled is too conservative, but a blanket `*args`
dispatcher would weaken the reviewability contract. Static overloads need the
same guardrails as instance dispatch: each Java overload must remain visible,
and groups that Python cannot distinguish must stay on the explicit manual
fallback.

## Decision

Static method overload groups may use the vendored `@overloaded` dispatcher when
all overloads are static methods and their erased Python signatures are pairwise
distinct. The generated methods are decorated as:

```python
@staticmethod
@overloaded
def method(...):
    ...
```

This keeps instance access from injecting `self` while still letting the
dispatcher register same-named definitions.

Receiverless calls from one overload body to the same static overload group are
qualified with the containing Python class name, for example:

```python
return ObjectNameManager.get_instance(text)
```

That preserves same-group dispatch and avoids emitting unresolved bare
functions inside static method bodies.

Forwarding merge rules may also recognize known boxed primitive wrapper calls
such as `Double.valueOf(x)` as pass-through arguments. This permits same-arity
boxed/unboxed forwarding overloads to merge into the implementation overload
instead of falling back solely because Java's primitive and boxed types both
translate to the same Python type.

Erased-signature collisions remain manual. Examples include overload groups
where Java distinguishes `int` and `long`, but both erase to Python `int`.

## Consequences

+ Static factory overloads can be represented without hiding individual Java
  signatures.
+ Same-group static forwarding calls remain valid Python and continue through
  the dispatcher.
+ Commons-style boxed/unboxed forwarding factories no longer require manual
  dispatch when the forwarding is mechanically pass-through.
+ Diagnostics stay honest because erased collisions and ambiguous groups keep
  the explicit manual-dispatch TODO.
- Runtime dispatch still uses Python runtime values, while Java resolves
  overloads using compile-time static types.
- Class-qualified self-calls are straightforward for normal classes but remain
  an approximation for unusual nested-type scopes.

## References

- [Issue #88](https://github.com/tomanizer/j2py/issues/88)
- [ADR 0006](0006-overload-translation-policy.md)
- [ADR 0009](0009-two-tier-overload-translation.md)

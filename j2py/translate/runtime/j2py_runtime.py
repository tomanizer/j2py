"""Runtime overload dispatch for j2py-translated Python.

This module is emitted verbatim next to translated output as ``j2py_runtime.py``
and depends only on the standard library.

Java resolves overloads at compile time using static argument types. The
``overloaded`` decorator approximates that at runtime so each Java overload can
stay a separate, same-named Python ``def`` (preserving line-level correspondence
with the Java source). Dispatch semantics, per ADR 0009:

- Candidates are filtered by arity (varargs-aware), then scored per positional
  argument: exact type match (2) beats subclass match (1) beats wildcard (0).
- Annotations that have no runtime-checkable equivalent (erased generics,
  untranslated Java types, ``Any``/``object``) are wildcards.
- ``Callable[...]`` annotations match any callable argument.
- On equal scores a non-varargs overload beats a varargs one (as in Java); a
  remaining tie raises ``TypeError`` rather than silently picking the wrong
  Java overload.

Because dispatch happens on runtime types rather than static types, behaviour
can differ from Java when an argument's declared type differs from its runtime
type. Translated call sites pass the same values as the Java original, so this
is rarely observable in practice.
"""

from __future__ import annotations

import builtins
import inspect
from collections.abc import Callable
from typing import Any, ClassVar, NoReturn

__all__ = ["__j2py_todo__", "overloaded"]


def __j2py_todo__(java_source: str) -> NoReturn:
    """Raise NotImplementedError for an untranslated Java construct.

    j2py emits calls to this function in place of Java constructs that the
    rule layer could not translate. Reaching this at runtime signals a
    translation gap that requires manual attention.
    """
    raise NotImplementedError(f"untranslated Java construct: {java_source!r}")

_WILDCARD: Any = object()  # annotation cannot be checked at runtime
_CALLABLE: Any = object()  # annotation means "any callable"
_CALLABLE_NAMES = frozenset({"Callable", "typing.Callable", "collections.abc.Callable"})


def _resolve_annotation(annotation: object, globalns: dict[str, Any]) -> Any:
    """Map a (string) annotation to a runtime check: a type, a tuple, or a sentinel."""
    if annotation is inspect.Parameter.empty:
        return _WILDCARD
    text = str(annotation).strip()
    if not text or text in {"Any", "object", "typing.Any"}:
        return _WILDCARD
    if text == "None":
        return type(None)
    parts = _split_union(text)
    if len(parts) > 1:
        resolved = tuple(_resolve_annotation(part, globalns) for part in parts)
        if any(item is _WILDCARD for item in resolved):
            return _WILDCARD
        return resolved
    base = text.split("[", 1)[0].strip()
    if base in _CALLABLE_NAMES:
        return _CALLABLE
    target: Any = globalns
    for index, name in enumerate(base.split(".")):
        if index == 0:
            target = globalns.get(name, getattr(builtins, name, _WILDCARD))
        else:
            target = getattr(target, name, _WILDCARD)
        if target is _WILDCARD:
            return _WILDCARD
    return target if isinstance(target, type) else _WILDCARD


def _split_union(text: str) -> list[str]:
    """Split a type expression on top-level ``|`` only."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "|" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _score_argument(argument: object, check: Any) -> int | None:
    """Score one argument against one resolved check; ``None`` means no match."""
    if check is _WILDCARD:
        return 0
    if check is _CALLABLE:
        return 1 if callable(argument) else None
    if isinstance(check, tuple):
        scores = [_score_argument(argument, item) for item in check]
        matched = [score for score in scores if score is not None]
        return max(matched) if matched else None
    if type(argument) is check:
        return 2
    if isinstance(argument, check):
        return 1
    if check is float and isinstance(argument, int):
        return 1
    return None


class _Overload:
    """One registered Java overload with lazily resolved dispatch checks."""

    __slots__ = ("func", "_param_names", "_checks", "_vararg_check", "has_vararg")

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func
        self._param_names: tuple[str, ...] | None = None
        self._checks: tuple[Any, ...] = ()
        self._vararg_check: Any = _WILDCARD
        self.has_vararg = False

    def _resolve(self) -> None:
        globalns = getattr(self.func, "__globals__", {})
        names: list[str] = []
        checks: list[Any] = []
        for parameter in inspect.signature(self.func).parameters.values():
            if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                self.has_vararg = True
                self._vararg_check = _resolve_annotation(parameter.annotation, globalns)
            elif parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                names.append(parameter.name)
                checks.append(_resolve_annotation(parameter.annotation, globalns))
        self._param_names = tuple(names)
        self._checks = tuple(checks)

    def match(self, args: tuple[object, ...], kwargs: dict[str, object]) -> int | None:
        """Return a dispatch score for the call, or ``None`` if it cannot apply."""
        if self._param_names is None:
            self._resolve()
        assert self._param_names is not None
        fixed = len(self._param_names)
        arity_ok = len(args) >= fixed if self.has_vararg else len(args) == fixed
        if not arity_ok:
            return None
        if any(name not in self._param_names for name in kwargs):
            return None
        score = 0
        for argument, check in zip(args, self._checks, strict=False):
            argument_score = _score_argument(argument, check)
            if argument_score is None:
                return None
            score += argument_score
        for argument in args[fixed:]:
            argument_score = _score_argument(argument, self._vararg_check)
            if argument_score is None:
                return None
            score += argument_score
        return score


class overloaded:  # noqa: N801 - decorator is intentionally lowercase
    """Collect same-named Java overloads and dispatch on runtime argument types.

    Every ``def`` decorated with ``@overloaded`` registers into a group keyed by
    its qualified name, so repeated same-named definitions in one class body all
    join the same dispatcher. The class attribute ends up bound to the group.
    """

    _registry: ClassVar[dict[tuple[str, str], overloaded]] = {}

    _overloads: list[_Overload]
    _qualname: str

    def __new__(cls, func: Callable[..., Any]) -> overloaded:
        key = (getattr(func, "__module__", "?"), func.__qualname__)
        group = cls._registry.get(key)
        if group is None:
            group = super().__new__(cls)
            group._overloads = []
            group._qualname = func.__qualname__
            group.__doc__ = func.__doc__
            cls._registry[key] = group
        group._overloads.append(_Overload(func))
        return group

    def __init__(self, func: Callable[..., Any]) -> None:
        # Registration happens in __new__ so re-decoration returns the group.
        pass

    def __get__(self, obj: object, objtype: type | None = None) -> Callable[..., Any]:
        if obj is None:
            return self

        def bound(*args: object, **kwargs: object) -> object:
            return self._dispatch((obj, *args), kwargs)

        return bound

    def __call__(self, *args: object, **kwargs: object) -> object:
        return self._dispatch(args, kwargs)

    def _dispatch(self, args: tuple[object, ...], kwargs: dict[str, object]) -> object:
        matches: list[tuple[int, int, _Overload]] = []
        for candidate in self._overloads:
            score = candidate.match(args, kwargs)
            if score is not None:
                # Mirror Java by preferring non-varargs overloads on equal scores.
                matches.append((score, 0 if candidate.has_vararg else 1, candidate))
        received = ", ".join(type(argument).__name__ for argument in args[1:])
        if not matches:
            raise TypeError(
                f"no overload of {self._qualname!r} matches argument types ({received})",
            )
        best_key = max(match[:2] for match in matches)
        best = [candidate for score, vararg, candidate in matches if (score, vararg) == best_key]
        if len(best) > 1:
            raise TypeError(
                f"ambiguous overload call to {self._qualname!r} for argument types "
                f"({received}); runtime types cannot distinguish the Java signatures",
            )
        return best[0].func(*args, **kwargs)

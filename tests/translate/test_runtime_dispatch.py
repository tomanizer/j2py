"""Behavioral tests for the vendored runtime overload dispatcher (ADR 0009)."""

from __future__ import annotations

import gc
import re
import threading
import time
from collections.abc import Callable

import pytest

from j2py.translate.runtime import __j2py_todo__, _j2py_monitor, overloaded
from j2py.translate.runtime.j2py_runtime import _j2py_monitor_registry


class TypeReference:
    def __init__(self, name: str) -> None:
        self.name = name


class MemberCategory:
    pass


class Base:
    pass


class Derived(Base):
    pass


def test_dispatch_picks_overload_by_argument_type() -> None:
    class Hints:
        @overloaded
        def register_type(self, type: TypeReference, type_hint: Callable[[str], None]) -> str:
            return "reference+consumer"

        @overloaded  # noqa: F811
        def register_type(self, type: type, *categories: MemberCategory) -> str:  # noqa: F811
            return f"class+{len(categories)}"

    hints = Hints()
    assert hints.register_type(TypeReference("X"), lambda value: None) == "reference+consumer"
    assert hints.register_type(str, MemberCategory(), MemberCategory()) == "class+2"
    assert hints.register_type(str) == "class+0"


def test_dispatch_rejects_unmatched_arguments_with_type_error() -> None:
    class Single:
        @overloaded
        def accept(self, value: str) -> str:
            return value

    with pytest.raises(TypeError, match="no overload"):
        Single().accept(3.5)


def test_exact_type_match_beats_subclass_match() -> None:
    """Annotations resolve against module globals, as in translated output."""

    class Visitor:
        @overloaded
        def visit(self, node: Base) -> str:
            return "base"

        @overloaded  # noqa: F811
        def visit(self, node: Derived) -> str:  # noqa: F811
            return "derived"

    assert Visitor().visit(Derived()) == "derived"
    assert Visitor().visit(Base()) == "base"


def test_unresolvable_annotation_is_wildcard_and_loses_to_real_match() -> None:
    class Sink:
        @overloaded
        def put(self, value: UnknownJavaType) -> str:  # noqa: F821
            return "wildcard"

        @overloaded  # noqa: F811
        def put(self, value: int) -> str:  # noqa: F811
            return "int"

    assert Sink().put(3) == "int"
    assert Sink().put(object()) == "wildcard"


def test_arity_distinguishes_overloads() -> None:
    class Pad:
        @overloaded
        def pad(self, value: str) -> str:
            return self.pad(value, " ")

        @overloaded  # noqa: F811
        def pad(self, value: str, fill: str) -> str:  # noqa: F811
            return value + fill

    assert Pad().pad("a", "-") == "a-"
    assert Pad().pad("a") == "a "


def test_constructor_dispatch_supports_delegation_via_self_init() -> None:
    class Context:
        @overloaded
        def __init__(self, name: str, files: list[str]) -> None:
            self.__init__(name, files, {"hints": True})

        @overloaded  # noqa: F811
        def __init__(self, name: str, files: list[str], hints: dict[str, bool]) -> None:  # noqa: F811
            self.name = name
            self.files = files
            self.hints = hints

        @overloaded  # noqa: F811
        def __init__(self, existing: Context, feature: str) -> None:  # noqa: F811
            self.name = existing.name + feature
            self.files = existing.files
            self.hints = existing.hints

    context = Context("base", ["a.py"])
    assert context.hints == {"hints": True}
    copy = Context(context, "-fork")
    assert copy.name == "base-fork"
    assert copy.files == ["a.py"]


def test_union_annotations_match_any_member() -> None:
    class Add:
        @overloaded
        def add(self, left: int | float, right: int | float) -> int | float:
            return left + right

        @overloaded  # noqa: F811
        def add(self, left: str, right: str) -> str:  # noqa: F811
            return left + right

    assert Add().add(1, 2.0) == 3.0
    assert Add().add("a", "b") == "ab"


def test_int_arguments_match_float_annotations_as_numeric_promotion() -> None:
    class Numeric:
        @overloaded
        def accept(self, value: float) -> str:
            return "float"

        @overloaded  # noqa: F811
        def accept(self, value: str) -> str:  # noqa: F811
            return "str"

    assert Numeric().accept(1) == "float"


def test_callable_union_keeps_callable_check() -> None:
    class MaybeCallback:
        @overloaded
        def accept(self, value: Callable[[str], None] | None) -> str:
            return "callback"

    maybe = MaybeCallback()
    assert maybe.accept(lambda value: None) == "callback"
    assert maybe.accept(None) == "callback"
    with pytest.raises(TypeError, match="no overload"):
        maybe.accept(object())


def test_indistinguishable_runtime_types_raise_instead_of_misdispatching() -> None:
    class Tie:
        @overloaded
        def pick(self, value: Erased[int]) -> str:  # noqa: F821
            return "first"

        @overloaded  # noqa: F811
        def pick(self, value: Erased[str]) -> str:  # noqa: F811, F821
            return "second"

    with pytest.raises(TypeError, match="ambiguous overload"):
        Tie().pick(object())


def test_j2py_todo_raises_not_implemented_error() -> None:
    with pytest.raises(NotImplementedError, match="untranslated Java construct"):
        __j2py_todo__("new int[rows][cols]")


def test_j2py_todo_includes_java_source_in_message() -> None:
    snippet = "someComplexExpression()"
    with pytest.raises(NotImplementedError, match=re.escape(snippet)):
        __j2py_todo__(snippet)


class _JavaObj:
    """Stand-in for a translated Java object: user-defined, so weakly referenceable."""


def test_j2py_monitor_is_a_context_manager() -> None:
    with _j2py_monitor(_JavaObj()):
        pass  # must not raise


def test_j2py_monitor_same_object_same_lock() -> None:
    obj = _JavaObj()
    m1 = _j2py_monitor(obj)
    m2 = _j2py_monitor(obj)
    assert m1._lock is m2._lock


def test_j2py_monitor_different_objects_different_locks() -> None:
    a, b = _JavaObj(), _JavaObj()
    assert _j2py_monitor(a)._lock is not _j2py_monitor(b)._lock


def test_j2py_monitor_is_reentrant() -> None:
    obj = _JavaObj()
    with _j2py_monitor(obj), _j2py_monitor(obj):  # must not deadlock — uses RLock
        pass


def test_j2py_monitor_blocks_concurrent_access() -> None:
    obj = _JavaObj()
    results: list[str] = []

    def writer(tag: str) -> None:
        with _j2py_monitor(obj):
            results.append(f"{tag}:enter")
            results.append(f"{tag}:exit")

    t1 = threading.Thread(target=writer, args=("A",))
    t2 = threading.Thread(target=writer, args=("B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Lock must prevent interleaving: each thread's enter/exit must be adjacent
    assert results.index("A:enter") + 1 == results.index("A:exit")
    assert results.index("B:enter") + 1 == results.index("B:exit")


class _ValueObj:
    """Distinct instances that compare equal — mirrors a translated Java value object."""

    def __init__(self, v: int) -> None:
        self.v = v

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _ValueObj) and self.v == other.v

    def __hash__(self) -> int:
        return hash(self.v)


def test_j2py_monitor_non_weak_referenceable_object_shares_lock() -> None:
    # object()/list/dict cannot be weakly referenced. The monitor must still bind
    # ONE lock per object (by identity) — a fresh lock per call would silently
    # provide no mutual exclusion at all (the bug this guards against).
    for obj in (object(), [1, 2, 3], {"k": "v"}):
        assert _j2py_monitor(obj)._lock is _j2py_monitor(obj)._lock


def test_j2py_monitor_distinct_non_weak_referenceable_objects_differ() -> None:
    assert _j2py_monitor(object())._lock is not _j2py_monitor(object())._lock


def test_j2py_monitor_uses_identity_not_equality() -> None:
    # Java monitors are per-object-identity; two equal-but-distinct objects must
    # NOT share a monitor (a hash/eq-keyed registry would wrongly merge them).
    a, b = _ValueObj(1), _ValueObj(1)
    assert a == b and hash(a) == hash(b)
    assert a is not b
    assert _j2py_monitor(a)._lock is not _j2py_monitor(b)._lock


def test_j2py_monitor_evicts_lock_when_object_collected() -> None:
    # A weakly-referenceable object's entry must be dropped on GC so its id()
    # cannot later be recycled onto an unrelated object that would inherit its lock.
    obj = _JavaObj()
    key = id(obj)
    _j2py_monitor(obj)
    assert key in _j2py_monitor_registry
    del obj
    gc.collect()
    assert key not in _j2py_monitor_registry


def test_j2py_monitor_serializes_non_weak_referenceable_object() -> None:
    # Behavioural proof of mutual exclusion on a non-weak-referenceable lock: a
    # no-op (fresh-lock-per-call) implementation would let B enter during A's hold.
    lock_obj: list[int] = []
    order: list[str] = []
    a_inside = threading.Event()

    def first() -> None:
        with _j2py_monitor(lock_obj):
            order.append("a-enter")
            a_inside.set()
            time.sleep(0.05)
            order.append("a-exit")

    def second() -> None:
        a_inside.wait()
        with _j2py_monitor(lock_obj):
            order.append("b-enter")

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    a_inside.wait()
    t2.start()
    t1.join()
    t2.join()

    assert order == ["a-enter", "a-exit", "b-enter"]

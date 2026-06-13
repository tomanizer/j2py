"""Behavioral tests for the vendored runtime overload dispatcher (ADR 0009)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from j2py.translate.runtime import __j2py_todo__, overloaded


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
    with pytest.raises(NotImplementedError, match=snippet):
        __j2py_todo__(snippet)

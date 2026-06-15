"""End-to-end case study: Apache Commons Lang ``org.apache.commons.lang3.tuple``.

This is the real-world, multi-file case study for issue #311. Six interdependent Java
files (an abstract ``Pair``/``Triple`` base plus immutable and mutable subclasses) are
translated by the rule layer (no LLM), linked, and exercised by unit tests whose
assertions are ported from the upstream Commons-Lang test suite.

The narrative and the gaps this surfaced are documented in ``docs/CASE_STUDY.md``.
``strict=True`` xfails below pin the known translation gaps; each will flip and force its
own removal when the corresponding bug is fixed (mirroring the equivalence-gate
discipline).
"""

from __future__ import annotations

import pytest

from tests.case_study.harness import (
    link_tuple_namespace,
    translate_tuple_package,
)

ALL_CLASSES = (
    "Pair",
    "Triple",
    "ImmutablePair",
    "MutablePair",
    "ImmutableTriple",
    "MutableTriple",
)


@pytest.fixture(scope="module")
def sources() -> dict[str, str]:
    return translate_tuple_package()


@pytest.fixture(scope="module")
def tuple_pkg():
    return link_tuple_namespace()


# --- Translation quality: rule layer reaches every node in all six files. ---------


def test_all_six_files_translate(sources: dict[str, str]) -> None:
    assert set(sources) == set(ALL_CLASSES)
    for name, source in sources.items():
        assert f"class {name}" in source


@pytest.mark.parametrize("name", ALL_CLASSES)
def test_no_todo_markers(sources: dict[str, str], name: str) -> None:
    source = sources[name]
    assert "__j2py_todo__" not in source
    assert "TODO(j2py)" not in source


def test_cross_file_inheritance_is_preserved(sources: dict[str, str]) -> None:
    # Bug B fix: generic cross-file superclasses are kept and imported.
    assert "class ImmutablePair(Pair):" in sources["ImmutablePair"]
    assert "from org.apache.commons.lang3.tuple.Pair import Pair" in sources["ImmutablePair"]
    assert "class MutablePair(Pair):" in sources["MutablePair"]
    assert "class ImmutableTriple(Triple):" in sources["ImmutableTriple"]
    assert "class MutableTriple(Triple):" in sources["MutableTriple"]


def test_self_referential_static_field_is_deferred(sources: dict[str, str]) -> None:
    # Bug A fix: NULL singleton is assigned after the class, not in the class body.
    source = sources["ImmutablePair"]
    body, _, after = source.partition("ImmutablePair.NULL = ImmutablePair(None, None)")
    assert "    NULL: ImmutablePair = ImmutablePair(None, None)" not in body
    assert "ImmutablePair.NULL = ImmutablePair(None, None)" in source
    assert after.strip() == ""


# --- Ported behavioural assertions: the working surface. --------------------------


def test_immutable_pair_factory_and_accessors(tuple_pkg) -> None:
    pair = tuple_pkg.ImmutablePair.of("left", 42)
    assert pair.get_left() == "left"
    assert pair.get_right() == 42
    # Map.Entry view (inherited from Pair).
    assert pair.get_key() == "left"
    assert pair.get_value() == 42


def test_base_factory_delegates_to_immutable(tuple_pkg) -> None:
    # Pair.of delegates to ImmutablePair.of across files.
    pair = tuple_pkg.Pair.of("a", "b")
    assert type(pair).__name__ == "ImmutablePair"
    assert (pair.get_left(), pair.get_right()) == ("a", "b")


def test_pair_equality_and_hash(tuple_pkg) -> None:
    a = tuple_pkg.ImmutablePair.of("k", 1)
    b = tuple_pkg.ImmutablePair.of("k", 1)
    c = tuple_pkg.ImmutablePair.of("k", 2)
    assert a.equals(b) is True
    assert a.equals(c) is False
    assert a.hash_code() == b.hash_code()
    assert isinstance(a, tuple_pkg.Map.Entry)


def test_pair_to_string(tuple_pkg) -> None:
    assert tuple_pkg.ImmutablePair.of("x", "y").to_string() == "(x,y)"


def test_pair_compare_to(tuple_pkg) -> None:
    a = tuple_pkg.ImmutablePair.of("a", 1)
    b = tuple_pkg.ImmutablePair.of("a", 2)
    assert a.compare_to(b) < 0
    assert b.compare_to(a) > 0
    assert a.compare_to(tuple_pkg.ImmutablePair.of("a", 1)) == 0


def test_mutable_pair_setters(tuple_pkg) -> None:
    pair = tuple_pkg.MutablePair("k", 1)
    pair.set_left("k2")
    pair.set_right(2)
    assert (pair.get_left(), pair.get_right()) == ("k2", 2)
    # set_value returns the previous value and updates the right element (Map.Entry).
    previous = pair.set_value(99)
    assert previous == 2
    assert pair.get_right() == 99


def test_immutable_triple_constructor_and_accessors(tuple_pkg) -> None:
    triple = tuple_pkg.ImmutableTriple(1, "mid", 3.0)
    assert triple.get_left() == 1
    assert triple.get_middle() == "mid"
    assert triple.get_right() == 3.0


def test_triple_to_string(tuple_pkg) -> None:
    assert tuple_pkg.ImmutableTriple(1, 2, 3).to_string() == "(1,2,3)"


def test_triple_compare_to(tuple_pkg) -> None:
    a = tuple_pkg.ImmutableTriple("x", "y", 1)
    c = tuple_pkg.ImmutableTriple("x", "y", 2)
    assert a.compare_to(c) < 0
    assert c.compare_to(a) > 0
    assert a.compare_to(tuple_pkg.ImmutableTriple("x", "y", 1)) == 0


def test_mutable_triple_setters(tuple_pkg) -> None:
    triple = tuple_pkg.MutableTriple()
    triple.set_left("L")
    triple.set_middle("M")
    triple.set_right("R")
    assert (triple.get_left(), triple.get_middle(), triple.get_right()) == ("L", "M", "R")


# --- Known translation gaps (pinned; see docs/CASE_STUDY.md "Gaps surfaced"). ------


@pytest.mark.xfail(strict=True, reason="CASE_STUDY gap C: static field read emitted unqualified")
def test_gap_c_null_singleton_accessor(tuple_pkg) -> None:
    # null_pair() does `return NULL` (bare) instead of `return ImmutablePair.NULL`.
    assert tuple_pkg.ImmutablePair.null_pair() is tuple_pkg.ImmutablePair.NULL


@pytest.mark.xfail(strict=True, reason="CASE_STUDY gap D: bitwise '|' precedence vs comparison")
def test_gap_d_triple_factory(tuple_pkg) -> None:
    # ImmutableTriple.of mistranslates `a != null | b != null` precedence.
    triple = tuple_pkg.ImmutableTriple.of(1, 2, 3)
    assert (triple.get_left(), triple.get_middle(), triple.get_right()) == (1, 2, 3)


@pytest.mark.xfail(strict=True, reason="CASE_STUDY gap E: cast() to generic translated class")
def test_gap_e_triple_equals(tuple_pkg) -> None:
    a = tuple_pkg.ImmutableTriple("x", "y", 1)
    b = tuple_pkg.ImmutableTriple("x", "y", 1)
    assert a.equals(b) is True

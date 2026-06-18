"""Equivalence gate for Commons-Lang ``BooleanUtils`` focused surface."""

from __future__ import annotations

import sys

import pytest

from tests.equivalence.harness import (
    JavaBoolean,
    install_boolean_utils_stubs,
    load_translated_module,
    translate_rule_layer,
)

JAVA_CLASS = "BooleanUtils.java"
pytestmark = pytest.mark.equivalence
surface = pytest.mark.equivalence_surface


@pytest.fixture(scope="module")
def boolean_utils_source() -> str:
    return translate_rule_layer(JAVA_CLASS)


@pytest.fixture(scope="module")
def boolean_utils(boolean_utils_source: str):
    stub_modules = install_boolean_utils_stubs()
    module = load_translated_module(boolean_utils_source, "boolean_utils_fixture")
    yield module.BooleanUtils
    sys.modules.pop("boolean_utils_fixture", None)
    for name in reversed(stub_modules):
        sys.modules.pop(name, None)


@surface(JAVA_CLASS, "BooleanUtils.booleanValues()")
def test_boolean_values(boolean_utils) -> None:
    assert boolean_utils.boolean_values() == [JavaBoolean.FALSE, JavaBoolean.TRUE]


@surface(JAVA_CLASS, "BooleanUtils.primitiveValues()")
def test_primitive_values(boolean_utils) -> None:
    assert boolean_utils.primitive_values() == [False, True]


@surface(JAVA_CLASS, "BooleanUtils.values()")
def test_values(boolean_utils) -> None:
    assert boolean_utils.values() == [JavaBoolean.FALSE, JavaBoolean.TRUE]


@surface(JAVA_CLASS, "BooleanUtils.compare(boolean,boolean)")
def test_compare(boolean_utils) -> None:
    assert boolean_utils.compare(False, False) == 0
    assert boolean_utils.compare(True, True) == 0
    assert boolean_utils.compare(False, True) < 0
    assert boolean_utils.compare(True, False) > 0


@surface(JAVA_CLASS, "BooleanUtils.isTrue(Boolean)")
@surface(JAVA_CLASS, "BooleanUtils.isFalse(Boolean)")
@surface(JAVA_CLASS, "BooleanUtils.isNotTrue(Boolean)")
@surface(JAVA_CLASS, "BooleanUtils.isNotFalse(Boolean)")
def test_predicates(boolean_utils) -> None:
    assert boolean_utils.is_true(JavaBoolean.TRUE) is True
    assert boolean_utils.is_true(JavaBoolean.FALSE) is False
    assert boolean_utils.is_true(None) is False
    assert boolean_utils.is_false(JavaBoolean.FALSE) is True
    assert boolean_utils.is_false(JavaBoolean.TRUE) is False
    assert boolean_utils.is_false(None) is False
    assert boolean_utils.is_not_true(None) is True
    assert boolean_utils.is_not_true(JavaBoolean.FALSE) is True
    assert boolean_utils.is_not_true(JavaBoolean.TRUE) is False
    assert boolean_utils.is_not_false(None) is True
    assert boolean_utils.is_not_false(JavaBoolean.TRUE) is True
    assert boolean_utils.is_not_false(JavaBoolean.FALSE) is False


@surface(JAVA_CLASS, "BooleanUtils.negate(Boolean)")
def test_negate(boolean_utils) -> None:
    assert boolean_utils.negate(JavaBoolean.TRUE) == JavaBoolean.FALSE
    assert boolean_utils.negate(JavaBoolean.FALSE) == JavaBoolean.TRUE
    assert boolean_utils.negate(None) is None


@surface(JAVA_CLASS, "BooleanUtils.toBooleanDefaultIfNull(Boolean,boolean)")
def test_to_boolean_default_if_null(boolean_utils) -> None:
    assert boolean_utils.to_boolean_default_if_null(JavaBoolean.TRUE, False) is True
    assert boolean_utils.to_boolean_default_if_null(JavaBoolean.FALSE, True) is False
    assert boolean_utils.to_boolean_default_if_null(None, True) is True
    assert boolean_utils.to_boolean_default_if_null(None, False) is False


@surface(JAVA_CLASS, "BooleanUtils.toBooleanObject(int)")
def test_to_boolean_object_int(boolean_utils) -> None:
    assert boolean_utils.to_boolean_object(0) == JavaBoolean.FALSE
    assert boolean_utils.to_boolean_object(1) == JavaBoolean.TRUE
    assert boolean_utils.to_boolean_object(-1) == JavaBoolean.TRUE


@surface(JAVA_CLASS, "BooleanUtils.toBooleanObject(int,int,int,int)")
def test_to_boolean_object_int_mapping(boolean_utils) -> None:
    assert boolean_utils.to_boolean_object(1, 1, 0, 2) == JavaBoolean.TRUE
    assert boolean_utils.to_boolean_object(0, 1, 0, 2) == JavaBoolean.FALSE
    assert boolean_utils.to_boolean_object(2, 1, 0, 2) is None
    with pytest.raises(ValueError, match="Integer"):
        boolean_utils.to_boolean_object(3, 1, 0, 2)


@surface(JAVA_CLASS, "BooleanUtils.toInteger(boolean)")
def test_to_integer_boolean(boolean_utils) -> None:
    assert boolean_utils.to_integer(True) == 1
    assert boolean_utils.to_integer(False) == 0


@surface(JAVA_CLASS, "BooleanUtils.toInteger(boolean,int,int)")
def test_to_integer_boolean_mapping(boolean_utils) -> None:
    assert boolean_utils.to_integer(True, 10, 20) == 10
    assert boolean_utils.to_integer(False, 10, 20) == 20


@surface(JAVA_CLASS, "BooleanUtils.toString(boolean,String,String)")
def test_to_string_boolean(boolean_utils) -> None:
    assert boolean_utils.to_string(True, "yes", "no") == "yes"
    assert boolean_utils.to_string(False, "yes", "no") == "no"

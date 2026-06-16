"""Tests for static import allowlist helpers."""

from j2py.translate.rules.static_imports import (
    is_known_static_method_import,
    known_static_field_alias,
)


def test_known_static_method_import_includes_preconditions_and_objects() -> None:
    assert is_known_static_method_import("com.google.common.base.Preconditions.checkNotNull")
    assert is_known_static_method_import("com.google.common.base.Preconditions.checkState")
    assert is_known_static_method_import("java.util.Objects.requireNonNull")
    assert not is_known_static_method_import("com.example.Helpers.magic")


def test_known_static_field_alias_math_constants() -> None:
    assert known_static_field_alias("java.lang.Math.PI") == "math.pi"
    assert (
        known_static_field_alias("java.lang.annotation.ElementType.METHOD") == "ElementType.METHOD"
    )

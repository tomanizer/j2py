"""Tests for the literal-oracle equivalence harvester."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.harvest import harvest_equivalence_tests as harvester


def _write_java(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "GuavaPrecedenceMathTest.java"
    path.write_text(body, encoding="utf-8")
    return path


def test_harvests_supported_literal_oracle_assertions(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        import org.junit.Test;

        class GuavaPrecedenceMathTest {
            @Test public void testExpandedCapacity() {
                assertEquals(22, GuavaPrecedenceMath.expandedCapacity(10));
                assertEquals("message", -4, GuavaPrecedenceMath.scaledSum(-2, 0, 2));
                assertTrue(GuavaPrecedenceMath.isPositive(1));
                assertFalse(GuavaPrecedenceMath.isPositive(0));
                assertNull(GuavaPrecedenceMath.maybeNull(null));
                assertNotNull(GuavaPrecedenceMath.maybeNull("x"));
            }
        }
        """,
    )
    fixture = tmp_path / "GuavaPrecedenceMath.java"
    fixture.write_text(
        """
        package com.google.common.math;

        public final class GuavaPrecedenceMath {
            public static int expandedCapacity(int value) { return value; }
            public static int scaledSum(int left, int middle, int right) {
                return left + middle + right;
            }
            public static boolean isPositive(int value) { return value > 0; }
            public static String maybeNull(String value) { return value; }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture=str(fixture),
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 6
    assert (
        "assert guava_precedence_math.expanded_capacity(10) == 22  # GuavaPrecedenceMathTest.java:6"
    ) in draft
    assert "assert guava_precedence_math.scaled_sum(-2, 0, 2) == -4" in draft
    assert "assert guava_precedence_math.is_positive(1) is True" in draft
    assert "assert guava_precedence_math.is_positive(0) is False" in draft
    assert "assert guava_precedence_math.maybe_null(None) is None" in draft
    assert 'assert guava_precedence_math.maybe_null("x") is not None' in draft
    assert "install_fixture_stubs," in draft
    assert "stub_modules = install_fixture_stubs(JAVA_CLASS)" in draft
    assert "finally:" in draft


def test_drops_expression_oracle_expected_values(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class GuavaPrecedenceMathTest {
            public void testExpressionOracle() {
                assertEquals((10 + 1) * 2, GuavaPrecedenceMath.expandedCapacity(10));
            }
        }
        """,
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture="GuavaPrecedenceMath.java",
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 0
    assert result.dropped_expression_oracle_count == 1
    assert "# dropped expression-oracle assertions: 1" in draft
    assert "expression-oracle expected value" in draft


def test_reports_unsupported_assertions_and_non_target_calls(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class GuavaPrecedenceMathTest {
            public void testUnsupported() {
                assertThat(GuavaPrecedenceMath.expandedCapacity(10)).isEqualTo(22);
                assertEquals(1, OtherMath.value());
            }
        }
        """,
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture="GuavaPrecedenceMath.java",
    )
    reasons = [item.reason for item in result.skipped]

    assert result.harvested_count == 0
    assert result.unsupported_assertion_count == 1
    assert result.skipped_method_count == 1
    assert "unsupported assertion" in reasons
    assert "unsupported target call" in reasons


def test_skips_unqualified_helper_calls_without_static_import(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class GuavaPrecedenceMathTest {
            public void testHelper() {
                assertEquals(22, helper(10));
            }

            private int helper(int value) {
                return value;
            }
        }
        """,
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture="GuavaPrecedenceMath.java",
    )

    assert result.harvested_count == 0
    assert result.skipped_method_count == 1
    assert result.skipped[0].reason == "unsafe unqualified target call"


def test_allows_unqualified_calls_only_from_explicit_target_static_import(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        import static com.google.common.math.GuavaPrecedenceMath.expandedCapacity;

        class GuavaPrecedenceMathTest {
            public void testStaticImport() {
                assertEquals(22, expandedCapacity(10));
            }
        }
        """,
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture="GuavaPrecedenceMath.java",
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 1
    assert "assert guava_precedence_math.expanded_capacity(10) == 22" in draft


def test_skips_explicit_static_import_from_wrong_package(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        import static other.pkg.GuavaPrecedenceMath.expandedCapacity;

        class GuavaPrecedenceMathTest {
            public void testWrongPackageStaticImport() {
                assertEquals(22, expandedCapacity(10));
            }
        }
        """,
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture="GuavaPrecedenceMath.java",
    )

    assert result.harvested_count == 0
    assert result.skipped_method_count == 1
    assert result.skipped[0].reason == "unsafe unqualified target call"


def test_skips_unqualified_calls_from_wildcard_static_import(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        import static com.google.common.math.GuavaPrecedenceMath.*;

        class GuavaPrecedenceMathTest {
            public void testWildcardImport() {
                assertEquals(22, expandedCapacity(10));
            }
        }
        """,
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture="GuavaPrecedenceMath.java",
    )

    assert result.harvested_count == 0
    assert result.skipped_method_count == 1
    assert result.skipped[0].reason == "unsafe unqualified target call"


def test_wildcard_static_import_does_not_capture_test_helper(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        import static com.google.common.math.GuavaPrecedenceMath.*;

        class GuavaPrecedenceMathTest {
            public void testHelper() {
                assertEquals(22, helper(10));
            }

            private int helper(int value) {
                return 22;
            }
        }
        """,
    )

    result = harvester.harvest_file(
        source,
        target_class="GuavaPrecedenceMath",
        java_fixture="GuavaPrecedenceMath.java",
    )

    assert result.harvested_count == 0
    assert result.skipped_method_count == 1
    assert result.skipped[0].reason == "unsafe unqualified target call"


def test_reserved_target_class_generates_valid_python_draft(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class ClassTest {
            public void testValue() {
                assertEquals(1, Class.value());
            }
        }
        """,
    )
    fixture = tmp_path / "Class.java"
    fixture.write_text(
        """
        public final class Class {
            public static int value() { return 1; }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="Class",
        java_fixture=str(fixture),
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 1
    assert "def class__source() -> str:" in draft
    assert "def class_(class__source: str):" in draft
    assert "def test_value(class_) -> None:" in draft
    compile(draft, "<harvest-draft>", "exec")


def test_reserved_target_class_draft_executes_against_tmp_fixture(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class ClassTest {
            public void testValue() {
                assertEquals(1, Class.value());
            }
        }
        """,
    )
    fixture = tmp_path / "Class.java"
    fixture.write_text(
        """
        public final class Class {
            public static int value() { return 1; }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="Class",
        java_fixture=str(fixture),
    )
    namespace: dict[str, object] = {}
    exec(compile(harvester.render_pytest_draft(result), "<harvest-draft>", "exec"), namespace)

    source_fixture = namespace["class__source"].__wrapped__
    class_fixture = namespace["class_"].__wrapped__
    class_source = source_fixture()
    fixture_generator = class_fixture(class_source)
    class_under_test = next(fixture_generator)

    namespace["test_value"](class_under_test)
    with pytest.raises(StopIteration):
        next(fixture_generator)


def test_disambiguates_java_tests_with_same_python_name(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class TargetTest {
            public void testValue() {
                assertEquals(1, Target.one());
            }

            public void test_value() {
                assertEquals(2, Target.two());
            }
        }
        """,
    )
    fixture = tmp_path / "Target.java"
    fixture.write_text(
        """
        public final class Target {
            public static int one() { return 1; }
            public static int two() { return 2; }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="Target",
        java_fixture=str(fixture),
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 2
    assert "def test_value(target) -> None:" in draft
    assert "def test_value_2(target) -> None:" in draft
    assert "assert target.one() == 1" in draft
    assert "assert target.two() == 2" in draft


def test_skips_overloaded_target_methods_from_java_fixture(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class OverloadedMathTest {
            public void testOverloaded() {
                assertEquals(1, OverloadedMath.parse("1"));
                assertEquals(2, OverloadedMath.identity(2));
            }
        }
        """,
    )
    fixture = tmp_path / "OverloadedMath.java"
    fixture.write_text(
        """
        public final class OverloadedMath {
            public static int parse(String value) { return 1; }
            public static int parse(int value) { return value; }
            public static int identity(int value) { return value; }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="OverloadedMath",
        java_fixture=str(fixture),
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 1
    assert result.skipped_method_count == 1
    assert result.skipped[0].reason == "overloaded target method"
    assert "assert overloaded_math.identity(2) == 2" in draft
    assert "overloaded_math.parse" not in draft


def test_skips_methods_not_declared_on_java_fixture(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class TargetTest {
            public void testMissing() {
                assertEquals(1, Target.missing(1));
                assertEquals(2, Target.present(2));
            }
        }
        """,
    )
    fixture = tmp_path / "Target.java"
    fixture.write_text(
        """
        public final class Target {
            public static int present(int value) { return value; }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="Target",
        java_fixture=str(fixture),
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 1
    assert result.skipped_method_count == 1
    assert result.skipped[0].reason == "target method not in fixture"
    assert "assert target.present(2) == 2" in draft
    assert "target.missing" not in draft


def test_skips_instance_methods_on_java_fixture(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class TargetTest {
            public void testInstanceMethod() {
                assertEquals(1, Target.instanceOnly(1));
            }
        }
        """,
    )
    fixture = tmp_path / "Target.java"
    fixture.write_text(
        """
        public final class Target {
            public int instanceOnly(int value) { return value; }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="Target",
        java_fixture=str(fixture),
    )

    assert result.harvested_count == 0
    assert result.skipped_method_count == 1
    assert result.skipped[0].reason == "target method not in fixture"


def test_nested_class_method_names_do_not_create_false_overloads(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class TargetTest {
            public void testOuter() {
                assertEquals(3, Target.outer(3));
            }
        }
        """,
    )
    fixture = tmp_path / "Target.java"
    fixture.write_text(
        """
        public final class Target {
            public static int outer(int value) { return value; }
            static class Inner {
                int outer(String value) { return 1; }
            }
        }
        """,
        encoding="utf-8",
    )

    result = harvester.harvest_file(
        source,
        target_class="Target",
        java_fixture=str(fixture),
    )
    draft = harvester.render_pytest_draft(result)

    assert result.harvested_count == 1
    assert result.skipped_method_count == 0
    assert "assert target.outer(3) == 3" in draft


def test_parse_errors_fail_fast(tmp_path: Path) -> None:
    source = _write_java(
        tmp_path,
        """
        class GuavaPrecedenceMathTest {
            public void testBroken() {
                @@@
            }
        }
        """,
    )

    try:
        harvester.harvest_file(
            source,
            target_class="GuavaPrecedenceMath",
            java_fixture="GuavaPrecedenceMath.java",
        )
    except ValueError as exc:
        assert "parse errors" in str(exc)
    else:
        raise AssertionError("expected parse errors to fail fast")


def test_main_writes_draft_file(monkeypatch, tmp_path: Path, capsys) -> None:
    source = _write_java(
        tmp_path,
        """
        class GuavaPrecedenceMathTest {
            public void testExpandedCapacity() {
                assertEquals(22, GuavaPrecedenceMath.expandedCapacity(10));
            }
        }
        """,
    )
    out = tmp_path / "test_guava_precedence_math_draft.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "harvest_equivalence_tests.py",
            "--test-source",
            str(source),
            "--target-class",
            "GuavaPrecedenceMath",
            "--java-fixture",
            "GuavaPrecedenceMath.java",
            "--write",
            str(out),
        ],
    )

    assert harvester.main() == 0
    captured = capsys.readouterr()

    assert out.is_file()
    assert "Harvest summary: 1 harvested" in captured.out
    assert "def test_expanded_capacity(guava_precedence_math) -> None:" in out.read_text(
        encoding="utf-8"
    )

"""Tests for the equivalence surface metric report."""

from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from scripts.equivalence import surface_report
from scripts.equivalence.surface_report import (
    LibrarySurface,
    PassedMethod,
    build_report,
    public_methods_for_fixture,
    render_report,
)

FIXTURES = Path("tests/fixtures/equivalence")


def test_public_method_extraction_preserves_overload_signatures() -> None:
    methods = public_methods_for_fixture(FIXTURES / "NumberUtils.java")
    signatures = {method.signature for method in methods}

    assert len(methods) == 61
    assert "NumberUtils.toDouble(String)" in signatures
    assert "NumberUtils.toDouble(String,double)" in signatures
    assert "NumberUtils.toDouble(BigDecimal)" in signatures
    assert "NumberUtils.toDouble(BigDecimal,double)" in signatures
    assert "NumberUtils.NumberUtils()" not in signatures


def test_public_method_extraction_counts_implicit_interface_methods(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text(
        """
        public interface Api {
            int size();
            private int hidden() { return 0; }
        }
        """,
        encoding="utf-8",
    )

    signatures = {method.signature for method in public_methods_for_fixture(source)}

    assert signatures == {"Api.size()"}


def test_public_method_extraction_qualifies_nested_classes(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text(
        """
        public class Outer {
            public void top() {}
            public static class Inner {
                public void nested() {}
            }
        }
        """,
        encoding="utf-8",
    )

    signatures = {method.signature for method in public_methods_for_fixture(source)}

    assert "Outer.top()" in signatures
    assert "Outer.Inner.nested()" in signatures
    assert "Inner.nested()" not in signatures


def test_surface_report_counts_verified_and_untestable_buckets() -> None:
    report = build_report(
        [
            PassedMethod(
                fixture="CharUtils.java",
                signature="CharUtils.compare(char,char)",
                nodeid="tests/equivalence/test_char_utils.py::test_compare_less",
            ),
            PassedMethod(
                fixture="NumberUtils.java",
                signature="NumberUtils.toInt(String)",
                nodeid="tests/equivalence/test_number_utils.py::test_to_int_equivalence",
            ),
        ]
    )

    summary = report["summary"]
    char_utils = next(item for item in report["fixtures"] if item["fixture"] == "CharUtils.java")

    assert summary["total_public_methods"] == 152
    assert summary["verified_methods"] == 2
    assert summary["untestable_methods"] == 14
    assert char_utils["total_public_methods"] == 23
    assert char_utils["untestable_methods"] == 14
    assert (
        char_utils["untestable_method_reasons"]["CharUtils.toChar(Character)"]
        == "char/Character overload dispatch currently erases to Python str"
    )


def test_surface_report_adds_library_wide_denominator(monkeypatch: MonkeyPatch) -> None:
    def fake_library_surfaces() -> dict[str, LibrarySurface]:
        return {
            "commons-lang": LibrarySurface(
                library="commons-lang",
                source_available=True,
                source_root="/tmp/commons-lang",
                source_preset="commons-lang-dense",
                total_public_methods=1000,
                source_files=10,
                parse_error_files=0,
                method_signatures=frozenset({"CharUtils.compare(char,char)"}),
            ),
            "guava": LibrarySurface(
                library="guava",
                source_available=True,
                source_root="/tmp/guava",
                source_preset="guava-dense",
                total_public_methods=2000,
                source_files=20,
                parse_error_files=0,
                method_signatures=frozenset({"Strings.isNullOrEmpty(String)"}),
            ),
        }

    monkeypatch.setattr(surface_report, "_library_surfaces", fake_library_surfaces)

    report = build_report(
        [
            PassedMethod(
                fixture="CharUtils.java",
                signature="CharUtils.compare(char,char)",
                nodeid="tests/equivalence/test_char_utils.py::test_compare_less",
            ),
            PassedMethod(
                fixture="GuavaPrecedenceMath.java",
                signature="GuavaPrecedenceMath.expandedCapacity(int)",
                nodeid="tests/equivalence/test_guava_precedence_math.py::test_expanded",
            ),
        ]
    )

    commons_lang = next(item for item in report["libraries"] if item["library"] == "commons-lang")
    guava = next(item for item in report["libraries"] if item["library"] == "guava")

    assert commons_lang["verified_library_methods"] == 1
    assert commons_lang["library_total_public_methods"] == 1000
    assert guava["verified_methods"] == 1
    assert guava["verified_library_methods"] == 0
    assert report["library_wide_summary"]["verified_library_methods"] == 1
    assert report["library_wide_summary"]["library_total_public_methods"] == 3000

    rendered = render_report(report)
    assert f"Equivalence-verified fixture surface ({len(report['fixtures'])} files)" in rendered
    assert "Library-wide denominator" in rendered
    assert "| guava | 0 | 2000 | 0.0% | guava-dense checkout, 20 files |" in rendered


def test_surface_report_removes_verified_methods_from_untestable_bucket() -> None:
    report = build_report(
        [
            PassedMethod(
                fixture="CharUtils.java",
                signature="CharUtils.toChar(Character)",
                nodeid="tests/equivalence/test_char_utils.py::test_to_char_character[A]",
            ),
        ]
    )

    char_utils = next(item for item in report["fixtures"] if item["fixture"] == "CharUtils.java")

    assert char_utils["verified_methods"] == 1
    assert char_utils["untestable_methods"] == 13
    assert "CharUtils.toChar(Character)" not in char_utils["untestable_method_reasons"]

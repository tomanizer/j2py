"""Tests for the equivalence surface metric report."""

from __future__ import annotations

from pathlib import Path

from scripts.equivalence.surface_report import (
    PassedMethod,
    build_report,
    public_methods_for_fixture,
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

    assert summary["total_public_methods"] == 97
    assert summary["verified_methods"] == 2
    assert summary["untestable_methods"] == 14
    assert char_utils["total_public_methods"] == 23
    assert char_utils["untestable_methods"] == 14
    assert (
        char_utils["untestable_method_reasons"]["CharUtils.toChar(Character)"]
        == "char/Character overload dispatch currently erases to Python str"
    )

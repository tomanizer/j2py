"""Tests for translation diagnostics metrics."""

from j2py.translate.diagnostics import TranslationDiagnostic, TranslationDiagnostics


def test_semantic_warnings_do_not_reduce_coverage() -> None:
    diagnostics = TranslationDiagnostics(
        handled=[
            TranslationDiagnostic("method_declaration", 1, "void run()", "handled"),
        ],
        warnings=[
            TranslationDiagnostic("synchronized_statement", 2, "sync", "verify lock semantics"),
        ],
    )

    assert diagnostics.coverage == 1.0
    assert diagnostics.rule_coverage == 1.0
    assert diagnostics.semantic_warning_count == 1

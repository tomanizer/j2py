"""Tests for translation diagnostics metrics."""

from j2py.translate.diagnostics import ImportSet, TranslationDiagnostic, TranslationDiagnostics
from tests.translate.skeleton.helpers import translate_source_with_diagnostics


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


def test_translation_diagnostic_exposes_structured_category_and_facts() -> None:
    diagnostic = TranslationDiagnostic(
        "method_invocation",
        3,
        "values.get(key)",
        "ambiguous get invocation requires receiver collection type",
        category="missing_receiver_type",
        facts={"receiver": "values"},
    )

    assert diagnostic.structured["category"] == "missing_receiver_type"
    assert diagnostic.structured["facts"] == {"receiver": "values"}


def test_missing_receiver_type_diagnostic_has_structured_category() -> None:
    result = translate_source_with_diagnostics(
        """
        class Ambiguous {
            String run(Object values, String key) {
                return values.get(key);
            }
        }
        """,
    )

    diagnostic = result.diagnostics.unhandled[-1]
    assert diagnostic.reason == "ambiguous get invocation requires receiver collection type"
    assert diagnostic.category in {"missing_receiver_type", "opaque_receiver_shape"}
    assert diagnostic.facts["receiver"] == "values"


def test_import_set_combines_explicit_and_inferred_from_imports() -> None:
    imports = ImportSet()
    imports.need_line("from typing import IO")
    imports.need_line("from j2py_runtime import get_mapping")
    imports.need_line("from j2py_runtime import rest_controller")
    imports.need_typing("Iterator")

    assert imports.render() == [
        "from typing import IO, Iterator",
        "",
        "from j2py_runtime import get_mapping, rest_controller",
    ]


def test_import_set_groups_standard_library_imports_before_project_imports() -> None:
    imports = ImportSet()
    imports.need_line("import os")
    imports.need_line("import re")
    imports.need_line("import sys")
    imports.need_line("from j2py_runtime import Optional")

    assert imports.render() == [
        "import os",
        "import re",
        "import sys",
        "",
        "from j2py_runtime import Optional",
    ]

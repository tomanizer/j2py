"""Import-policy coverage for Java platform/external types."""

from __future__ import annotations

import ast

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file, parse_source
from j2py.translate.name_resolution import (
    TypeBinding,
    build_file_name_bindings,
    imported_type_bindings,
)
from j2py.translate.rules.imports import java_import_policy
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.conftest import CORPUS_CONSTRUCT_FIXTURES
from tests.translate.skeleton.helpers import CFG, FIXTURES, translate_source_with_diagnostics


@pytest.mark.parametrize(
    ("java_name", "python_name", "import_lines", "source"),
    [
        ("java.lang.Integer", "Integer", (), "drop_import"),
        (
            "java.util.Comparator",
            "Comparator",
            ("from j2py_runtime import Comparator",),
            "platform_placeholder",
        ),
        (
            "javax.management.ObjectName",
            "ObjectName",
            ("from typing import Any as ObjectName",),
            "platform_placeholder",
        ),
        (
            "javax.management.MalformedObjectNameException",
            "MalformedObjectNameException",
            ("from typing import Any as MalformedObjectNameException",),
            "platform_placeholder",
        ),
        (
            "org.springframework.core.NativeDetector",
            "NativeDetector",
            ("from typing import Any as NativeDetector",),
            "external_placeholder",
        ),
    ],
)
def test_java_import_policy_classifies_evidence_types(
    java_name: str,
    python_name: str,
    import_lines: tuple[str, ...],
    source: str,
) -> None:
    policy = java_import_policy(java_name, CFG)

    assert policy is not None
    assert policy.python_name == python_name
    assert policy.import_lines == import_lines
    assert policy.source == source


def test_platform_import_bindings_do_not_request_java_module_imports() -> None:
    parsed = parse_source(
        """
        package org.springframework.jmx.support;

        import java.util.Comparator;
        import javax.management.ObjectName;
        import javax.management.MalformedObjectNameException;
        import org.springframework.core.NativeDetector;
        import com.example.ProjectType;

        public class UsesImports {}
        """,
    )

    bindings = imported_type_bindings(parsed, CFG)

    assert bindings["Comparator"] == TypeBinding(
        raw_name="Comparator",
        python_name="Comparator",
        import_line="from j2py_runtime import Comparator",
        source="platform_placeholder",
    )
    assert bindings["ObjectName"].import_line == "from typing import Any as ObjectName"
    assert bindings["MalformedObjectNameException"].import_line == (
        "from typing import Any as MalformedObjectNameException"
    )
    assert bindings["NativeDetector"].source == "external_placeholder"
    assert bindings["ProjectType"] == TypeBinding(
        raw_name="ProjectType",
        python_name="ProjectType",
        import_line="from com.example.ProjectType import ProjectType",
    )


def test_implicit_java_lang_type_does_not_become_same_package_import() -> None:
    parsed = parse_source(
        """
        package com.example;

        public class UsesImplicitInteger {
            public int compare(int left, int right) {
                return Integer.compare(left, right);
            }
        }
        """,
    )
    bindings = build_file_name_bindings(parsed, extract_symbols(parsed), CFG)

    resolved = bindings.imported_types.get("Integer")
    assert resolved is None

    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert "from com.example.Integer import Integer" not in result.source
    assert "return (left > right) - (left < right)" in result.source


def test_anonymous_comparator_fixture_has_no_bogus_platform_imports() -> None:
    parsed = parse_file(FIXTURES / "llm" / "AnonymousComparator.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert "from java." not in result.source
    assert "from javax." not in result.source
    assert "from com.example.Integer import Integer" not in result.source
    assert "from j2py_runtime import Comparator" in result.source
    assert "class _J2pyAnonymous1:" in result.source
    assert "class _J2pyAnonymous1(Comparator):" not in result.source
    assert "return (len(a) > len(b)) - (len(a) < len(b))" in result.source


@pytest.mark.parametrize(
    "fixture_path",
    [
        FIXTURES / "llm" / "AnonymousComparator.java",
        CORPUS_CONSTRUCT_FIXTURES / "JdkComparatorAnonymousClass.java",
    ],
    ids=["AnonymousComparator", "JdkComparatorAnonymousClass"],
)
def test_comparator_anonymous_class_uses_runtime_protocol_without_subclassing(
    fixture_path,
) -> None:
    parsed = parse_file(fixture_path)
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from j2py_runtime import Comparator" in result.source
    assert "from java." not in result.source
    assert "class _J2pyAnonymous1:" in result.source
    assert "class _J2pyAnonymous1(Comparator):" not in result.source
    assert "def compare(self, a: str, b: str) -> int:" in result.source


def test_object_name_probe_has_no_bogus_platform_imports() -> None:
    result = translate_source_with_diagnostics(
        """
        package org.springframework.jmx.support;

        import javax.management.ObjectName;
        import javax.management.MalformedObjectNameException;

        public class ObjectNameManagerProbe {
            public ObjectName getInstance(String name) throws MalformedObjectNameException {
                return ObjectName.getInstance(name);
            }
        }
        """,
    )

    ast.parse(result.source)
    assert "from java." not in result.source
    assert "from javax." not in result.source
    assert "from typing import Any as ObjectName" in result.source
    assert "from typing import Any as MalformedObjectNameException" in result.source
    assert "def get_instance(self, name: str) -> ObjectName:" in result.source
    assert "return ObjectName.get_instance(name)" in result.source

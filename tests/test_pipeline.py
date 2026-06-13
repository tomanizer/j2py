"""Tests for the top-level translation pipeline."""

import ast
from pathlib import Path

import j2py.llm.client as llm_client
import j2py.pipeline as pipeline
from j2py.config.loader import ConfigLoader
from j2py.pipeline import (
    PARSE_ERROR_LLM_SKIP_MSG,
    translate_directory,
    translate_file,
)
from j2py.validate.checks import ValidationResult

FIXTURES = Path(__file__).parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()
PARTIAL_FIXTURE = FIXTURES / "java" / "PartialUnsupported.java"
PARTIAL_LLM_OUTPUT = """\
class PartialUnsupported:
    def matrix(self, rows: int, cols: int) -> list[list[int]]:
        return []
"""


def test_translate_file_no_llm_preserves_full_confidence_fixture() -> None:
    result = translate_file(FIXTURES / "java" / "HelloWorld.java", cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence == 1.0
    assert result.diagnostics is not None
    assert result.diagnostics.coverage == 1.0
    assert result.validation is not None
    assert result.validation.ok
    assert result.python_source == (FIXTURES / "python" / "HelloWorld.py").read_text()
    ast.parse(result.python_source)


def test_translate_file_no_llm_returns_partial_confidence_fixture() -> None:
    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence < 1.0
    assert result.diagnostics is not None
    assert result.diagnostics.unhandled
    assert result.validation is not None
    assert "__j2py_todo__('new int[rows][cols]')" in result.python_source
    ast.parse(result.python_source)


def test_translate_file_uses_llm_when_rule_coverage_is_partial(monkeypatch) -> None:
    def fake_translate_with_llm(
        *,
        java_source: str,
        partial_python: str,
        context: str,
        diagnostics: str,
        validation_feedback: str,
        previous_python: str,
        config_fingerprint: str,
        model: str,
    ) -> str:
        assert "public class PartialUnsupported" in java_source
        assert "__j2py_todo__('new int[rows][cols]')" in partial_python
        assert "package: com.example" in context
        assert "array_creation_expression" in diagnostics
        assert validation_feedback == ""
        assert previous_python == ""
        assert config_fingerprint
        assert model == "claude-test"
        return PARTIAL_LLM_OUTPUT

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(
        PARTIAL_FIXTURE,
        cfg=CFG,
        use_llm=True,
        model="claude-test",
    )

    assert result.used_llm
    assert result.confidence < 1.0
    assert result.diagnostics is not None
    assert result.structural_verification is not None
    assert result.structural_verification.ok
    assert result.python_source == PARTIAL_LLM_OUTPUT


def test_translate_file_skips_llm_when_java_parse_has_errors(monkeypatch, tmp_path) -> None:
    broken = tmp_path / "Broken.java"
    broken.write_text("public class Broken { void foo( { }")

    def fail_if_called(**kwargs) -> str:
        raise AssertionError("translate_with_llm should not run on parse errors")

    monkeypatch.setattr(llm_client, "translate_with_llm", fail_if_called)

    result = translate_file(broken, cfg=CFG, use_llm=True)

    assert not result.used_llm
    assert not result.parse_ok
    assert result.confidence == 0.0


def test_translate_directory_reports_parse_error_warnings(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Good.java").write_text("package com.example; public class Good {}")
    (source / "Broken.java").write_text("public class Broken { void foo( { }")

    result = translate_directory(source, tmp_path / "out", cfg=CFG, use_llm=False)

    broken = next(file for file in result.files if file.source_path.name == "Broken.java")
    assert not broken.parse_ok
    assert broken.confidence == 0.0
    assert any(
        "Broken.java" in warning and PARSE_ERROR_LLM_SKIP_MSG in warning
        for warning in result.warnings
    )


def test_translate_file_can_validate_generated_source(monkeypatch) -> None:
    def fake_validate(source: str, path: Path | None = None) -> ValidationResult:
        assert "class HelloWorld" in source
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=True,
        )

    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_file(
        FIXTURES / "java" / "HelloWorld.java",
        cfg=CFG,
        use_llm=False,
        validate=True,
    )

    assert result.validation is not None
    assert result.validation.ok


def test_translate_file_reports_validation_failure_for_invalid_llm_output(
    monkeypatch,
) -> None:
    monkeypatch.setattr(llm_client, "translate_with_llm", lambda **kwargs: "def broken(:\n")

    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=True, validate=True)

    assert result.used_llm
    assert result.validation is not None
    assert not result.validation.ok
    assert result.validation.syntax_errors


def test_translate_file_retries_llm_once_with_validation_feedback(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append((kwargs["validation_feedback"], kwargs["previous_python"]))
        if len(calls) == 1:
            return "def broken(:\n"
        return PARTIAL_LLM_OUTPUT

    def fake_validate(source: str, path: Path | None = None) -> ValidationResult:
        if source.startswith("def broken"):
            return ValidationResult(
                path=path or Path("<string>"),
                syntax_ok=False,
                syntax_errors=["SyntaxError: invalid syntax"],
            )
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=True,
        )

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)
    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=True, validate=True)

    assert result.used_llm
    assert calls[0] == ("", "")
    assert "SyntaxError:" in calls[1][0]
    assert calls[1][1] == "def broken(:\n"
    assert result.python_source == PARTIAL_LLM_OUTPUT
    assert result.validation is not None
    assert result.validation.ok


def test_post_llm_feedback_adds_targeted_repair_hints() -> None:
    validation_path = Path("/tmp/j2py-cache-test/generated.py")
    validation = ValidationResult(
        path=validation_path,
        syntax_ok=True,
        mypy_errors=[
            (
                f"{validation_path}:1: error: Unused \"type: ignore\" comment  "
                "[unused-ignore]"
            ),
            (
                f"{validation_path}:2: error: Overloaded function signature 2 will never be "
                "matched: signature 1's parameter type(s) are the same or broader "
                "[overload-cannot-match]"
            ),
            (
                f"{validation_path}:3: error: Cannot find implementation or library stub "
                "for module com.example"
            ),
            (
                f"{validation_path}:4: error: Missing type arguments for generic type "
                '"tuple"  [type-arg]'
            ),
        ],
    )

    feedback = pipeline._post_llm_feedback(
        validation,
        pipeline.StructuralVerificationResult(errors=[]),
    )

    assert "Repair guidance:" in feedback
    assert "Remove unused # type: ignore comments" in feedback
    assert "Fix unreachable overloads" in feedback
    assert "Do not import unresolved Java packages" in feedback
    assert "Add explicit type arguments" in feedback
    assert str(validation_path) not in feedback
    assert "generated.py:1:" in feedback


def test_translate_file_does_not_retry_when_llm_output_validates_and_verifies(monkeypatch) -> None:
    calls: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        return PARTIAL_LLM_OUTPUT

    def fake_validate(source: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=True,
        )

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)
    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=True, validate=True)

    assert calls == [""]
    assert result.validation is not None
    assert result.validation.ok
    assert result.structural_verification is not None
    assert result.structural_verification.ok


def test_translate_file_retries_llm_once_with_structural_feedback(monkeypatch, tmp_path) -> None:
    source = tmp_path / "DroppedMethod.java"
    source.write_text(
        """
        package com.example;
        public class DroppedMethod {
            public int first() { return 1; }
            public int second() { return 2; }
            public int[][] matrix(int rows, int cols) {
                return new int[rows][cols];
            }
        }
        """,
    )
    calls: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        if len(calls) == 1:
            return """\
class DroppedMethod:
    def first(self) -> int:
        return 1
    def matrix(self, rows: int, cols: int) -> list[list[int]]:
        return []
"""
        return """\
class DroppedMethod:
    def first(self) -> int:
        return 1
    def second(self) -> int:
        return 2
    def matrix(self, rows: int, cols: int) -> list[list[int]]:
        return []
"""

    def fake_validate(source_text: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=True,
        )

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)
    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_file(source, cfg=CFG, use_llm=True)

    assert len(calls) == 2
    assert calls[0] == ""
    assert "Missing method in class DroppedMethod: second" in calls[1]
    assert result.structural_verification is not None
    assert result.structural_verification.ok
    assert "def second" in result.python_source


def test_translate_file_records_structural_failure_when_retry_still_drops_method(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "DroppedMethod.java"
    source.write_text(
        """
        package com.example;
        public class DroppedMethod {
            public int first() { return 1; }
            public int second() { return 2; }
            public int[][] matrix(int rows, int cols) {
                return new int[rows][cols];
            }
        }
        """,
    )
    calls: list[str] = []
    dropped_second = """\
class DroppedMethod:
    def first(self) -> int:
        return 1
    def matrix(self, rows: int, cols: int) -> list[list[int]]:
        return []
"""

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        return dropped_second

    def fake_validate(source_text: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=True,
        )

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)
    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_file(source, cfg=CFG, use_llm=True)

    assert len(calls) == 3
    assert "Missing method in class DroppedMethod: second" in calls[1]
    assert "Missing method in class DroppedMethod: second" in calls[2]
    assert result.structural_verification is not None
    assert not result.structural_verification.ok
    assert result.structural_verification.errors == [
        "Missing method in class DroppedMethod: second",
        "Method order changed in class DroppedMethod: "
        "expected ['first', 'second', 'matrix'], got ['first', 'matrix']",
    ]


def test_translate_file_stops_after_bounded_llm_retries(monkeypatch) -> None:
    calls: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        return "def still_broken(:\n"

    def fake_validate(source: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=False,
            syntax_errors=["SyntaxError: invalid syntax"],
        )

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)
    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=True, validate=True)

    assert len(calls) == 3
    assert calls[0] == ""
    assert "SyntaxError:" in calls[1]
    assert "SyntaxError:" in calls[2]
    assert result.python_source == "def still_broken(:\n"
    assert result.validation is not None
    assert not result.validation.ok


def test_translate_file_still_retries_structural_errors_when_validation_disabled(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        return "def broken(:\n"

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=True, validate=False)

    assert len(calls) == 3
    assert calls[0] == ""
    assert "Structural verification skipped" in calls[1]
    assert "Structural verification skipped" in calls[2]
    assert result.validation is None
    assert result.structural_verification is not None
    assert not result.structural_verification.ok
    assert result.python_source == "def broken(:\n"


def test_translate_directory_uses_dependency_order_and_package_paths(tmp_path: Path) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "Child.java").write_text(
        """
        package com.example;
        import com.example.Base;
        public class Child extends Base {}
        """,
    )
    (source / "Base.java").write_text("package com.example; public class Base {}")

    result = translate_directory(source, output, cfg=CFG, use_llm=False)

    assert [path.name for path in result.order] == ["Base.java", "Child.java"]
    assert [file.output_path for file in result.files] == [
        output / "com" / "example" / "Base.py",
        output / "com" / "example" / "Child.py",
    ]


def test_translate_directory_reuses_parsed_files(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "A.java").write_text("package com.example; public class A {}")
    (source / "B.java").write_text("package com.example; public class B {}")
    real_parse_file = pipeline.parse_file
    calls: list[Path] = []

    def counted_parse_file(path: Path):
        calls.append(path)
        return real_parse_file(path)

    monkeypatch.setattr(pipeline, "parse_file", counted_parse_file)

    result = translate_directory(source, output, cfg=CFG, use_llm=False)

    assert sorted(path.name for path in calls) == ["A.java", "B.java"]
    assert len(calls) == 2
    assert len(result.files) == 2


def test_translate_directory_validates_each_result(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "A.java").write_text("package com.example; public class A {}")
    calls: list[Path | None] = []

    def fake_validate(source_text: str, path: Path | None = None) -> ValidationResult:
        calls.append(path)
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=True,
        )

    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_directory(source, output, cfg=CFG, use_llm=False, validate=True)

    assert calls == [output / "com" / "example" / "A.py"]
    assert result.files[0].validation is not None
    assert result.files[0].validation.ok


def test_translate_directory_surfaces_cycle_warnings(tmp_path: Path) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "A.java").write_text("package com.example; public class A extends B {}")
    (source / "B.java").write_text("package com.example; public class B extends A {}")

    result = translate_directory(source, output, cfg=CFG, use_llm=False)

    assert sorted(path.name for path in result.order) == ["A.java", "B.java"]
    assert result.warnings
    assert "Circular dependencies" in result.warnings[0]

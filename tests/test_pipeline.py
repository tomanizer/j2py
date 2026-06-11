"""Tests for the top-level translation pipeline."""

import ast
from pathlib import Path

import j2py.llm.client as llm_client
import j2py.pipeline as pipeline
from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_directory, translate_file
from j2py.validate.checks import ValidationResult

FIXTURES = Path(__file__).parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()
PARTIAL_FIXTURE = FIXTURES / "java" / "PartialUnsupported.java"


def test_translate_file_no_llm_preserves_full_confidence_fixture() -> None:
    result = translate_file(FIXTURES / "java" / "HelloWorld.java", cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence == 1.0
    assert result.diagnostics is not None
    assert result.diagnostics.coverage == 1.0
    assert result.validation is None
    assert result.python_source == (FIXTURES / "python" / "HelloWorld.py").read_text()
    ast.parse(result.python_source)


def test_translate_file_no_llm_returns_partial_confidence_fixture() -> None:
    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence < 1.0
    assert result.diagnostics is not None
    assert result.diagnostics.unhandled
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
        config_fingerprint: str,
        model: str,
    ) -> str:
        assert "public class PartialUnsupported" in java_source
        assert "__j2py_todo__('new int[rows][cols]')" in partial_python
        assert "package: com.example" in context
        assert "array_creation_expression" in diagnostics
        assert validation_feedback == ""
        assert config_fingerprint
        assert model == "claude-test"
        return "class PartialUnsupported:\n    pass\n"

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
    assert result.python_source == "class PartialUnsupported:\n    pass\n"


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
    calls: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        if len(calls) == 1:
            return "def broken(:\n"
        return "class PartialUnsupported:\n    pass\n"

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
    assert calls[0] == ""
    assert "SyntaxError:" in calls[1]
    assert result.python_source == "class PartialUnsupported:\n    pass\n"
    assert result.validation is not None
    assert result.validation.ok


def test_translate_file_does_not_retry_when_llm_output_validates(monkeypatch) -> None:
    calls: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        return "class PartialUnsupported:\n    pass\n"

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


def test_translate_file_does_not_loop_when_llm_retry_still_fails(monkeypatch) -> None:
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

    assert len(calls) == 2
    assert calls[0] == ""
    assert "SyntaxError:" in calls[1]
    assert result.python_source == "def still_broken(:\n"
    assert result.validation is not None
    assert not result.validation.ok


def test_translate_file_does_not_retry_when_validation_disabled(monkeypatch) -> None:
    calls: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        calls.append(kwargs["validation_feedback"])
        return "def broken(:\n"

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=True)

    assert calls == [""]
    assert result.validation is None
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

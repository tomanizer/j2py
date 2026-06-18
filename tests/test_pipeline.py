"""Tests for the top-level translation pipeline."""

import ast
import json
from pathlib import Path

import j2py.llm.client as llm_client
import j2py.pipeline as pipeline
import j2py.translate.skeleton as skeleton_module
from j2py.analyze.symbols import FileSymbols
from j2py.config.loader import ConfigLoader
from j2py.llm.review import LlmReviewFinding
from j2py.pipeline import (
    PARSE_ERROR_LLM_SKIP_MSG,
    translate_directory,
    translate_file,
)
from j2py.state import entry_from_result, save_state, source_key
from j2py.translate.diagnostics import TranslationDiagnostic, TranslationDiagnostics
from j2py.translate.skeleton import SkeletonTranslation
from j2py.validate.checks import ValidationResult
from tests.fixtures.framework.reference_plugin import ReferenceFrameworkPlugin

FIXTURES = Path(__file__).parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()
PARTIAL_FIXTURE = FIXTURES / "java" / "PartialUnsupported.java"
PARTIAL_LLM_OUTPUT = """\
class PartialUnsupported:
    def matrix(self, rows: int, cols: int) -> list[list[int]]:
        return [[0] * cols for _ in range(rows)]

    def check(self, value: int) -> None:
        return

    def stop(self) -> None:
        while True:
            break
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


def test_translate_file_llm_review_runs_for_full_confidence_fixture(monkeypatch) -> None:
    expected_python = (FIXTURES / "python" / "HelloWorld.py").read_text()
    observed: dict[str, object] = {}

    def fake_review_translation_with_llm(**kwargs) -> list[LlmReviewFinding]:
        observed.update(kwargs)
        return [
            LlmReviewFinding(
                severity="warning",
                category="semantics",
                source_line=6,
                output_line=8,
                message="Verify constructor initialization semantics.",
                recommendation="Compare with Java behavior tests.",
            )
        ]

    monkeypatch.setattr(
        llm_client,
        "review_translation_with_llm",
        fake_review_translation_with_llm,
    )

    result = translate_file(
        FIXTURES / "java" / "HelloWorld.java",
        cfg=CFG,
        use_llm=False,
        llm_review=True,
        model="claude-review-test",
    )

    assert not result.used_llm
    assert result.llm_review_ran
    assert result.confidence == 1.0
    assert result.python_source == expected_python
    assert result.llm_review_findings[0].message == "Verify constructor initialization semantics."
    assert observed["provider"] == "anthropic"
    assert observed["model"] == "claude-review-test"
    assert "public class HelloWorld" in observed["java_source"]
    assert expected_python == observed["python_source"]
    assert observed["validation_summary"] == "Validation passed."


def test_translate_file_llm_review_disabled_preserves_current_behavior(monkeypatch) -> None:
    def fake_review_translation_with_llm(**kwargs) -> list[LlmReviewFinding]:
        raise AssertionError("review should not run")

    monkeypatch.setattr(
        llm_client,
        "review_translation_with_llm",
        fake_review_translation_with_llm,
    )

    result = translate_file(FIXTURES / "java" / "HelloWorld.java", cfg=CFG, use_llm=False)

    assert not result.llm_review_ran
    assert result.llm_review_findings == []
    assert result.llm_review_error is None


def test_translate_file_llm_review_scope_low_confidence_skips_full_confidence(
    monkeypatch,
) -> None:
    def fake_review_translation_with_llm(**kwargs) -> list[LlmReviewFinding]:
        raise AssertionError("review should not run")

    monkeypatch.setattr(
        llm_client,
        "review_translation_with_llm",
        fake_review_translation_with_llm,
    )

    result = translate_file(
        FIXTURES / "java" / "HelloWorld.java",
        cfg=CFG,
        use_llm=False,
        llm_review=True,
        llm_review_scope="low-confidence",
    )

    assert result.confidence == 1.0
    assert not result.llm_review_ran


def test_translate_file_llm_review_failure_does_not_corrupt_output(monkeypatch) -> None:
    expected_python = (FIXTURES / "python" / "HelloWorld.py").read_text()

    def fake_review_translation_with_llm(**kwargs) -> list[LlmReviewFinding]:
        raise RuntimeError("review provider unavailable")

    monkeypatch.setattr(
        llm_client,
        "review_translation_with_llm",
        fake_review_translation_with_llm,
    )

    result = translate_file(
        FIXTURES / "java" / "HelloWorld.java",
        cfg=CFG,
        use_llm=False,
        llm_review=True,
    )

    assert result.python_source == expected_python
    assert result.confidence == 1.0
    assert result.llm_review_ran
    assert result.llm_review_findings == []
    assert result.llm_review_error == "review provider unavailable"


def test_translate_directory_llm_review_scope_warnings_selects_only_warning_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    output_root = tmp_path / "out"
    source_root.mkdir()
    (source_root / "Plain.java").write_text(
        """
        public class Plain {
            public int value() {
                return 1;
            }
        }
        """,
    )
    (source_root / "Division.java").write_text(
        """
        public class Division {
            public int half(int value) {
                return value / 2;
            }
        }
        """,
    )
    reviewed: list[str] = []

    def fake_review_translation_with_llm(**kwargs) -> list[LlmReviewFinding]:
        reviewed.append(Path(str(kwargs["source_path"])).name)
        return []

    monkeypatch.setattr(
        llm_client,
        "review_translation_with_llm",
        fake_review_translation_with_llm,
    )

    batch = translate_directory(
        source_root,
        output_root,
        cfg=CFG,
        use_llm=False,
        llm_review=True,
        llm_review_scope="warnings",
        validate=False,
        workers=1,
    )

    assert reviewed == ["Division.java"]
    by_name = {result.source_path.name: result for result in batch.files}
    assert by_name["Division.java"].llm_review_ran
    assert not by_name["Plain.java"].llm_review_ran


def test_translate_directory_llm_review_receives_validation_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    output_root = tmp_path / "out"
    source_root.mkdir()
    (source_root / "Plain.java").write_text(
        """
        public class Plain {
            public int value() {
                return 1;
            }
        }
        """,
    )
    observed: dict[str, object] = {}

    def fake_review_translation_with_llm(**kwargs) -> list[LlmReviewFinding]:
        observed.update(kwargs)
        return []

    monkeypatch.setattr(
        llm_client,
        "review_translation_with_llm",
        fake_review_translation_with_llm,
    )

    batch = translate_directory(
        source_root,
        output_root,
        cfg=CFG,
        use_llm=False,
        llm_review=True,
        validate=True,
        workers=1,
    )

    assert batch.files[0].llm_review_ran
    assert observed["validation_summary"] == "Validation passed."


def test_translate_file_no_llm_returns_partial_confidence_fixture() -> None:
    result = translate_file(PARTIAL_FIXTURE, cfg=CFG, use_llm=False)

    assert not result.used_llm
    assert result.confidence < 1.0
    assert result.diagnostics is not None
    assert result.diagnostics.unhandled
    assert result.validation is not None
    assert "return [[0] * cols for _ in range(rows)]" in result.python_source
    assert "# label: positive" in result.python_source
    assert "# TODO(j2py): unsupported labeled_statement target outer" in result.python_source
    ast.parse(result.python_source)


def test_translate_file_clamps_confidence_for_semantic_warnings(tmp_path: Path) -> None:
    source = tmp_path / "Division.java"
    source.write_text(
        """
        public class Division {
            public int half(int value) {
                return value / 2;
            }
        }
        """,
    )

    result = translate_file(source, cfg=CFG, use_llm=False, validate=True)

    assert result.diagnostics is not None
    assert result.diagnostics.coverage == 1.0
    assert result.diagnostics.semantic_warning_count > 0
    assert result.validation is not None
    assert result.validation.ok
    assert result.confidence == 0.99


def test_translate_file_clamps_confidence_for_validation_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Broken.java"
    source.write_text("public class Broken {}")

    def fake_skeleton(*args, **kwargs) -> SkeletonTranslation:
        diagnostics = TranslationDiagnostics()
        diagnostics.handled.append(
            TranslationDiagnostic(
                node_type="class_declaration",
                line=1,
                text="public class Broken {}",
                reason="fake full coverage",
            )
        )
        return SkeletonTranslation(
            source="def broken(:\n",
            coverage=1.0,
            diagnostics=diagnostics,
        )

    def fake_validate(source_text: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=False,
            syntax_errors=["SyntaxError: invalid syntax"],
        )

    monkeypatch.setattr(
        skeleton_module,
        "translate_skeleton_with_diagnostics",
        fake_skeleton,
    )
    monkeypatch.setattr(pipeline, "validate_source", fake_validate)

    result = translate_file(source, cfg=CFG, use_llm=False, validate=True)

    assert result.diagnostics is not None
    assert result.diagnostics.coverage == 1.0
    assert result.validation is not None
    assert not result.validation.ok
    # Syntactically invalid output is never reviewable → confidence must be 0.
    assert result.confidence == 0.0


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
        model: str | None,
        provider: str,
        base_url: str | None,
    ) -> str:
        assert "public class PartialUnsupported" in java_source
        assert "return [[0] * cols for _ in range(rows)]" in partial_python
        assert "# label: positive" in partial_python
        assert "# TODO(j2py): unsupported labeled_statement target outer" in partial_python
        assert "package: com.example" in context
        assert "unsupported labeled break/continue target outer" in diagnostics
        assert validation_feedback == ""
        assert previous_python == ""
        assert config_fingerprint
        assert model == "claude-test"
        assert provider == "anthropic"
        assert base_url is None
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


def test_translate_file_forwards_gemini_provider_to_llm(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_translate_with_llm(**kwargs) -> str:
        observed.update(kwargs)
        return PARTIAL_LLM_OUTPUT

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(
        PARTIAL_FIXTURE,
        cfg=CFG,
        use_llm=True,
        model="gemini-test",
        llm_provider="gemini",
    )

    assert result.used_llm
    assert observed["provider"] == "gemini"
    assert observed["model"] == "gemini-test"


def test_translate_file_uses_configured_llm_defaults(monkeypatch) -> None:
    observed: dict[str, object] = {}
    cfg = CFG.model_copy(
        update={
            "llm_provider": "gemini",
            "model": "gemini-config",
        },
    )

    def fake_translate_with_llm(**kwargs) -> str:
        observed.update(kwargs)
        return PARTIAL_LLM_OUTPUT

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(PARTIAL_FIXTURE, cfg=cfg, use_llm=True)

    assert result.used_llm
    assert observed["provider"] == "gemini"
    assert observed["model"] == "gemini-config"


def test_translate_file_passes_configured_openai_base_url(monkeypatch) -> None:
    observed: dict[str, object] = {}
    cfg = CFG.model_copy(
        update={
            "llm_provider": "openai",
            "llm_base_url": "https://provider.example/v1",
            "model": "provider-model-id",
        },
    )

    def fake_translate_with_llm(**kwargs) -> str:
        observed.update(kwargs)
        return PARTIAL_LLM_OUTPUT

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(PARTIAL_FIXTURE, cfg=cfg, use_llm=True)

    assert result.used_llm
    assert observed["provider"] == "openai"
    assert observed["model"] == "provider-model-id"
    assert observed["base_url"] == "https://provider.example/v1"


def test_translate_file_uses_full_prevalidation_for_invalid_full_coverage_skeleton(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Broken.java"
    source.write_text("package com.example; public class Broken {}")
    validation_calls: list[str] = []
    llm_feedback: list[str] = []

    def fake_skeleton(*args, **kwargs) -> SkeletonTranslation:
        return SkeletonTranslation(
            source="def broken(:\n",
            coverage=1.0,
            diagnostics=TranslationDiagnostics(),
        )

    def fake_validate(source_text: str, path: Path | None = None) -> ValidationResult:
        validation_calls.append(source_text)
        if source_text.startswith("def broken"):
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

    def fake_translate_with_llm(**kwargs) -> str:
        llm_feedback.append(kwargs["validation_feedback"])
        return "class Broken:\n    pass\n"

    monkeypatch.setattr(
        skeleton_module,
        "translate_skeleton_with_diagnostics",
        fake_skeleton,
    )
    monkeypatch.setattr(pipeline, "validate_source", fake_validate)
    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_file(source, cfg=CFG, use_llm=True, validate=True)

    assert result.used_llm
    assert validation_calls == ["def broken(:\n", "class Broken:\n    pass\n"]
    assert llm_feedback == ["SyntaxError: invalid syntax"]
    assert result.validation is not None
    assert result.validation.ok


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


def test_wiring_metadata_payload_and_sidecar_are_versioned(tmp_path: Path) -> None:
    source = tmp_path / "Orders.java"
    output = tmp_path / "out" / "Orders.py"
    source.write_text(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
    )
    cfg = CFG.model_copy(update={"framework_plugins": [ReferenceFrameworkPlugin()]})

    result = translate_file(source, cfg=cfg, use_llm=False, validate=False)
    result.output_path = output
    payload = pipeline.wiring_metadata_payload(result)

    assert payload == {
        "schema_version": 1,
        "source": str(source),
        "output": str(output),
        "elements": [
            {
                "plugin": "reference",
                "kind": "class",
                "java_name": "Orders",
                "python_name": "Orders",
                "annotations": [
                    {
                        "name": "MappedController",
                        "simple_name": "MappedController",
                        "values": {},
                    },
                ],
                "metadata": {"controller": "Orders"},
            },
        ],
    }

    sidecar = pipeline.write_wiring_metadata_sidecar(result)

    assert sidecar == output.with_suffix(".wiring.json")
    assert sidecar is not None
    assert json.loads(sidecar.read_text()) == payload


def test_wiring_metadata_payload_is_empty_without_metadata(tmp_path: Path) -> None:
    source = tmp_path / "Plain.java"
    source.write_text("public class Plain {}")

    result = translate_file(source, cfg=CFG, use_llm=False, validate=False)
    result.output_path = tmp_path / "Plain.py"

    assert pipeline.wiring_metadata_payload(result) is None
    assert pipeline.write_wiring_metadata_sidecar(result) is None


def test_wiring_metadata_sidecar_is_removed_when_metadata_disappears(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Plain.java"
    output = tmp_path / "Plain.py"
    sidecar = output.with_suffix(".wiring.json")
    source.write_text("public class Plain {}")
    sidecar.write_text('{"stale": true}\n')

    result = translate_file(source, cfg=CFG, use_llm=False, validate=False)
    result.output_path = output

    assert pipeline.write_wiring_metadata_sidecar(result) is None
    assert not sidecar.exists()


def test_config_fingerprint_handles_framework_plugins() -> None:
    cfg = CFG.model_copy(update={"framework_plugins": [ReferenceFrameworkPlugin()]})

    fingerprint = pipeline._config_fingerprint(cfg)

    payload = json.loads(fingerprint)
    assert payload["framework_plugins"] == ["reference"]


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
            (f'{validation_path}:1: error: Unused "type: ignore" comment  [unused-ignore]'),
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
            public int first() { done: while (true) { break done; } return 1; }
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
            public int first() { done: while (true) { break done; } return 1; }
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
    calls: list[dict[Path, str]] = []

    def fake_validate_directory(files: dict[Path, str]) -> dict[Path, ValidationResult]:
        calls.append(files)
        return {
            path: ValidationResult(
                path=path,
                syntax_ok=True,
                mypy_ok=True,
                ruff_ok=True,
            )
            for path in files
        }

    monkeypatch.setattr(pipeline, "validate_directory", fake_validate_directory)

    result = translate_directory(source, output, cfg=CFG, use_llm=False, validate=True)

    assert len(calls) == 1
    assert list(calls[0]) == [output / "com" / "example" / "A.py"]
    assert result.files[0].validation is not None
    assert result.files[0].validation.ok


def test_translate_directory_clamps_confidence_after_batched_validation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "A.java").write_text("package com.example; public class A {}")

    def fake_validate_directory(files: dict[Path, str]) -> dict[Path, ValidationResult]:
        return {
            path: ValidationResult(
                path=path,
                syntax_ok=True,
                ruff_ok=True,
                mypy_ok=False,
                mypy_errors=["A.py:1: error: simulated failure"],
            )
            for path in files
        }

    monkeypatch.setattr(pipeline, "validate_directory", fake_validate_directory)

    result = translate_directory(source, output, cfg=CFG, use_llm=False, validate=True)

    translated = result.files[0]
    assert translated.diagnostics is not None
    assert translated.diagnostics.coverage == 1.0
    assert translated.validation is not None
    assert not translated.validation.ok
    assert translated.confidence == pipeline.REVIEW_REQUIRED_CONFIDENCE_CAP


def test_translate_directory_clamps_confidence_to_zero_on_syntax_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "A.java").write_text("package com.example; public class A {}")

    def fake_validate_directory(files: dict[Path, str]) -> dict[Path, ValidationResult]:
        return {
            path: ValidationResult(
                path=path,
                syntax_ok=False,
                syntax_errors=["SyntaxError: invalid syntax (<string>, line 1)"],
                ruff_ok=False,
                mypy_ok=False,
            )
            for path in files
        }

    monkeypatch.setattr(pipeline, "validate_directory", fake_validate_directory)

    result = translate_directory(source, output, cfg=CFG, use_llm=False, validate=True)

    translated = result.files[0]
    assert translated.confidence == 0.0


def test_translate_directory_batches_full_coverage_llm_prevalidation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    for name in ["A", "B", "C"]:
        (source / f"{name}.java").write_text(
            f"package com.example; public class {name} {{}}",
        )
    validate_source_calls: list[str] = []
    validate_directory_calls: list[dict[Path, str]] = []

    def fake_validate_source(source_text: str, path: Path | None = None) -> ValidationResult:
        validate_source_calls.append(source_text)
        raise AssertionError("directory translation should use batched validation")

    def fake_validate_directory(files: dict[Path, str]) -> dict[Path, ValidationResult]:
        validate_directory_calls.append(files)
        return {
            path: ValidationResult(
                path=path,
                syntax_ok=True,
                mypy_ok=True,
                ruff_ok=True,
            )
            for path in files
        }

    monkeypatch.setattr(pipeline, "validate_source", fake_validate_source)
    monkeypatch.setattr(pipeline, "validate_directory", fake_validate_directory)

    result = translate_directory(source, output, cfg=CFG, use_llm=True, validate=True)

    assert validate_source_calls == []
    assert len(validate_directory_calls) == 1
    assert sorted(path.name for path in validate_directory_calls[0]) == [
        "A.py",
        "B.py",
        "C.py",
    ]
    assert not any(file.used_llm for file in result.files)
    assert all(file.validation is not None and file.validation.ok for file in result.files)


def test_translate_directory_passes_direct_sibling_signatures_to_llm(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "Person.java").write_text(
        """
        package com.example;

        public class Person {
            public int id() {
                return 1;
            }
        }
        """,
    )
    (source / "PersonService.java").write_text(
        """
        package com.example;

        import com.example.Person;

        public class PersonService {
            public Person passthrough(Person person) {
                return person;
            }

            public int[][] matrix(int rows, int cols) {
                ready:
                while (true) {
                    break ready;
                }
                return new int[rows][cols];
            }
        }
        """,
    )
    contexts: list[str] = []

    def fake_translate_with_llm(**kwargs) -> str:
        contexts.append(kwargs["context"])
        return """\
class PersonService:
    def passthrough(self, person: Person) -> Person:
        return person

    def matrix(self, rows: int, cols: int) -> list[list[int]]:
        return []
"""

    monkeypatch.setattr(llm_client, "translate_with_llm", fake_translate_with_llm)

    result = translate_directory(
        source,
        output,
        cfg=CFG,
        use_llm=True,
        validate=False,
    )

    assert [path.name for path in result.order] == ["Person.java", "PersonService.java"]
    service = next(file for file in result.files if file.source_path.name == "PersonService.java")
    assert service.used_llm
    assert len(contexts) == 1
    assert "Already-translated sibling classes:" in contexts[0]
    assert "- Person: class Person" in contexts[0]
    assert "id_(self) -> int" in contexts[0]


def test_direct_import_signatures_are_package_aware() -> None:
    symbols = FileSymbols(
        path=Path("src/com/app/UseHelpers.java"),
        package="com.app",
        imports=["org.shared.Helper", "com.wildcard"],
    )

    result = pipeline._direct_import_signatures(
        symbols,
        {
            "com.app": {"LocalHelper": "class LocalHelper"},
            "org.shared": {"Helper": "class SharedHelper"},
            "com.wildcard": {"WildcardHelper": "class WildcardHelper"},
            "com.other": {"Helper": "class WrongHelper"},
        },
    )

    assert result == {
        "LocalHelper": "class LocalHelper",
        "Helper": "class SharedHelper",
        "WildcardHelper": "class WildcardHelper",
    }


def test_extract_python_signatures_includes_varargs_and_keyword_args() -> None:
    result = pipeline._extract_python_signatures(
        """\
class Collector:
    def collect(
        self,
        first: str,
        *items: str,
        required: bool,
        **extra: object,
    ) -> list[str]:
        return [first, *items]
"""
    )

    assert result == {
        "Collector": (
            "class Collector; methods=["
            "'collect(self, first: str, *items: str, required: bool, "
            "**extra: object) -> list[str]'"
            "]"
        )
    }


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


def test_translate_directory_incremental_skips_unchanged_outputs(tmp_path: Path) -> None:
    source = tmp_path / "src"
    output = tmp_path / "out"
    source.mkdir()
    (source / "Base.java").write_text("package com.example; public class Base {}")
    (source / "Child.java").write_text(
        """
        package com.example;
        import com.example.Base;
        public class Child extends Base {}
        """,
    )

    first = translate_directory(source, output, cfg=CFG, use_llm=False, validate=False)
    for result in first.files:
        assert result.output_path is not None
        result.output_path.parent.mkdir(parents=True, exist_ok=True)
        result.output_path.write_text(result.python_source)
    save_state(
        output,
        {
            source_key(result.source_path, source): entry_from_result(
                result,
                source_root=source,
                output_root=output,
            )
            for result in first.files
        },
    )

    second = translate_directory(
        source,
        output,
        cfg=CFG,
        use_llm=False,
        validate=False,
        incremental=True,
    )

    assert second.skipped_count == 2
    assert second.translated_count == 0
    assert all(result.skipped for result in second.files)

    (source / "Base.java").write_text(
        "package com.example; public class Base { public int id() { return 1; } }",
    )

    third = translate_directory(
        source,
        output,
        cfg=CFG,
        use_llm=False,
        validate=False,
        incremental=True,
    )

    assert third.skipped_count == 0
    assert third.translated_count == 2
    assert not any(result.skipped for result in third.files)


def test_translate_directory_workers_one_matches_parallel_output(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "A.java").write_text("package com.example; public class A {}")
    (source / "B.java").write_text("package com.example; public class B {}")
    cfg = ConfigLoader().add_defaults().build()

    sequential = translate_directory(
        source,
        tmp_path / "out1",
        cfg=cfg,
        use_llm=False,
        validate=False,
        workers=1,
    )
    parallel = translate_directory(
        source,
        tmp_path / "out2",
        cfg=cfg,
        use_llm=False,
        validate=False,
        workers=4,
    )

    assert [item.python_source for item in sequential.files] == [
        item.python_source for item in parallel.files
    ]

"""CLI smoke tests."""

import json
from pathlib import Path

from typer.testing import CliRunner

import j2py.pipeline as pipeline
from j2py.cli.main import app
from j2py.validate.checks import ValidationResult
from j2py.verify.structure import StructuralVerificationResult

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_cli_translate_dry_run_without_llm() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(FIXTURES / "java" / "HelloWorld.java"),
            "--no-llm",
            "--no-validate",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "class HelloWorld:" in result.output
    assert "def get_name" in result.output


def test_cli_translate_auto_discovery_ignores_python_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    (tmp_path / "j2py_config.py").write_text(
        "raise RuntimeError('auto-discovered Python config executed')\n",
    )
    observed_target_python: list[str] = []

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        observed_target_python.append(cfg.target_python)
        return pipeline.TranslationResult(
            source_path=path,
            python_source="class Sample:\n    pass\n",
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--dry-run"],
    )

    assert result.exit_code == 0
    assert observed_target_python == ["3.11"]


def test_cli_translate_help_uses_provider_neutral_llm_wording() -> None:
    from typer.main import get_command

    translate_cmd = get_command(app).commands["translate"]
    option_help = {
        opt: param.help or ""
        for param in translate_cmd.params
        for opt in getattr(param, "opts", ())
    }

    assert "--llm-provider" in option_help
    assert "anthropic or gemini" in option_help["--llm-provider"]
    assert "LLM model ID" in option_help["--model"]
    assert "ANTHROPIC_API_KEY" not in option_help["--llm"]
    assert "Claude model" not in option_help["--model"]


def test_cli_translate_forwards_llm_provider_and_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    observed: dict[str, object] = {}

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        observed.update(
            {
                "use_llm": use_llm,
                "model": model,
                "llm_provider": llm_provider,
                "validate": validate,
            }
        )
        return pipeline.TranslationResult(
            source_path=path,
            python_source="class Sample:\n    pass\n",
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--llm-provider",
            "gemini",
            "--model",
            "gemini-test",
            "--no-validate",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert observed == {
        "use_llm": True,
        "model": "gemini-test",
        "llm_provider": "gemini",
        "validate": False,
    }


def test_cli_translate_uses_configured_llm_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    (tmp_path / "j2py.toml").write_text(
        """
llm_provider = "gemini"
model = "gemini-3.5-flash"
""",
    )
    observed: dict[str, object] = {}

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        observed.update({"model": model, "llm_provider": llm_provider})
        return pipeline.TranslationResult(
            source_path=path,
            python_source="class Sample:\n    pass\n",
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-validate", "--dry-run"],
    )

    assert result.exit_code == 0
    assert observed == {
        "model": "gemini-3.5-flash",
        "llm_provider": "gemini",
    }


def test_cli_translate_llm_flags_override_config_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    (tmp_path / "j2py.toml").write_text(
        """
llm_provider = "gemini"
model = "gemini-3.5-flash"
""",
    )
    observed: dict[str, object] = {}

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        observed.update({"model": model, "llm_provider": llm_provider})
        return pipeline.TranslationResult(
            source_path=path,
            python_source="class Sample:\n    pass\n",
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--llm-provider",
            "anthropic",
            "--model",
            "claude-test",
            "--no-validate",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert observed == {
        "model": "claude-test",
        "llm_provider": "anthropic",
    }


def test_cli_translate_rejects_unknown_llm_provider(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--llm-provider", "unknown", "--dry-run"],
    )

    assert result.exit_code != 0
    assert "unsupported LLM provider" in result.output


def test_cli_translate_writes_wiring_metadata_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "Orders.java"
    output = tmp_path / "Orders.py"
    config = tmp_path / "j2py_config.py"
    source.write_text(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
    )
    config.write_text(
        "\n".join(
            [
                "from tests.fixtures.framework.reference_plugin import (",
                "    ReferenceFrameworkPlugin as _ReferenceFrameworkPlugin,",
                ")",
                "framework_plugins = [_ReferenceFrameworkPlugin()]",
                "emit_wiring_metadata = True",
            ],
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--output",
            str(output),
            "--config",
            str(config),
            "--no-llm",
            "--no-validate",
        ],
    )

    assert result.exit_code == 0
    assert output.exists()
    sidecar = output.with_suffix(".wiring.json")
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text())
    assert payload["schema_version"] == 1
    assert payload["source"] == str(source)
    assert payload["output"] == str(output)
    assert payload["elements"][0]["metadata"] == {"controller": "Orders"}


def test_cli_translate_removes_stale_wiring_metadata_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "Orders.java"
    output = tmp_path / "Orders.py"
    config = tmp_path / "j2py_config.py"
    source.write_text(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
    )
    config.write_text(
        "\n".join(
            [
                "from tests.fixtures.framework.reference_plugin import (",
                "    ReferenceFrameworkPlugin as _ReferenceFrameworkPlugin,",
                ")",
                "framework_plugins = [_ReferenceFrameworkPlugin()]",
                "emit_wiring_metadata = True",
            ],
        ),
    )
    runner = CliRunner()
    args = [
        "translate",
        str(source),
        "--output",
        str(output),
        "--config",
        str(config),
        "--no-llm",
        "--no-validate",
    ]

    first = runner.invoke(app, args)
    sidecar = output.with_suffix(".wiring.json")
    assert first.exit_code == 0
    assert sidecar.exists()

    source.write_text(
        """
        public class Orders {
        }
        """,
    )
    second = runner.invoke(app, args)

    assert second.exit_code == 0
    assert not sidecar.exists()


def test_cli_analyze_prints_record_and_nested_inventory() -> None:
    runner = CliRunner()
    target = FIXTURES / "java" / "targets" / "NestedTypes.java"

    result = runner.invoke(app, ["analyze", str(target)])

    assert result.exit_code == 0
    assert "Entry (record)" in result.output
    assert "2 fields" in result.output


def test_cli_analyze_prints_deeply_nested_inventory(tmp_path: Path) -> None:
    source = tmp_path / "Deep.java"
    source.write_text(
        """
        public class Outer {
            public static class Middle {
                public static class Inner {}
            }
        }
        """,
    )
    runner = CliRunner()

    result = runner.invoke(app, ["analyze", str(source)])

    assert result.exit_code == 0
    assert "Outer (class)" in result.output
    assert "Middle (class)" in result.output
    assert "Inner (class)" in result.output


def test_cli_analyze_prints_class_inventory() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["analyze", str(FIXTURES / "java" / "HelloWorld.java")])

    assert result.exit_code == 0
    assert "HelloWorld" in result.output
    assert "5 methods" in result.output
    assert "2 fields" in result.output
    assert "Translation order:" in result.output


def test_cli_analyze_prints_dependency_graph_for_directory(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Child.java").write_text(
        """
        package com.example;
        import com.example.Base;
        public class Child extends Base {}
        """,
    )
    (source / "Base.java").write_text("package com.example; public class Base {}")
    runner = CliRunner()

    result = runner.invoke(app, ["analyze", str(source)])

    assert result.exit_code == 0
    assert "Dependency graph" in result.output
    assert "Child.java → Base.java" in result.output
    assert "Translation order:" in result.output
    assert "1. Base.java" in result.output
    assert "2. Child.java" in result.output


def test_cli_translate_directory_reports_dependency_order(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Child.java").write_text(
        """
        package com.example;
        import com.example.Base;
        public class Child extends Base {}
        """,
    )
    (source / "Base.java").write_text("package com.example; public class Base {}")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Translation order:" in result.output
    assert "1. Base.java" in result.output
    assert "2. Child.java" in result.output


def test_cli_translate_directory_uses_configured_llm_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Sample.java").write_text("public class Sample {}")
    (source / "j2py.toml").write_text(
        """
llm_provider = "gemini"
model = "gemini-3.5-flash"
""",
    )
    output = tmp_path / "out"
    observed: dict[str, object] = {}

    def fake_translate_directory(
        source_root: Path,
        output_root: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
        workers: int | None = None,
        llm_concurrency: int | None = None,
        incremental: bool = False,
    ) -> pipeline.DirectoryTranslationResult:
        observed.update({"model": model, "llm_provider": llm_provider})
        result = pipeline.TranslationResult(
            source_path=source_root / "Sample.java",
            python_source="class Sample:\n    pass\n",
            output_path=output_root / "Sample.py",
        )
        return pipeline.DirectoryTranslationResult(
            source_root=source_root,
            output_root=output_root,
            files=[result],
            order=[source_root / "Sample.java"],
            warnings=[],
        )

    monkeypatch.setattr(pipeline, "translate_directory", fake_translate_directory)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--output",
            str(output),
            "--no-validate",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert observed == {
        "model": "gemini-3.5-flash",
        "llm_provider": "gemini",
    }


def test_cli_translate_exits_nonzero_on_validation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    output = tmp_path / "Sample.py"

    def fake_validate(source_text: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=False,
            ruff_errors=["ruff failed"],
        )

    monkeypatch.setattr(pipeline, "validate_source", fake_validate)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--output", str(output)],
    )

    assert result.exit_code == 1
    assert "Validation issues:" in result.output
    assert "ruff failed" in result.output


def test_cli_translate_exits_nonzero_on_structural_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        return pipeline.TranslationResult(
            source_path=path,
            python_source="class Sample:\n    pass\n",
            used_llm=True,
            structural_verification=StructuralVerificationResult(
                errors=["Missing method in class Sample: run"],
            ),
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(app, ["translate", str(source), "--no-validate", "--dry-run"])

    assert result.exit_code == 1
    assert "Structural verification issues:" in result.output
    assert "Missing method in class Sample: run" in result.output


def test_cli_translate_directory_exits_nonzero_on_structural_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Sample.java").write_text("public class Sample {}")
    output = tmp_path / "out"

    def fake_translate_directory(
        source_root: Path,
        output_root: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
        workers: int | None = None,
        llm_concurrency: int | None = None,
        incremental: bool = False,
    ) -> pipeline.DirectoryTranslationResult:
        result = pipeline.TranslationResult(
            source_path=source_root / "Sample.java",
            python_source="class Sample:\n    pass\n",
            used_llm=True,
            output_path=output_root / "Sample.py",
            structural_verification=StructuralVerificationResult(
                errors=["Missing method in class Sample: run"],
            ),
        )
        return pipeline.DirectoryTranslationResult(
            source_root=source_root,
            output_root=output_root,
            files=[result],
            order=[source_root / "Sample.java"],
            warnings=[],
        )

    monkeypatch.setattr(pipeline, "translate_directory", fake_translate_directory)
    runner = CliRunner()

    result = runner.invoke(app, ["translate", str(source), "--output", str(output)])

    assert result.exit_code == 1
    assert "Translation verification failures:" in result.output
    assert "Structural verification issues:" in result.output
    assert "Missing method in class Sample: run" in result.output


def test_cli_translate_emits_vendored_dispatch_runtime(tmp_path: Path) -> None:
    """Files using @overloaded dispatch get j2py_runtime.py written next to them."""
    source = tmp_path / "Over.java"
    source.write_text(
        """
        class Foo {}
        class Bar {}

        public class Over {
            public int get(Foo value) { return 1; }
            public int get(Bar value) { return 2; }
        }
        """,
    )
    output = tmp_path / "Over.py"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "from j2py_runtime import overloaded" in output.read_text()
    runtime = tmp_path / "j2py_runtime.py"
    assert runtime.exists()
    assert "class overloaded" in runtime.read_text()


def test_cli_translate_emits_vendored_integer_division_runtime(tmp_path: Path) -> None:
    """Files using truncating integer division get j2py_runtime.py written next to them."""
    source = tmp_path / "Div.java"
    source.write_text(
        """
        public class Div {
            public int run() {
                int value = -20;
                value /= 6;
                return value;
            }
        }
        """,
    )
    output = tmp_path / "Div.py"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "from j2py_runtime import _j2py_idiv" in output.read_text()
    runtime = tmp_path / "j2py_runtime.py"
    assert runtime.exists()
    assert "def _j2py_idiv" in runtime.read_text()


def test_cli_translate_reports_parse_errors(tmp_path: Path) -> None:
    source = tmp_path / "Broken.java"
    source.write_text("public class Broken { void foo( { }")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "parse_ok=False" in result.output
    assert "Java parse errors detected" in result.output


def test_cli_translate_skips_runtime_module_when_dispatch_unused(tmp_path: Path) -> None:
    source = tmp_path / "Plain.java"
    source.write_text("public class Plain {}")
    output = tmp_path / "Plain.py"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert not (tmp_path / "j2py_runtime.py").exists()


def test_cli_translate_writes_self_contained_review_report(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text(
        """
        public class Sample {
            public String greet() { return "hello"; }
        }
        """,
    )
    output = tmp_path / "Sample.py"
    report = tmp_path / "report.html"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--no-llm",
            "--no-validate",
            "--output",
            str(output),
            "--report",
            str(report),
        ],
    )

    assert result.exit_code == 0
    html = report.read_text()
    assert "Sample.java" in html
    assert "Java" in html
    assert "Python" in html
    assert 'data-provenance="rule"' in html
    assert "No unresolved rule-layer diagnostics." in html
    assert "https://" not in html
    assert "<script" not in html


def test_cli_translate_writes_dashboard_and_state(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Sample.java").write_text(
        """
        package com.example;
        public class Sample {
            public String greet() { return "hello"; }
        }
        """,
    )
    output = tmp_path / "out"
    dashboard = tmp_path / "dashboard.html"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--no-llm",
            "--no-validate",
            "--output",
            str(output),
            "--dashboard",
            str(dashboard),
        ],
    )

    assert result.exit_code == 0
    assert (output / ".j2py-state.json").exists()
    html = dashboard.read_text()
    assert "Confidence Heatmap" in html
    assert "Sample.java" in html
    assert "https://" not in html


def test_cli_translate_json_output_is_machine_readable(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--no-llm",
            "--no-validate",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"confidence": 1.0' in result.output
    assert '"todos": []' in result.output
    assert "Translating" not in result.output


def test_cli_translate_surfaces_clamped_confidence_consistently(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    # int / int is currently translated with a semantic warning because Java truncates
    # toward zero while Python floor division differs for negative values.
    (source / "Division.java").write_text(
        """
        package com.example;
        public class Division {
            public int half(int value) {
                return value / 2;
            }
        }
        """,
    )
    output = tmp_path / "out"
    dashboard = tmp_path / "dashboard.html"
    report = tmp_path / "report.html"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--no-llm",
            "--no-validate",
            "--output",
            str(output),
            "--dashboard",
            str(dashboard),
            "--report",
            str(report),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    translated = payload["files"][0]
    assert translated["confidence"] == pipeline.SEMANTIC_WARNING_CONFIDENCE_CAP
    assert translated["semantic_warnings"]

    expected_percent = f"{pipeline.SEMANTIC_WARNING_CONFIDENCE_CAP:.0%}"
    state = json.loads((output / ".j2py-state.json").read_text())
    assert state["files"]["Division.java"]["confidence"] == pipeline.SEMANTIC_WARNING_CONFIDENCE_CAP
    assert f'"confidence": {pipeline.SEMANTIC_WARNING_CONFIDENCE_CAP}' in dashboard.read_text()
    assert expected_percent in report.read_text()


def test_cli_translate_json_clamps_confidence_for_validation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Broken.java"
    source.write_text("public class Broken {}")

    def fake_validate_source(source_text: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            ruff_ok=False,
            mypy_ok=True,
            ruff_errors=["Broken.py:1:1: simulated ruff failure"],
        )

    monkeypatch.setattr(pipeline, "validate_source", fake_validate_source)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--no-llm",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["confidence"] == pipeline.REVIEW_REQUIRED_CONFIDENCE_CAP
    assert payload["validation"]["ok"] is False


def test_cli_translate_incremental_reports_skipped_files(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Sample.java").write_text("package com.example; public class Sample {}")
    output = tmp_path / "out"
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--output", str(output)],
    )
    assert first.exit_code == 0

    second = runner.invoke(
        app,
        [
            "translate",
            str(source),
            "--no-llm",
            "--no-validate",
            "--output",
            str(output),
            "--incremental",
        ],
    )

    assert second.exit_code == 0
    assert "1 files skipped, 0 re-translated" in second.output


def test_cli_dashboard_regenerates_from_state(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Sample.java").write_text("package com.example; public class Sample {}")
    output = tmp_path / "out"
    runner = CliRunner()

    translated = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--output", str(output)],
    )
    assert translated.exit_code == 0

    dashboard = tmp_path / "regenerated.html"
    result = runner.invoke(app, ["dashboard", str(output), "--output", str(dashboard)])

    assert result.exit_code == 0
    assert "Sample.java" in dashboard.read_text()


def test_cli_doctor_writes_json_and_html_assessment(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Sample.java").write_text("package com.example; public class Sample {}")
    json_path = tmp_path / "assessment.json"
    html_path = tmp_path / "assessment.html"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "doctor",
            str(source),
            "--json",
            str(json_path),
            "--html",
            str(html_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(json_path.read_text())
    assert payload["schema_version"] == 1
    assert payload["summary"]["files"] == 1
    assert payload["files"][0]["classes"][0]["name"] == "Sample"
    assert "Doctor assessment" in result.output
    assert "j2py doctor assessment" in html_path.read_text()


def test_cli_doctor_writes_config_suggestions(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Controller.java").write_text(
        """
        import org.springframework.web.bind.annotation.RestController;
        import com.external.PaymentClient;

        @RestController
        public class Controller {
            private PaymentClient client;
        }
        """,
    )
    suggestions_path = tmp_path / "j2py.suggested.yaml"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "doctor",
            str(source),
            "--config-suggestions",
            str(suggestions_path),
        ],
    )

    assert result.exit_code == 0
    suggestions = suggestions_path.read_text()
    assert "config_suggestions:" in suggestions
    assert 'java_import: "com.external.PaymentClient"' in suggestions
    assert "Config suggestions" in result.output


def test_cli_doctor_diff_compares_assessments(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    diff_json = tmp_path / "diff.json"
    before.write_text(
        json.dumps(
            {
                "source": "before-src",
                "summary": {
                    "files": 1,
                    "average_rule_coverage": 0.5,
                    "unresolved_imports": 1,
                },
                "unresolved_imports": [
                    {
                        "import": "com.external.PaymentClient",
                        "category": "external-import",
                        "reason": "missing",
                    }
                ],
                "files": [
                    {
                        "path": "Controller.java",
                        "parse_ok": True,
                        "unresolved_imports": [{"import": "com.external.PaymentClient"}],
                        "translation": {
                            "rule_coverage": 0.5,
                            "semantic_warnings": [],
                            "unhandled": [],
                        },
                    }
                ],
            }
        )
    )
    after.write_text(
        json.dumps(
            {
                "source": "after-src",
                "summary": {
                    "files": 1,
                    "average_rule_coverage": 0.75,
                    "unresolved_imports": 0,
                },
                "unresolved_imports": [],
                "files": [
                    {
                        "path": "Controller.java",
                        "parse_ok": True,
                        "unresolved_imports": [],
                        "translation": {
                            "rule_coverage": 0.75,
                            "semantic_warnings": [],
                            "unhandled": [],
                        },
                    }
                ],
            }
        )
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["doctor", "diff", str(before), str(after), "--json", str(diff_json)],
    )

    assert result.exit_code == 0
    assert "Unresolved imports: 1 removed, 0 added" in result.output
    payload = json.loads(diff_json.read_text())
    assert payload["summary_delta"]["unresolved_imports"] == -1


def test_cli_doctor_diff_without_operands_reports_usage() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["doctor", "diff"])

    assert result.exit_code == 2
    assert "usage: j2py doctor diff BEFORE_JSON AFTER_JSON" in result.output
    assert "source path not found" not in result.output


def test_cli_doctor_reports_missing_source_without_traceback(tmp_path: Path) -> None:
    source = tmp_path / "missing"
    json_path = tmp_path / "assessment.json"
    runner = CliRunner()

    result = runner.invoke(app, ["doctor", str(source), "--json", str(json_path)])

    assert result.exit_code == 1
    assert "source path not found" in result.output
    assert "Traceback" not in result.output
    assert not json_path.exists()


def test_cli_sarif_writes_report_from_doctor_assessment(tmp_path: Path) -> None:
    assessment = tmp_path / "assessment.json"
    output = tmp_path / "j2py.sarif"
    assessment.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "src",
                "files": [
                    {
                        "path": "Sample.java",
                        "parse_ok": True,
                        "parse_errors": [],
                        "unresolved_imports": [
                            {
                                "import": "com.external.PaymentClient",
                                "category": "external-import",
                                "reason": "not covered by defaults",
                            }
                        ],
                        "translation": {
                            "semantic_warnings": [],
                            "unhandled": [],
                            "todos": [],
                            "validation": None,
                        },
                    }
                ],
            }
        )
    )
    runner = CliRunner()

    result = runner.invoke(app, ["sarif", str(assessment), "--output", str(output)])

    assert result.exit_code == 0
    assert "SARIF:" in result.output
    payload = json.loads(output.read_text())
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["results"][0]["ruleId"] == "j2py.unresolved-import"


def test_cli_compare_existing_python_skips_translation_and_opens_diff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text("public class Sample {}")
    python.write_text("class Sample:\n    pass\n")
    calls: list[list[str]] = []

    def fake_popen(args: list[str]) -> None:
        calls.append(args)

    monkeypatch.setattr("j2py.cli.main.subprocess.Popen", fake_popen)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java)])

    assert result.exit_code == 0
    assert "Skipping translation" in result.output
    assert calls == [["code", "--diff", str(java), str(python)]]


def test_cli_compare_missing_python_translates_without_llm_and_opens_diff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text(
        """
        public class Sample {
            public String greet() {
                return "hello";
            }
        }
        """,
    )
    calls: list[list[str]] = []

    def fake_popen(args: list[str]) -> None:
        calls.append(args)

    monkeypatch.setattr("j2py.cli.main.subprocess.Popen", fake_popen)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--no-validate"])

    assert result.exit_code == 0
    assert python.exists()
    assert "Translating" in result.output
    assert calls == [["code", "--diff", str(java), str(python)]]


def test_cli_compare_auto_discovery_ignores_python_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text("public class Sample {}")
    (tmp_path / "j2py_config.py").write_text(
        "raise RuntimeError('auto-discovered Python config executed')\n",
    )
    observed_target_python: list[str] = []

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        observed_target_python.append(cfg.target_python)
        return pipeline.TranslationResult(
            source_path=path,
            python_source="class Sample:\n    pass\n",
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--no-open", "--no-validate"])

    assert result.exit_code == 0
    assert python.exists()
    assert observed_target_python == ["3.11"]


def test_cli_compare_no_open_prints_paths_without_opening_editor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text("public class Sample {}")
    python.write_text("class Sample:\n    pass\n")
    calls: list[list[str]] = []

    def fake_popen(args: list[str]) -> None:
        calls.append(args)

    monkeypatch.setattr("j2py.cli.main.subprocess.Popen", fake_popen)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--no-open"])

    assert result.exit_code == 0
    assert f"Java:   {java}" in result.output
    assert f"Python: {python}" in result.output
    assert calls == []


def test_cli_compare_editor_not_found_prints_manual_diff_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text("public class Sample {}")
    python.write_text("class Sample:\n    pass\n")

    def fake_popen(args: list[str]) -> None:
        raise FileNotFoundError

    monkeypatch.setattr("j2py.cli.main.subprocess.Popen", fake_popen)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--editor", "missing-code"])

    assert result.exit_code == 0
    assert "not found" in result.output
    assert "--diff" in result.output


def test_cli_compare_missing_source_exits_without_traceback(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(tmp_path / "Missing.java"), "--no-open"])

    assert result.exit_code == 1
    assert "source file not found" in result.output
    assert "Traceback" not in result.output


def test_cli_compare_rejects_output_directory(tmp_path: Path) -> None:
    java = tmp_path / "Sample.java"
    java.write_text("public class Sample {}")
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--output", str(tmp_path), "--no-open"])

    assert result.exit_code == 1
    assert "Python output path is a directory" in result.output


def test_cli_compare_editor_launch_os_error_prints_manual_diff_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text("public class Sample {}")
    python.write_text("class Sample:\n    pass\n")

    def fake_popen(args: list[str]) -> None:
        raise PermissionError("permission denied")

    monkeypatch.setattr("j2py.cli.main.subprocess.Popen", fake_popen)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--editor", "blocked-code"])

    assert result.exit_code == 0
    assert "could not be launched" in result.output
    assert "permission denied" in result.output
    assert "--diff" in result.output


def test_cli_compare_generic_editor_omits_vscode_diff_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text("public class Sample {}")
    python.write_text("class Sample:\n    pass\n")
    calls: list[list[str]] = []

    def fake_popen(args: list[str]) -> None:
        calls.append(args)

    monkeypatch.setattr("j2py.cli.main.subprocess.Popen", fake_popen)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--editor", "vimdiff"])

    assert result.exit_code == 0
    assert calls == [["vimdiff", str(java), str(python)]]


def test_cli_watch_auto_discovery_ignores_python_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    output = tmp_path / "Sample.py"
    source.write_text("public class Sample {}")
    (tmp_path / "j2py_config.py").write_text(
        "raise RuntimeError('auto-discovered Python config executed')\n",
    )
    observed_target_python: list[str] = []

    def fake_run_watch_translation(
        source: Path,
        output: Path,
        cfg,
        llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> None:
        observed_target_python.append(cfg.target_python)

    def stop_after_first_poll(interval: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("j2py.cli.main._run_watch_translation", fake_run_watch_translation)
    monkeypatch.setattr("j2py.cli.main.time.sleep", stop_after_first_poll)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "watch",
            str(source),
            "--output",
            str(output),
            "--no-llm",
            "--no-validate",
            "--poll-interval",
            "0.1",
        ],
    )

    assert result.exit_code == 0
    assert observed_target_python == ["3.11"]


def test_cli_watch_uses_configured_llm_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    output = tmp_path / "Sample.py"
    source.write_text("public class Sample {}")
    (tmp_path / "j2py.toml").write_text(
        """
llm_provider = "gemini"
model = "gemini-3.5-flash"
""",
    )
    observed: list[tuple[str | None, str]] = []

    def fake_run_watch_translation(
        source: Path,
        output: Path,
        cfg,
        llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> None:
        observed.append((model, llm_provider))

    def stop_after_first_poll(interval: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("j2py.cli.main._run_watch_translation", fake_run_watch_translation)
    monkeypatch.setattr("j2py.cli.main.time.sleep", stop_after_first_poll)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "watch",
            str(source),
            "--output",
            str(output),
            "--no-validate",
            "--poll-interval",
            "0.1",
        ],
    )

    assert result.exit_code == 0
    assert observed == [("gemini-3.5-flash", "gemini")]


def test_cli_compare_uses_config_when_translating_missing_python(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    config = tmp_path / "j2py_config.py"
    java.write_text("public class Sample {}")
    config.write_text(
        "\n".join(
            [
                "type_map = {'String': 'Text'}",
                "llm_provider = 'gemini'",
                "model = 'gemini-3.5-flash'",
            ],
        ),
    )
    observed_string_types: list[str] = []
    observed_validate: list[bool] = []
    observed_llm: list[tuple[str | None, str]] = []

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        observed_string_types.append(cfg.type_map["String"])
        observed_validate.append(validate)
        observed_llm.append((model, llm_provider))
        return pipeline.TranslationResult(
            source_path=path,
            python_source="class Sample:\n    pass\n",
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["compare", str(java), "--config", str(config), "--no-open"],
    )

    assert result.exit_code == 0
    assert python.exists()
    assert observed_string_types == ["Text"]
    assert observed_validate == [True]
    assert observed_llm == [("gemini-3.5-flash", "gemini")]


def test_cli_compare_writes_wiring_metadata_sidecar_when_configured(
    tmp_path: Path,
) -> None:
    java = tmp_path / "Orders.java"
    python = tmp_path / "Orders.py"
    config = tmp_path / "j2py_config.py"
    java.write_text(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
    )
    config.write_text(
        "\n".join(
            [
                "from tests.fixtures.framework.reference_plugin import (",
                "    ReferenceFrameworkPlugin as _ReferenceFrameworkPlugin,",
                ")",
                "framework_plugins = [_ReferenceFrameworkPlugin()]",
                "emit_wiring_metadata = True",
            ],
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["compare", str(java), "--config", str(config), "--no-open", "--no-validate"],
    )

    assert result.exit_code == 0
    assert python.exists()
    sidecar = python.with_suffix(".wiring.json")
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text())
    assert payload["source"] == str(java)
    assert payload["output"] == str(python)
    assert payload["elements"][0]["metadata"] == {"controller": "Orders"}


def test_cli_compare_emits_vendored_dispatch_runtime_for_generated_python(
    tmp_path: Path,
    monkeypatch,
) -> None:
    java = tmp_path / "Sample.java"
    python = tmp_path / "Sample.py"
    java.write_text("public class Sample {}")

    def fake_translate_file(
        path: Path,
        *,
        cfg,
        use_llm: bool,
        model: str | None,
        llm_provider: str,
        validate: bool,
    ) -> pipeline.TranslationResult:
        return pipeline.TranslationResult(
            source_path=path,
            python_source="from j2py_runtime import overloaded\n\nclass Sample:\n    pass\n",
        )

    monkeypatch.setattr(pipeline, "translate_file", fake_translate_file)
    runner = CliRunner()

    result = runner.invoke(app, ["compare", str(java), "--no-open"])

    assert result.exit_code == 0
    assert "from j2py_runtime import overloaded" in python.read_text()
    runtime = tmp_path / "j2py_runtime.py"
    assert runtime.exists()
    assert "class overloaded" in runtime.read_text()

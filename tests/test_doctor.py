"""Tests for the j2py doctor assessment command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from j2py.config.loader import ConfigLoader
from j2py.doctor import (
    DOCTOR_GATE_PROFILES,
    DOCTOR_GATE_SCHEMA_VERSION,
    DOCTOR_SCHEMA_VERSION,
    DoctorAssessment,
    DoctorDiff,
    DoctorGateResult,
    DoctorGateThresholds,
    assess_project,
    diff_assessments,
    doctor_gate_thresholds_for_profile,
    evaluate_doctor_gate,
    load_assessment_json,
    render_assessment_html,
    render_config_suggestions,
    render_doctor_diff_text,
    render_doctor_gate_text,
    write_assessment_html,
    write_assessment_json,
    write_config_suggestions,
    write_doctor_diff_json,
    write_doctor_gate_json,
)
from j2py.doctor_assessment import _file_risk_profile
from j2py.doctor_readiness import migration_readiness_profile

CFG = ConfigLoader().add_defaults().build()


def _minimal_doctor_file_payload(
    path: str,
    *,
    parse_ok: bool = True,
    rule_coverage: float = 1.0,
    semantic_warning_count: int = 0,
    unhandled_count: int = 0,
    unresolved_import_count: int = 0,
    risk_score: float = 0.0,
    readiness_bucket: str = "ready",
) -> dict[str, Any]:
    return {
        "path": path,
        "parse_ok": parse_ok,
        "translation": {
            "rule_coverage": rule_coverage,
            "semantic_warnings": [_synthetic_diagnostic() for _ in range(semantic_warning_count)],
            "unhandled": [_synthetic_diagnostic() for _ in range(unhandled_count)],
        },
        "unresolved_imports": [{}] * unresolved_import_count,
        "risk_score": risk_score,
        "readiness_bucket": readiness_bucket,
    }


def _synthetic_diagnostic() -> dict[str, Any]:
    return {"line": None, "node_type": "", "reason": "", "text": ""}


def test_doctor_public_facade_exports_stable_api() -> None:
    assert DOCTOR_SCHEMA_VERSION == 2
    assert DOCTOR_GATE_SCHEMA_VERSION == 1
    assert DOCTOR_GATE_PROFILES == ("strict", "one-zero", "migration-trial", "advisory")
    assert DoctorAssessment({"schema_version": DOCTOR_SCHEMA_VERSION}).to_json()
    assert DoctorDiff({"schema_version": DOCTOR_SCHEMA_VERSION}).to_json()
    assert DoctorGateResult({"schema_version": DOCTOR_GATE_SCHEMA_VERSION}).to_json()
    assert callable(assess_project)
    assert callable(diff_assessments)
    assert callable(doctor_gate_thresholds_for_profile)
    assert callable(evaluate_doctor_gate)
    assert callable(load_assessment_json)
    assert callable(render_assessment_html)
    assert callable(render_config_suggestions)
    assert callable(render_doctor_gate_text)
    assert callable(render_doctor_diff_text)
    assert callable(write_assessment_html)
    assert callable(write_assessment_json)
    assert callable(write_config_suggestions)
    assert callable(write_doctor_diff_json)
    assert callable(write_doctor_gate_json)


def test_doctor_assessment_reports_core_migration_signals(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
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
    (source / "Controller.java").write_text(
        """
        package com.example;
        import org.springframework.web.bind.annotation.RestController;
        import com.external.PaymentClient;

        @RestController
        public class Controller {
            private PaymentClient client;
        }
        """,
    )
    (source / "Broken.java").write_text("public class Broken { public void broken( }")
    (source / "Ready.java").write_text("package com.example; public class Ready {}")

    payload = assess_project(source, cfg=CFG).payload

    assert payload["schema_version"] == DOCTOR_SCHEMA_VERSION
    assert payload["summary"]["files"] == 4
    assert payload["summary"]["parse_failures"] == 1
    assert payload["summary"]["semantic_warnings"] >= 1
    assert payload["summary"]["unresolved_imports"] == 2
    assert payload["summary"]["average_risk_score"] >= 0.0
    assert payload["summary"]["max_risk_score"] >= payload["summary"]["min_risk_score"]
    readiness = {
        item["bucket"]: item["files"] for item in payload["summary"]["readiness_distribution"]
    }
    assert readiness["not_ready"] == 1
    assert readiness["ready"] >= 1
    assert readiness["requires_manual_fixes"] >= 0
    migration_readiness = {
        item["bucket"]: item["files"]
        for item in payload["summary"]["migration_readiness_distribution"]
    }
    assert migration_readiness["parse_blocked"] == 1
    assert migration_readiness["framework_boundary"] == 1
    assert migration_readiness["ready_to_translate"] >= 1
    assert all("migration_readiness" in item for item in payload["files"])
    assert [item["path"] for item in payload["summary"]["top_risk_files"]][:1] == ["Broken.java"]
    assert [item["name"] for item in payload["annotation_inventory"]] == ["RestController"]

    controller = next(item for item in payload["files"] if item["path"] == "Controller.java")
    assert controller["classes"][0]["name"] == "Controller"
    assert controller["annotations"][0]["full_name"] == (
        "org.springframework.web.bind.annotation.RestController"
    )
    assert {item["import"] for item in controller["unresolved_imports"]} == {
        "com.external.PaymentClient",
        "org.springframework.web.bind.annotation.RestController",
    }

    broken = next(item for item in payload["files"] if item["path"] == "Broken.java")
    assert broken["parse_ok"] is False
    assert broken["parse_errors"]
    assert broken["risk_score"] >= 80.0
    assert broken["risk_band"] == "critical"
    assert broken["readiness_bucket"] == "not_ready"
    assert broken["migration_readiness"]["bucket"] == "parse_blocked"
    assert broken["migration_readiness"]["next_action"]
    assert {reason["reason"] for reason in broken["risk_reasons"]} == {"parse_errors"}

    assert controller["migration_readiness"]["bucket"] == "framework_boundary"
    assert controller["migration_readiness"]["next_action"].startswith("Decide target-stack")

    suggestions = payload["config_suggestions"]
    assert {item["annotation"] for item in suggestions["annotation_map"]} == {"RestController"}
    assert payload["hotspots"]["unresolved_import_packages"][0] == {
        "package": "com.external",
        "count": 1,
    }
    assert payload["hotspots"]["lowest_coverage_files"][0]["path"] == "Broken.java"
    assert {item["reason"] for item in payload["hotspots"]["risk_reasons"]} >= {
        "parse_errors",
    }
    assert "j2py translate" in payload["recommended_next_commands"][0]


def test_doctor_assessment_reports_method_level_signals(tmp_path: Path) -> None:
    source = tmp_path / "MethodSignals.java"
    source.write_text(
        """
        public class MethodSignals {
            public int safe(int value) {
                return value + 1;
            }

            public int risky(int value) {
                // TODO: verify Java truncating division semantics.
                return value / 2;
            }

            private int internal(int value) {
                return value + 2;
            }
        }
        """,
    )

    assessment = assess_project(source, cfg=CFG)
    payload = assessment.payload
    file_payload = payload["files"][0]
    cls = file_payload["classes"][0]
    methods = {method["name"]: method for method in cls["methods"]}

    assert payload["summary"]["methods"] == 3
    assert payload["summary"]["risky_methods"] == 1
    assert payload["summary"]["equivalence_candidate_methods"] == 2
    assert cls["qualified_name"] == "MethodSignals"
    assert cls["end_line"] >= cls["line"]
    assert cls["range_source"] == "tree_sitter_node_range"
    assert cls["diagnostics"]["semantic_warnings"] >= 1

    safe = methods["safe"]
    assert safe["signature"] == "MethodSignals.safe(int)"
    assert safe["public"] is True
    assert safe["visibility"] == "public"
    assert safe["equivalence_candidate"] is True
    assert safe["readiness_bucket"] == "ready_to_translate"
    assert safe["diagnostics"]["semantic_warnings"] == 0
    assert safe["diagnostic_mapping_source"] == "source_line_containment"

    risky = methods["risky"]
    assert risky["signature"] == "MethodSignals.risky(int)"
    assert risky["diagnostics"]["semantic_warnings"] >= 1
    assert risky["diagnostics"]["todos"] == 1
    assert risky["readiness_bucket"] == "manual_port"
    assert risky["risk_score"] > 0.0
    assert risky["equivalence_candidate"] is True
    assert {
        reason["detail"]
        for reason in risky["migration_readiness"]["reasons"]
        if reason["reason"] == "todo_markers"
    } == {"Java source contains TODO/FIXME markers in this scope"}

    internal = methods["internal"]
    assert internal["public"] is False
    assert internal["visibility"] == "private"
    assert internal["equivalence_candidate"] is False

    high_risk_methods = payload["hotspots"]["highest_risk_methods"]
    assert high_risk_methods == [
        {
            "path": "MethodSignals.java",
            "class": "MethodSignals",
            "method": "risky",
            "signature": "MethodSignals.risky(int)",
            "line": risky["line"],
            "risk_score": risky["risk_score"],
            "risk_band": risky["risk_band"],
            "readiness_bucket": "manual_port",
            "semantic_warnings": risky["diagnostics"]["semantic_warnings"],
            "unhandled": 0,
            "todos": 1,
            "equivalence_candidate": True,
        }
    ]
    html = render_assessment_html(assessment)
    assert "High-Risk Methods" in html
    assert "MethodSignals.risky(int)" in html


def test_doctor_method_visibility_does_not_leak_from_enclosing_interface(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Contract.java"
    source.write_text(
        """
        public interface Contract {
            class Nested {
                int packagePrivate() {
                    return 1;
                }

                public int visible() {
                    return 2;
                }
            }
        }
        """,
    )

    payload = assess_project(source, cfg=CFG).payload
    nested = payload["files"][0]["classes"][0]["inner_classes"][0]
    methods = {method["name"]: method for method in nested["methods"]}

    assert methods["packagePrivate"]["visibility"] == "package_private"
    assert methods["packagePrivate"]["public"] is False
    assert methods["packagePrivate"]["equivalence_candidate"] is False
    assert methods["visible"]["visibility"] == "public"
    assert methods["visible"]["equivalence_candidate"] is True


def test_doctor_assessment_reports_maven_project_structure(tmp_path: Path) -> None:
    project = tmp_path / "orders"
    main_root = project / "src" / "main" / "java" / "com" / "example"
    test_root = project / "src" / "test" / "java" / "com" / "example"
    generated_root = project / "target" / "generated-sources" / "annotations"
    main_root.mkdir(parents=True)
    test_root.mkdir(parents=True)
    generated_root.mkdir(parents=True)
    (project / "pom.xml").write_text(
        """
        <project>
          <properties>
            <maven.compiler.release>17</maven.compiler.release>
          </properties>
        </project>
        """,
    )
    (main_root / "Orders.java").write_text("package com.example; public class Orders {}")
    (test_root / "OrdersTest.java").write_text("package com.example; public class OrdersTest {}")

    payload = assess_project(project, cfg=CFG).payload
    structure = payload["project_structure"]

    assert structure["root"] == "."
    assert structure["build_systems"] == ["maven"]
    assert structure["java_language_level"] == "17"
    assert structure["modules"] == [
        {
            "name": "orders",
            "path": ".",
            "build_systems": ["maven"],
            "build_files": ["pom.xml"],
            "source_roots": ["src/main/java"],
            "test_roots": ["src/test/java"],
            "generated_source_roots": ["target/generated-sources"],
            "java_language_level": "17",
        }
    ]
    orders = next(item for item in payload["files"] if item["path"].endswith("Orders.java"))
    assert orders["project_structure"] == {
        "module": "orders",
        "module_path": ".",
        "source_root": "src/main/java",
        "source_set": "main",
    }
    test_file = next(item for item in payload["files"] if item["path"].endswith("OrdersTest.java"))
    assert test_file["project_structure"]["source_root"] == "src/test/java"
    assert test_file["project_structure"]["source_set"] == "test"


def test_doctor_assessment_reports_maven_multi_module_structure(tmp_path: Path) -> None:
    root = tmp_path / "platform"
    api_root = root / "api" / "src" / "main" / "java"
    worker_root = root / "worker" / "src" / "main" / "java"
    api_root.mkdir(parents=True)
    worker_root.mkdir(parents=True)
    (root / "pom.xml").write_text(
        """
        <project>
          <modules>
            <module>api</module>
            <module>worker</module>
          </modules>
        </project>
        """,
    )
    (root / "api" / "pom.xml").write_text(
        """
        <project>
          <build>
            <plugins>
              <plugin>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration><source>11</source></configuration>
              </plugin>
            </plugins>
          </build>
        </project>
        """,
    )
    (root / "worker" / "pom.xml").write_text("<project />")
    (api_root / "Api.java").write_text("public class Api {}")
    (worker_root / "Worker.java").write_text("public class Worker {}")

    structure = assess_project(root, cfg=CFG).payload["project_structure"]
    modules = {module["path"]: module for module in structure["modules"]}

    assert structure["build_systems"] == ["maven"]
    assert structure["java_language_level"] == "11"
    assert set(modules) == {".", "api", "worker"}
    assert modules["."]["source_roots"] == []
    assert modules["api"]["source_roots"] == ["api/src/main/java"]
    assert modules["api"]["java_language_level"] == "11"
    assert modules["worker"]["build_files"] == ["worker/pom.xml"]


def test_doctor_assessment_reports_gradle_multi_module_structure(tmp_path: Path) -> None:
    root = tmp_path / "gradle-project"
    app_root = root / "app" / "src" / "main" / "java"
    lib_root = root / "lib" / "src" / "test" / "java"
    app_root.mkdir(parents=True)
    lib_root.mkdir(parents=True)
    (root / "settings.gradle").write_text("include 'app', ':lib'\n")
    (root / "build.gradle").write_text("sourceCompatibility = '21'\n")
    (root / "app" / "build.gradle").write_text("plugins { id 'java' }\n")
    (root / "lib" / "build.gradle.kts").write_text("plugins { java }\n")
    (app_root / "App.java").write_text("public class App {}")
    (lib_root / "LibTest.java").write_text("public class LibTest {}")

    payload = assess_project(root, cfg=CFG).payload
    structure = payload["project_structure"]
    modules = {module["path"]: module for module in structure["modules"]}

    assert structure["build_systems"] == ["gradle"]
    assert structure["java_language_level"] == "21"
    assert set(modules) == {".", "app", "lib"}
    assert modules["."]["source_roots"] == []
    assert modules["app"]["source_roots"] == ["app/src/main/java"]
    assert modules["lib"]["test_roots"] == ["lib/src/test/java"]
    app_file = next(item for item in payload["files"] if item["path"].endswith("App.java"))
    assert app_file["project_structure"]["module"] == "app"
    assert app_file["project_structure"]["source_set"] == "main"


def test_doctor_assessment_reports_source_only_project_structure(tmp_path: Path) -> None:
    source = tmp_path / "src"
    package_dir = source / "com" / "example"
    package_dir.mkdir(parents=True)
    (package_dir / "Sample.java").write_text("package com.example; public class Sample {}")

    payload = assess_project(source, cfg=CFG).payload
    structure = payload["project_structure"]

    assert structure["root"] == "."
    assert structure["build_systems"] == []
    assert structure["java_language_level"] is None
    assert structure["modules"][0]["build_files"] == []
    assert structure["modules"][0]["source_roots"] == ["."]
    assert payload["files"][0]["project_structure"]["source_root"] == "."


def test_migration_readiness_profile_buckets_are_deterministic() -> None:
    ready = migration_readiness_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=1.0,
        semantic_warnings=[],
        unhandled=[],
        todo_count=0,
        unresolved_imports=[],
        annotations=[],
        validation=None,
    )
    assert ready["bucket"] == "ready_to_translate"
    assert ready["risk_score"] == 0.0

    parse_blocked = migration_readiness_profile(
        parse_ok=False,
        parse_error_count=2,
        rule_coverage=1.0,
        semantic_warnings=[],
        unhandled=[],
        todo_count=0,
        unresolved_imports=[],
        annotations=[],
        validation=None,
    )
    assert parse_blocked["bucket"] == "parse_blocked"
    assert parse_blocked["risk_score"] == 100.0

    needs_rule_work = migration_readiness_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=0.5,
        semantic_warnings=[],
        unhandled=[{"reason": "unsupported"}],
        todo_count=0,
        unresolved_imports=[],
        annotations=[],
        validation={"ok": False, "errors": ["syntax"]},
    )
    assert needs_rule_work["bucket"] == "needs_rule_work"
    assert {reason["reason"] for reason in needs_rule_work["reasons"]} >= {
        "low_rule_coverage",
        "unhandled_nodes",
        "validation_failures",
    }

    framework_boundary = migration_readiness_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=1.0,
        semantic_warnings=[],
        unhandled=[],
        todo_count=0,
        unresolved_imports=[
            {"import": "org.springframework.stereotype.Service", "category": "framework-boundary"}
        ],
        annotations=[{"framework_candidate": True}],
        validation=None,
    )
    assert framework_boundary["bucket"] == "framework_boundary"

    needs_config = migration_readiness_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=1.0,
        semantic_warnings=[],
        unhandled=[],
        todo_count=0,
        unresolved_imports=[
            {"import": "com.external.PaymentClient", "category": "external-import"}
        ],
        annotations=[],
        validation=None,
    )
    assert needs_config["bucket"] == "needs_config"

    manual_port = migration_readiness_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=1.0,
        semantic_warnings=[{"reason": "verify"}],
        unhandled=[],
        todo_count=1,
        unresolved_imports=[],
        annotations=[],
        validation=None,
    )
    assert manual_port["bucket"] == "manual_port"


def test_doctor_gate_profiles_are_deterministic() -> None:
    strict = doctor_gate_thresholds_for_profile("strict")
    one_zero = doctor_gate_thresholds_for_profile("one-zero")
    migration_trial = doctor_gate_thresholds_for_profile("migration-trial")
    advisory = doctor_gate_thresholds_for_profile("advisory")

    assert strict.min_average_coverage == 1.0
    assert strict.max_semantic_warnings == 0
    assert one_zero.max_unhandled_diagnostics == 0
    assert one_zero.max_needs_config_files is None
    assert migration_trial.min_average_coverage == 0.80
    assert migration_trial.max_semantic_warnings is None
    assert advisory.max_parse_failures is None

    with pytest.raises(ValueError, match="unsupported doctor gate profile"):
        doctor_gate_thresholds_for_profile("unknown")


def test_doctor_gate_evaluator_reports_exact_failures(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Ready.java").write_text("public class Ready {}")
    (source / "Risky.java").write_text(
        """
        public class Risky {
            public int half(int value) {
                // TODO: verify truncation
                return value / 2;
            }
        }
        """,
    )

    assessment = assess_project(source, cfg=CFG)
    result = evaluate_doctor_gate(
        assessment,
        profile="strict",
        thresholds=DoctorGateThresholds(
            max_parse_failures=0,
            min_average_coverage=1.0,
            min_file_coverage=1.0,
            max_files_below_coverage=0,
            max_semantic_warnings=0,
            max_validation_failures=0,
            max_manual_port_files=0,
        ),
    )
    payload = result.payload

    assert payload["schema_version"] == DOCTOR_GATE_SCHEMA_VERSION
    assert payload["profile"] == "strict"
    assert payload["passed"] is False
    failures = {item["check"]: item for item in payload["failures"]}
    assert failures["semantic_warnings"]["actual"] >= 1
    assert failures["manual_port_files"]["actual"] == 1
    assert "validation_not_included" in {item["caveat"] for item in payload["caveats"]}
    text = render_doctor_gate_text(result)
    assert "Doctor gate failed: profile=strict" in text
    assert "semantic_warnings" in text


def test_doctor_gate_evaluator_reports_sample_caveat(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    assessment = assess_project(source, cfg=CFG, sample_limit=1)

    result = evaluate_doctor_gate(
        assessment,
        profile="one-zero",
        thresholds=doctor_gate_thresholds_for_profile("one-zero"),
        sample_limit=1,
    )

    assert result.payload["passed"] is True
    assert result.payload["summary"]["sample_limit"] == 1
    assert {caveat["caveat"] for caveat in result.payload["caveats"]} >= {
        "sampled_assessment",
        "validation_not_included",
    }


def test_write_doctor_gate_json_writes_payload(tmp_path: Path) -> None:
    path = tmp_path / "gate.json"
    result = DoctorGateResult(
        {
            "schema_version": DOCTOR_GATE_SCHEMA_VERSION,
            "profile": "advisory",
            "passed": True,
        }
    )

    write_doctor_gate_json(path, result)

    assert json.loads(path.read_text()) == result.payload


def test_file_risk_profile_is_deterministic() -> None:
    score, band, readiness, reasons = _file_risk_profile(
        parse_ok=False,
        parse_error_count=2,
        rule_coverage=1.0,
        semantic_warning_count=0,
        unhandled_count=0,
        todo_count=0,
        unresolved_import_count=0,
    )
    assert score == 100.0
    assert band == "critical"
    assert readiness == "not_ready"
    assert reasons[0]["reason"] == "parse_errors"
    assert reasons[0]["count"] == 2
    assert reasons[0]["weight"] == 100.0

    score, band, readiness, reasons = _file_risk_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=1.0,
        semantic_warning_count=0,
        unhandled_count=0,
        todo_count=0,
        unresolved_import_count=0,
    )
    assert score == 0.0
    assert band == "low"
    assert readiness == "ready"
    assert reasons == []

    score, band, readiness, reasons = _file_risk_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=1.0,
        semantic_warning_count=9,
        unhandled_count=0,
        todo_count=0,
        unresolved_import_count=0,
    )
    assert band == "medium"
    assert readiness == "requires_manual_fixes"
    assert reasons[0]["reason"] == "semantic_warnings"

    score, band, readiness, reasons = _file_risk_profile(
        parse_ok=True,
        parse_error_count=0,
        rule_coverage=0.0,
        semantic_warning_count=0,
        unhandled_count=0,
        todo_count=0,
        unresolved_import_count=0,
    )
    assert band == "high"
    assert readiness == "not_ready"
    assert reasons[0]["reason"] == "low_rule_coverage"
    assert score >= 55.0


def test_doctor_config_suggestions_honor_full_name_annotation_map(tmp_path: Path) -> None:
    source = tmp_path / "Controller.java"
    source.write_text(
        """
        import org.springframework.web.bind.annotation.RestController;

        @RestController
        public class Controller {}
        """,
    )
    cfg = CFG.model_copy(
        update={
            "annotation_map": {
                "org.springframework.web.bind.annotation.RestController": {},
            }
        },
    )

    payload = assess_project(source, cfg=cfg).payload

    assert payload["annotation_inventory"] == [{"name": "RestController", "count": 1}]
    assert payload["config_suggestions"]["annotation_map"] == []


def test_doctor_assessment_reports_repeated_diagnostic_clusters(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "A.java").write_text(
        "package com.example; public class A { int x(int value) { return value / 2; } }"
    )
    (source / "B.java").write_text(
        "package com.example; public class B { int y(int value) { return value / 2; } }"
    )
    (source / "C.java").write_text(
        "package com.example; import static com.example.Missing.*; "
        "public class C { int z() { return ONE + TWO; } }"
    )
    (source / "D.java").write_text(
        "package com.example; import static com.example.Missing.*; "
        "public class D { int w() { return ONE + TWO; } }"
    )

    payload = assess_project(source, cfg=CFG).payload
    clusters = payload["diagnostic_clusters"]
    cluster_by_id = {cluster["cluster_id"]: cluster for cluster in clusters}

    assert cluster_by_id["numeric-operators"]["count"] == 2
    assert len(cluster_by_id["numeric-operators"]["examples"]) == 2
    assert cluster_by_id["numeric-operators"]["affected_files"] == [
        {"path": "A.java", "count": 1},
        {"path": "B.java", "count": 1},
    ]
    assert cluster_by_id["wildcard_static_import_unresolved"]["count"] == 2
    assert len(cluster_by_id["wildcard_static_import_unresolved"]["affected_files"]) == 2
    assert {
        "numeric-operators",
        "wildcard_static_import_unresolved",
    } <= set(cluster_by_id)


def test_doctor_assessment_json_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")

    first = assess_project(source, cfg=CFG).to_json()
    second = assess_project(source, cfg=CFG).to_json()

    assert first == second
    assert json.loads(first)["files"][0]["classes"][0]["name"] == "Sample"


def test_doctor_config_suggestions_render_reviewable_yaml(tmp_path: Path) -> None:
    source = tmp_path / "Controller.java"
    source.write_text(
        """
        import org.springframework.web.bind.annotation.RestController;
        import com.external.PaymentClient;

        @RestController
        public class Controller {
            private PaymentClient client;
        }
        """,
    )

    rendered = render_config_suggestions(assess_project(source, cfg=CFG))

    assert "config_suggestions:" in rendered
    assert 'java_import: "com.external.PaymentClient"' in rendered
    assert 'annotation: "RestController"' in rendered


def test_doctor_diff_reports_improvements(tmp_path: Path) -> None:
    source = tmp_path / "Controller.java"
    source.write_text(
        """
        import org.springframework.web.bind.annotation.RestController;
        import com.external.PaymentClient;

        @RestController
        public class Controller {
            private PaymentClient client;
        }
        """,
    )
    before = assess_project(source, cfg=CFG)
    after_cfg = CFG.model_copy(
        update={
            "import_map": {
                "com.external.PaymentClient": "payments.PaymentClient",
            },
            "annotation_map": {
                "RestController": {"preserve_comment": False},
            },
        },
    )
    after = assess_project(source, cfg=after_cfg)

    diff = diff_assessments(before, after)
    text = render_doctor_diff_text(diff)
    file_changes = diff.payload["file_changes"]["changed"]
    assert len(file_changes) == 1
    changed = file_changes[0]

    assert diff.payload["summary_delta"]["unresolved_imports"] == -1
    assert [item["import"] for item in diff.payload["unresolved_imports"]["removed"]] == [
        "com.external.PaymentClient"
    ]
    assert changed["risk_score_delta"] < 0
    assert changed["readiness_bucket_before"] in {"ready", "requires_manual_fixes", "not_ready"}
    assert changed["readiness_bucket_after"] in {"ready", "requires_manual_fixes", "not_ready"}
    assert "Unresolved imports: 1 removed, 0 added" in text
    assert f"risk {changed['risk_score_delta']:+.1f}" in text


def test_file_changes_omits_unchanged_files() -> None:
    before = DoctorAssessment(
        {
            "schema_version": DOCTOR_SCHEMA_VERSION,
            "source": "before",
            "summary": {},
            "files": [
                _minimal_doctor_file_payload("A.java", rule_coverage=0.85, risk_score=5.0),
                _minimal_doctor_file_payload(
                    "B.java",
                    rule_coverage=0.80,
                    semantic_warning_count=1,
                    unhandled_count=0,
                    unresolved_import_count=1,
                    risk_score=12.0,
                ),
                _minimal_doctor_file_payload("C.java", parse_ok=False, risk_score=100.0),
            ],
        },
    )
    after = DoctorAssessment(
        {
            "schema_version": DOCTOR_SCHEMA_VERSION,
            "source": "after",
            "summary": {},
            "files": [
                _minimal_doctor_file_payload("A.java", rule_coverage=0.85, risk_score=5.0),
                _minimal_doctor_file_payload(
                    "B.java",
                    rule_coverage=0.95,
                    semantic_warning_count=2,
                    unhandled_count=1,
                    unresolved_import_count=1,
                    risk_score=11.0,
                ),
                _minimal_doctor_file_payload("C.java", parse_ok=False, risk_score=100.0),
            ],
        },
    )

    diff = diff_assessments(before, after)
    changed_paths = {item["path"] for item in diff.payload["file_changes"]["changed"]}

    assert changed_paths == {"B.java"}


def test_doctor_assessment_html_is_static(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")

    html = render_assessment_html(assess_project(source, cfg=CFG))

    assert "j2py doctor assessment" in html
    assert "Sample.java" in html
    assert "Hotspots" in html
    assert "Diagnostic Clusters" in html
    assert "Risk" in html
    assert "Ready files" in html
    assert "<script" not in html
    assert "https://" not in html


def test_doctor_assessment_html_formats_low_coverage_hotspot_percentage(tmp_path: Path) -> None:
    source = tmp_path / "LowCoverage.java"
    source.write_text("package com.example; public class LowCoverage {}")
    payload = assess_project(source, cfg=CFG).payload
    payload["hotspots"]["lowest_coverage_files"] = [
        {"path": "LowCoverage.java", "rule_coverage": 0.73},
    ]

    html = render_assessment_html(DoctorAssessment(payload))

    assert "<code>LowCoverage.java</code>: 73%" in html
    assert "<code>LowCoverage.java</code>: 0.73" not in html


def test_load_assessment_json_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "assessment.json"
    path.write_text(json.dumps({"schema_version": DOCTOR_SCHEMA_VERSION - 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported doctor schema_version"):
        load_assessment_json(path)


def test_load_assessment_json_rejects_non_integer_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "assessment.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid doctor schema_version"):
        load_assessment_json(path)


def test_load_assessment_json_rejects_missing_summary(tmp_path: Path) -> None:
    path = tmp_path / "assessment.json"
    path.write_text(
        json.dumps({"schema_version": DOCTOR_SCHEMA_VERSION, "files": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid payload: expected 'summary'"):
        load_assessment_json(path)


def test_load_assessment_json_rejects_missing_files(tmp_path: Path) -> None:
    path = tmp_path / "assessment.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": DOCTOR_SCHEMA_VERSION,
                "summary": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid payload: expected 'files' array"):
        load_assessment_json(path)

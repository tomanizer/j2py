"""Tests for the j2py doctor assessment command."""

from __future__ import annotations

import json
from pathlib import Path

from j2py.config.loader import ConfigLoader
from j2py.doctor import (
    DOCTOR_SCHEMA_VERSION,
    DoctorAssessment,
    DoctorDiff,
    assess_project,
    diff_assessments,
    load_assessment_json,
    render_assessment_html,
    render_config_suggestions,
    render_doctor_diff_text,
    write_assessment_html,
    write_assessment_json,
    write_config_suggestions,
    write_doctor_diff_json,
)
from j2py.doctor_assessment import _file_risk_profile

CFG = ConfigLoader().add_defaults().build()


def test_doctor_public_facade_exports_stable_api() -> None:
    assert DOCTOR_SCHEMA_VERSION == 1
    assert DoctorAssessment({"schema_version": 1}).to_json()
    assert DoctorDiff({"schema_version": 1}).to_json()
    assert callable(assess_project)
    assert callable(diff_assessments)
    assert callable(load_assessment_json)
    assert callable(render_assessment_html)
    assert callable(render_config_suggestions)
    assert callable(render_doctor_diff_text)
    assert callable(write_assessment_html)
    assert callable(write_assessment_json)
    assert callable(write_config_suggestions)
    assert callable(write_doctor_diff_json)


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

    payload = assess_project(source, cfg=CFG).payload

    assert payload["schema_version"] == 1
    assert payload["summary"]["files"] == 3
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
    assert {reason["reason"] for reason in broken["risk_reasons"]} == {"parse_errors"}

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
    assert reasons == [
        {"reason": "parse_errors", "count": 2, "weight": 100.0},
    ]

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


def test_doctor_assessment_html_is_static(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")

    html = render_assessment_html(assess_project(source, cfg=CFG))

    assert "j2py doctor assessment" in html
    assert "Sample.java" in html
    assert "Hotspots" in html
    assert "Risk" in html
    assert "Ready files" in html
    assert "<script" not in html
    assert "https://" not in html

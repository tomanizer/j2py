"""Tests for the j2py doctor assessment command."""

from __future__ import annotations

import json
from pathlib import Path

from j2py.config.loader import ConfigLoader
from j2py.doctor import (
    assess_project,
    diff_assessments,
    render_assessment_html,
    render_config_suggestions,
    render_doctor_diff_text,
)

CFG = ConfigLoader().add_defaults().build()


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

    suggestions = payload["config_suggestions"]
    assert {item["annotation"] for item in suggestions["annotation_map"]} == {"RestController"}
    assert payload["hotspots"]["unresolved_import_packages"][0] == {
        "package": "com.external",
        "count": 1,
    }
    assert payload["hotspots"]["lowest_coverage_files"][0]["path"] == "Broken.java"
    assert "j2py translate" in payload["recommended_next_commands"][0]


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

    assert diff.payload["summary_delta"]["unresolved_imports"] == -1
    assert [item["import"] for item in diff.payload["unresolved_imports"]["removed"]] == [
        "com.external.PaymentClient"
    ]
    assert "Unresolved imports: 1 removed, 0 added" in text


def test_doctor_assessment_html_is_static(tmp_path: Path) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")

    html = render_assessment_html(assess_project(source, cfg=CFG))

    assert "j2py doctor assessment" in html
    assert "Sample.java" in html
    assert "Hotspots" in html
    assert "<script" not in html
    assert "https://" not in html

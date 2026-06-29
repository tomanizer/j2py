"""File I/O helpers for doctor assessments and diffs."""

from __future__ import annotations

import json
from pathlib import Path

from j2py.doctor_models import DOCTOR_SCHEMA_VERSION, DoctorAssessment, DoctorDiff
from j2py.doctor_renderers import render_assessment_html, render_config_suggestions


def write_assessment_json(path: Path, assessment: DoctorAssessment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(assessment.to_json(), encoding="utf-8")


def write_assessment_html(path: Path, assessment: DoctorAssessment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_assessment_html(assessment), encoding="utf-8")


def write_config_suggestions(path: Path, assessment: DoctorAssessment) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config_suggestions(assessment), encoding="utf-8")


def load_assessment_json(path: Path) -> DoctorAssessment:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a doctor assessment object")
    _validate_doctor_schema(payload, path)
    return DoctorAssessment(payload=payload)


def _validate_doctor_schema(payload: dict[str, object], path: Path) -> None:
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int):
        raise ValueError(
            f"{path} has invalid doctor schema_version: "
            f"{schema_version!r}; expected {DOCTOR_SCHEMA_VERSION}"
        )
    if schema_version != DOCTOR_SCHEMA_VERSION:
        raise ValueError(
            f"{path} uses unsupported doctor schema_version {schema_version}; "
            f"expected {DOCTOR_SCHEMA_VERSION}"
        )


def write_doctor_diff_json(path: Path, diff: DoctorDiff) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(diff.to_json(), encoding="utf-8")

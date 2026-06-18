"""Public facade for project assessment reports."""

from __future__ import annotations

from j2py.doctor_assessment import assess_project
from j2py.doctor_diff import diff_assessments
from j2py.doctor_io import (
    load_assessment_json,
    write_assessment_html,
    write_assessment_json,
    write_config_suggestions,
    write_doctor_diff_json,
)
from j2py.doctor_models import DOCTOR_SCHEMA_VERSION, DoctorAssessment, DoctorDiff
from j2py.doctor_renderers import (
    render_assessment_html,
    render_config_suggestions,
    render_doctor_diff_text,
)

__all__ = [
    "DOCTOR_SCHEMA_VERSION",
    "DoctorAssessment",
    "DoctorDiff",
    "assess_project",
    "diff_assessments",
    "load_assessment_json",
    "render_assessment_html",
    "render_config_suggestions",
    "render_doctor_diff_text",
    "write_assessment_html",
    "write_assessment_json",
    "write_config_suggestions",
    "write_doctor_diff_json",
]

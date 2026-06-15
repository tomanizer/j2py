"""Equivalence pytest hooks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.equivalence.surface_report import PassedMethod, write_report


def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers",
        "equivalence_surface(fixture, signature): Java method signature verified by a "
        "literal-oracle equivalence test when the test item passes.",
    )
    config._j2py_equivalence_passed_methods = []  # type: ignore[attr-defined]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Any:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.passed:
        return
    passed = item.config._j2py_equivalence_passed_methods  # type: ignore[attr-defined]
    for marker in item.iter_markers(name="equivalence_surface"):
        fixture, signature = marker.args
        passed.append(
            PassedMethod(
                fixture=str(fixture),
                signature=str(signature),
                nodeid=report.nodeid,
            )
        )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    artifact = os.environ.get("J2PY_EQUIVALENCE_SURFACE_JSON")
    if not artifact:
        return
    passed = session.config._j2py_equivalence_passed_methods  # type: ignore[attr-defined]
    path = Path(artifact)
    if exitstatus == 0:
        write_report(path, passed)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "incomplete": True,
                "pytest_exitstatus": exitstatus,
                "passed_methods": [method.__dict__ for method in passed],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

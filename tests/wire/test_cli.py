"""CLI smoke tests for j2py-wire."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from j2py.wire.cli import app


def test_j2py_wire_list_empty_directory_exits_zero(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["list", str(tmp_path)])

    assert result.exit_code == 0
    assert "No wiring sidecars found" in result.output


def test_j2py_wire_list_reports_sidecars_and_elements(tmp_path: Path) -> None:
    sidecar = tmp_path / "nested" / "owner_controller.wiring.json"
    sidecar.parent.mkdir()
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "src/OwnerController.java",
                "output": "translated/owner_controller.py",
                "elements": [
                    {
                        "plugin": "spring-wiring",
                        "kind": "class",
                        "java_name": "OwnerController",
                        "python_name": "OwnerController",
                        "annotations": [],
                        "metadata": {
                            "spring": {
                                "profile_version": 1,
                                "role": "controller",
                            },
                        },
                    },
                    {
                        "plugin": "spring-wiring",
                        "kind": "method",
                        "java_name": "findOwner",
                        "python_name": "find_owner",
                        "annotations": [],
                        "metadata": {},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["list", str(tmp_path)])

    assert result.exit_code == 0
    assert "Found 1 wiring sidecar(s) with 2 element(s)." in result.output
    assert "translated/owner_controller.py: 2 element(s)" in result.output
    assert "Spring metadata elements: 1" in result.output


def test_j2py_wire_list_reports_malformed_sidecar(tmp_path: Path) -> None:
    (tmp_path / "bad.wiring.json").write_text("{", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["list", str(tmp_path)])

    assert result.exit_code == 1
    assert "malformed JSON" in result.output


def test_j2py_wire_generate_fastapi_writes_router_and_app(tmp_path: Path) -> None:
    translated = tmp_path / "translated"
    translated.mkdir()
    module = translated / "owner_controller.py"
    module.write_text("class OwnerController:\n    pass\n", encoding="utf-8")
    module.with_suffix(".wiring.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "OwnerController.java",
                "output": str(module),
                "elements": [
                    {
                        "plugin": "spring-wiring",
                        "kind": "class",
                        "java_name": "OwnerController",
                        "python_name": "OwnerController",
                        "annotations": [],
                        "metadata": {
                            "spring": {
                                "profile_version": 1,
                                "role": "controller",
                                "router_prefix": "/owners",
                            },
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    output = tmp_path / "wiring"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["generate", str(translated), "--target", "fastapi", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "generated" in result.output
    assert (output / "owner_controller_wiring.py").exists()
    assert (output / "app_wiring.py").exists()

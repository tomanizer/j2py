"""Tests for j2py-wire sidecar loading."""

from __future__ import annotations

import json
from pathlib import Path

from j2py.wire.loader import (
    discover_wiring_sidecars,
    load_wiring_sidecar,
    load_wiring_sidecars,
)


def _minimal_sidecar() -> dict[str, object]:
    return {
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
                "metadata": {},
            },
        ],
    }


def test_parse_minimal_generic_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "owner_controller.wiring.json"
    path.write_text(json.dumps(_minimal_sidecar()), encoding="utf-8")

    sidecar, diagnostics = load_wiring_sidecar(path)

    assert diagnostics == []
    assert sidecar is not None
    assert sidecar.schema_version == 1
    assert sidecar.elements[0].kind == "class"
    assert sidecar.elements[0].metadata == {}


def test_parse_sidecar_with_spring_metadata(tmp_path: Path) -> None:
    payload = _minimal_sidecar()
    elements = payload["elements"]
    assert isinstance(elements, list)
    element = elements[0]
    assert isinstance(element, dict)
    element["metadata"] = {
        "spring": {
            "profile_version": 1,
            "role": "controller",
            "router_prefix": "/owners",
        },
    }
    path = tmp_path / "owner_controller.wiring.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    sidecar, diagnostics = load_wiring_sidecar(path)

    assert diagnostics == []
    assert sidecar is not None
    assert sidecar.elements[0].spring == {
        "profile_version": 1,
        "role": "controller",
        "router_prefix": "/owners",
    }


def test_loader_walks_directory_tree_and_finds_sidecars(tmp_path: Path) -> None:
    nested = tmp_path / "translated" / "com" / "example"
    nested.mkdir(parents=True)
    expected = nested / "owner_controller.wiring.json"
    expected.write_text(json.dumps(_minimal_sidecar()), encoding="utf-8")
    (nested / "owner_controller.py").write_text("class OwnerController:\n    pass\n")

    paths = discover_wiring_sidecars(tmp_path / "translated")
    result = load_wiring_sidecars(tmp_path / "translated")

    assert paths == [expected]
    assert result.diagnostics == []
    assert len(result.sidecars) == 1
    assert result.sidecars[0].output == "translated/owner_controller.py"


def test_loader_reports_unknown_schema_version_as_warning(tmp_path: Path) -> None:
    payload = _minimal_sidecar()
    payload["schema_version"] = 99
    path = tmp_path / "owner_controller.wiring.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    sidecar, diagnostics = load_wiring_sidecar(path)

    assert sidecar is not None
    assert len(diagnostics) == 1
    assert diagnostics[0].level == "warning"
    assert "unknown wiring schema_version 99" in diagnostics[0].message


def test_loader_reports_missing_file_malformed_json_and_schema_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.wiring.json"
    malformed = tmp_path / "malformed.wiring.json"
    invalid = tmp_path / "invalid.wiring.json"
    malformed.write_text("{", encoding="utf-8")
    invalid.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    missing_sidecar, missing_diagnostics = load_wiring_sidecar(missing)
    malformed_sidecar, malformed_diagnostics = load_wiring_sidecar(malformed)
    invalid_sidecar, invalid_diagnostics = load_wiring_sidecar(invalid)

    assert missing_sidecar is None
    assert missing_diagnostics[0].level == "error"
    assert "sidecar not found" in missing_diagnostics[0].message
    assert malformed_sidecar is None
    assert malformed_diagnostics[0].level == "error"
    assert "malformed JSON" in malformed_diagnostics[0].message
    assert invalid_sidecar is None
    assert invalid_diagnostics[0].level == "error"
    assert "invalid wiring sidecar schema" in invalid_diagnostics[0].message

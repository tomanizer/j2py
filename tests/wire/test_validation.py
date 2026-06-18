"""Tests for j2py-wire validation checks."""

from __future__ import annotations

import json
from pathlib import Path

import j2py.pipeline as pipeline
from j2py.framework_plugins.spring import SpringWiringPlugin
from j2py.pipeline import translate_file
from j2py.wire.loader import load_wiring_sidecars
from j2py.wire.targets.fastapi import FastAPITarget
from j2py.wire.validation import (
    MissingProviderCheck,
    MissingSessionFactoryCheck,
    OrphanControllerCheck,
    RouteHandlerCheck,
    RouteParameterCheck,
    SpringProfileCheck,
    UnresolvedImportCheck,
    ValidationContext,
    validate_fastapi_wiring,
    validation_exit_code,
)
from tests.translate.skeleton.helpers import CFG, FIXTURES


def _spring_cfg():
    return CFG.model_copy(
        update={
            "annotation_map_preset": "spring",
            "framework_plugins": [SpringWiringPlugin()],
            "emit_wiring_metadata": True,
        },
    )


def test_validate_real_petclinic_sidecar_reports_only_session_stub(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    translated_root.mkdir()
    output = translated_root / "owner_controller.py"
    fixture = FIXTURES / "java" / "PetClinicOwnerController.java"
    result = translate_file(fixture, cfg=_spring_cfg(), use_llm=False, validate=False)
    result.output_path = output
    output.write_text(result.python_source, encoding="utf-8")
    assert pipeline.write_wiring_metadata_sidecar(result) is not None
    load_result = load_wiring_sidecars(translated_root)
    wiring_dir = tmp_path / "wiring"
    FastAPITarget(translated_root=translated_root).generate(load_result.sidecars, wiring_dir)

    findings = validate_fastapi_wiring(
        ValidationContext(translated_root, wiring_dir, load_result.sidecars),
    )

    assert validation_exit_code(findings) == 1
    assert {finding.code for finding in findings} == {"missing-session-factory"}


def test_spring_profile_check_reports_invalid_profile(tmp_path: Path) -> None:
    context = _context(tmp_path)
    payload = _payload(context.translated_root / "owner_controller.py")
    payload["elements"][0]["metadata"]["spring"]["profile_version"] = 99
    _write_sidecar(context.translated_root, payload)
    context = _loaded_context(context)

    findings = SpringProfileCheck().run(context)

    assert findings
    assert findings[0].severity == "error"
    assert findings[0].code == "spring-profile"


def test_missing_provider_check_reports_injected_dependency_without_provider(
    tmp_path: Path,
) -> None:
    context = _generated_context(tmp_path)
    router = context.wiring_dir / "owner_controller_wiring.py"
    router.write_text(
        router.read_text(encoding="utf-8").replace("def get_owner_repository", "def missing"),
        encoding="utf-8",
    )

    findings = MissingProviderCheck().run(context)

    assert findings
    assert findings[0].code == "missing-provider"
    assert findings[0].severity == "error"


def test_unresolved_import_check_reports_missing_translated_module(tmp_path: Path) -> None:
    context = _generated_context(tmp_path)
    (context.translated_root / "owner_controller.py").unlink()

    findings = UnresolvedImportCheck().run(context)

    assert findings
    assert findings[0].code == "unresolved-import"
    assert "owner_controller" in findings[0].message


def test_route_handler_check_reports_missing_controller_method(tmp_path: Path) -> None:
    context = _generated_context(tmp_path)
    module = context.translated_root / "owner_controller.py"
    module.write_text(module.read_text(encoding="utf-8").replace("def find_owner", "def missing"))

    findings = RouteHandlerCheck().run(context)

    assert findings
    assert findings[0].code == "route-handler"
    assert findings[0].severity == "warning"


def test_route_parameter_check_reports_signature_mismatch(tmp_path: Path) -> None:
    context = _generated_context(tmp_path)
    router = context.wiring_dir / "owner_controller_wiring.py"
    router.write_text(router.read_text(encoding="utf-8").replace("owner_id: int,", ""))

    findings = RouteParameterCheck().run(context)

    assert findings
    assert findings[0].code == "route-parameter"
    assert "owner_id" in findings[0].message


def test_missing_session_factory_check_reports_stub(tmp_path: Path) -> None:
    context = _generated_context(tmp_path)

    findings = MissingSessionFactoryCheck().run(context)

    assert findings
    assert findings[0].code == "missing-session-factory"


def test_orphan_controller_check_reports_missing_wiring_file(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _write_sidecar(
        context.translated_root,
        _payload(context.translated_root / "owner_controller.py"),
    )
    context = _loaded_context(context)

    findings = OrphanControllerCheck().run(context)

    assert findings
    assert findings[0].code == "orphan-controller"
    assert findings[0].severity == "error"


def _generated_context(tmp_path: Path) -> ValidationContext:
    context = _context(tmp_path)
    _write_translated_module(context.translated_root)
    _write_sidecar(
        context.translated_root,
        _payload(context.translated_root / "owner_controller.py"),
    )
    context = _loaded_context(context)
    FastAPITarget(translated_root=context.translated_root).generate(
        context.sidecars,
        context.wiring_dir,
    )
    return context


def _context(tmp_path: Path) -> ValidationContext:
    translated_root = tmp_path / "translated"
    wiring_dir = tmp_path / "wiring"
    translated_root.mkdir()
    return ValidationContext(translated_root=translated_root, wiring_dir=wiring_dir, sidecars=[])


def _loaded_context(context: ValidationContext) -> ValidationContext:
    load_result = load_wiring_sidecars(context.translated_root)
    assert load_result.diagnostics == []
    return ValidationContext(
        translated_root=context.translated_root,
        wiring_dir=context.wiring_dir,
        sidecars=load_result.sidecars,
    )


def _write_translated_module(translated_root: Path) -> None:
    (translated_root / "owner_controller.py").write_text(
        "\n".join(
            [
                "class OwnerRepository:",
                "    def __init__(self, session):",
                "        self.session = session",
                "",
                "class OwnerRequest:",
                "    pass",
                "",
                "class OwnerController:",
                "    def __init__(self, owner_repository):",
                "        self.owner_repository = owner_repository",
                "    def find_owner(self, owner_id):",
                "        return owner_id",
                "    def create_owner(self, request):",
                "        return request",
            ],
        )
        + "\n",
        encoding="utf-8",
    )


def _write_sidecar(translated_root: Path, payload: dict[str, object]) -> None:
    (translated_root / "owner_controller.wiring.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _payload(module: Path) -> dict[str, object]:
    return {
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
            {
                "plugin": "spring-wiring",
                "kind": "field",
                "java_name": "ownerRepository",
                "python_name": "owner_repository",
                "annotations": [],
                "metadata": {
                    "spring": {
                        "profile_version": 1,
                        "inject": {
                            "name": "owner_repository",
                            "java_name": "ownerRepository",
                            "type": "OwnerRepository",
                            "source": "field",
                            "required": True,
                            "qualifier": None,
                        },
                    },
                },
            },
            {
                "plugin": "spring-wiring",
                "kind": "method",
                "java_name": "findOwner",
                "python_name": "find_owner",
                "annotations": [],
                "metadata": {
                    "spring": {
                        "profile_version": 1,
                        "route": {
                            "http_method": "GET",
                            "path": "/{owner_id}",
                            "handler": "find_owner",
                            "status_code": 200,
                            "parameters": [
                                {
                                    "name": "owner_id",
                                    "java_name": "ownerId",
                                    "source": "path",
                                    "python_type": "int",
                                    "required": True,
                                },
                            ],
                            "request_body": None,
                        },
                    },
                },
            },
            {
                "plugin": "spring-wiring",
                "kind": "method",
                "java_name": "createOwner",
                "python_name": "create_owner",
                "annotations": [],
                "metadata": {
                    "spring": {
                        "profile_version": 1,
                        "route": {
                            "http_method": "POST",
                            "path": "",
                            "handler": "create_owner",
                            "status_code": 201,
                            "parameters": [],
                            "request_body": {
                                "name": "request",
                                "java_name": "request",
                                "python_type": "OwnerRequest",
                                "required": True,
                            },
                        },
                    },
                },
            },
        ],
    }

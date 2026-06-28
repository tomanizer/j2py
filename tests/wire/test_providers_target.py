"""Tests for framework-neutral provider generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from j2py.wire.cli import app
from j2py.wire.loader import load_wiring_sidecars
from j2py.wire.targets.common import GENERATED_HEADER
from j2py.wire.targets.providers import ProvidersTarget
from j2py.wire.validation import (
    ProviderDependencyCheck,
    ProviderFunctionCheck,
    ValidationContext,
    validate_providers_wiring,
    validation_exit_code,
)


def test_providers_target_generates_plain_provider_graph(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_graph(translated_root)
    _write_graph_sidecars(translated_root)
    _write_sqlalchemy_stub(tmp_path)
    load_result = load_wiring_sidecars(translated_root)
    output_dir = tmp_path / "wiring"

    generated = ProvidersTarget(translated_root=translated_root).generate(
        load_result.sidecars,
        output_dir,
    )

    providers = output_dir / "providers.py"
    assert generated == [providers]
    source = providers.read_text(encoding="utf-8")
    assert source.startswith(GENERATED_HEADER)
    assert "from sqlalchemy.orm import Session" in source
    assert "from owner_controller import OwnerController" in source
    assert "from owner_repository import OwnerRepository" in source
    assert "from owner_service import OwnerService" in source
    assert source.index("def get_owner_repository") < source.index("def get_owner_service")
    assert source.index("def get_owner_service") < source.index("def get_owner_controller")
    assert "def get_owner_repository(session: Session) -> OwnerRepository:" in source
    assert "def get_owner_service(owner_repository: OwnerRepository) -> OwnerService:" in source
    assert "def get_owner_controller(owner_service: OwnerService) -> OwnerController:" in source
    assert "Depends" not in source

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.syspath_prepend(str(translated_root))
    for name in [
        "sqlalchemy",
        "sqlalchemy.orm",
        "wiring.providers",
        "owner_controller",
        "owner_repository",
        "owner_service",
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    providers_module = __import__(
        "wiring.providers",
        fromlist=["get_owner_controller", "get_owner_repository", "get_owner_service"],
    )
    session = object()
    repository = providers_module.get_owner_repository(session)
    service = providers_module.get_owner_service(repository)
    controller = providers_module.get_owner_controller(service)

    assert repository.session is session
    assert service.owner_repository is repository
    assert controller.owner_service is service


def test_providers_target_overwrites_generated_file(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_graph(translated_root)
    _write_graph_sidecars(translated_root)
    output_dir = tmp_path / "wiring"
    load_result = load_wiring_sidecars(translated_root)
    target = ProvidersTarget(translated_root=translated_root)
    target.generate(load_result.sidecars, output_dir)
    providers = output_dir / "providers.py"
    providers.write_text("stale\n", encoding="utf-8")

    target.generate(load_result.sidecars, output_dir)

    assert providers.read_text(encoding="utf-8").startswith(GENERATED_HEADER)


def test_j2py_wire_generate_providers_cli(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_graph(translated_root)
    _write_graph_sidecars(translated_root)
    output_dir = tmp_path / "wiring"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["generate", str(translated_root), "--target", "providers", "--output", str(output_dir)],
    )

    assert result.exit_code == 0
    assert "generated" in result.output
    assert (output_dir / "providers.py").exists()


def test_j2py_wire_validate_providers_cli_outputs_json(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    _write_translated_graph(translated_root)
    _write_graph_sidecars(translated_root)
    output_dir = tmp_path / "wiring"
    runner = CliRunner()
    generated = runner.invoke(
        app,
        ["generate", str(translated_root), "--target", "providers", "--output", str(output_dir)],
    )
    assert generated.exit_code == 0

    result = runner.invoke(
        app,
        [
            "validate",
            str(translated_root),
            "--target",
            "providers",
            "--wiring-dir",
            str(output_dir),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {"errors": 0, "findings": [], "warnings": 0}


def test_validate_providers_reports_missing_provider_function(tmp_path: Path) -> None:
    context = _generated_context(tmp_path)
    providers = context.wiring_dir / "providers.py"
    providers.write_text(
        providers.read_text(encoding="utf-8").replace("def get_owner_service", "def missing"),
        encoding="utf-8",
    )

    findings = ProviderFunctionCheck().run(context)

    assert len(findings) == 1
    assert findings[0].code == "provider-function"
    assert "get_owner_service" in findings[0].message


def test_validate_providers_reports_missing_dependency_edge(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    translated_root.mkdir()
    (translated_root / "owner_controller.py").write_text(
        "class OwnerController:\n"
        "    def __init__(self, missing_client):\n"
        "        self.missing_client = missing_client\n",
        encoding="utf-8",
    )
    _write_sidecar(
        translated_root,
        "owner_controller",
        _sidecar_payload(
            translated_root / "owner_controller.py",
            class_name="OwnerController",
            role="controller",
            component_name="ownerController",
            router_prefix="/owners",
            injections=[
                {
                    "name": "missing_client",
                    "java_name": "missingClient",
                    "type": "MissingClient",
                    "source": "field",
                    "required": True,
                    "qualifier": None,
                },
            ],
        ),
    )
    load_result = load_wiring_sidecars(translated_root)
    wiring_dir = tmp_path / "wiring"
    ProvidersTarget(translated_root=translated_root).generate(load_result.sidecars, wiring_dir)
    context = ValidationContext(
        translated_root=translated_root,
        wiring_dir=wiring_dir,
        sidecars=load_result.sidecars,
    )

    findings = ProviderDependencyCheck().run(context)

    assert len(findings) == 1
    assert findings[0].code == "provider-dependency"
    assert "missing_client" in findings[0].message


def test_validate_providers_dispatch_passes_generated_graph(tmp_path: Path) -> None:
    context = _generated_context(tmp_path)

    findings = validate_providers_wiring(context)

    assert findings == []
    assert validation_exit_code(findings) == 0


def _generated_context(tmp_path: Path) -> ValidationContext:
    translated_root = tmp_path / "translated"
    _write_translated_graph(translated_root)
    _write_graph_sidecars(translated_root)
    load_result = load_wiring_sidecars(translated_root)
    wiring_dir = tmp_path / "wiring"
    ProvidersTarget(translated_root=translated_root).generate(load_result.sidecars, wiring_dir)
    return ValidationContext(
        translated_root=translated_root,
        wiring_dir=wiring_dir,
        sidecars=load_result.sidecars,
    )


def _write_translated_graph(translated_root: Path) -> None:
    translated_root.mkdir(parents=True, exist_ok=True)
    (translated_root / "owner_repository.py").write_text(
        "class OwnerRepository:\n"
        "    def __init__(self, session):\n"
        "        self.session = session\n",
        encoding="utf-8",
    )
    (translated_root / "owner_service.py").write_text(
        "class OwnerService:\n"
        "    def __init__(self, owner_repository):\n"
        "        self.owner_repository = owner_repository\n",
        encoding="utf-8",
    )
    (translated_root / "owner_controller.py").write_text(
        "class OwnerController:\n"
        "    def __init__(self, owner_service):\n"
        "        self.owner_service = owner_service\n",
        encoding="utf-8",
    )


def _write_graph_sidecars(translated_root: Path) -> None:
    _write_sidecar(
        translated_root,
        "owner_repository",
        _sidecar_payload(
            translated_root / "owner_repository.py",
            class_name="OwnerRepository",
            role="repository",
            component_name="ownerRepository",
        ),
    )
    _write_sidecar(
        translated_root,
        "owner_service",
        _sidecar_payload(
            translated_root / "owner_service.py",
            class_name="OwnerService",
            role="service",
            component_name="ownerService",
            injections=[
                {
                    "name": "owner_repository",
                    "java_name": "ownerRepository",
                    "type": "OwnerRepository",
                    "source": "field",
                    "required": True,
                    "qualifier": None,
                },
            ],
        ),
    )
    _write_sidecar(
        translated_root,
        "owner_controller",
        _sidecar_payload(
            translated_root / "owner_controller.py",
            class_name="OwnerController",
            role="controller",
            component_name="ownerController",
            router_prefix="/owners",
            injections=[
                {
                    "name": "owner_service",
                    "java_name": "ownerService",
                    "type": "OwnerService",
                    "source": "field",
                    "required": True,
                    "qualifier": None,
                },
            ],
        ),
    )


def _write_sidecar(translated_root: Path, stem: str, payload: dict[str, object]) -> None:
    (translated_root / f"{stem}.wiring.json").write_text(json.dumps(payload), encoding="utf-8")


def _sidecar_payload(
    module: Path,
    *,
    class_name: str,
    role: str,
    component_name: str,
    router_prefix: str | None = None,
    injections: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    spring: dict[str, object] = {
        "profile_version": 1,
        "role": role,
        "component_name": component_name,
    }
    if router_prefix is not None:
        spring["router_prefix"] = router_prefix
    elements: list[dict[str, object]] = [
        {
            "plugin": "spring-wiring",
            "kind": "class",
            "java_name": class_name,
            "python_name": class_name,
            "annotations": [],
            "metadata": {
                "spring": spring,
            },
        },
    ]
    for injection in injections or []:
        elements.append(
            {
                "plugin": "spring-wiring",
                "kind": "field",
                "java_name": str(injection["java_name"]),
                "python_name": str(injection["name"]),
                "annotations": [],
                "metadata": {
                    "spring": {
                        "profile_version": 1,
                        "inject": injection,
                    },
                },
            },
        )
    return {
        "schema_version": 1,
        "source": f"{class_name}.java",
        "output": str(module),
        "elements": elements,
    }


def _write_sqlalchemy_stub(root: Path) -> None:
    sqlalchemy = root / "sqlalchemy"
    sqlalchemy.mkdir()
    (sqlalchemy / "__init__.py").write_text("", encoding="utf-8")
    (sqlalchemy / "orm.py").write_text("class Session:\n    pass\n", encoding="utf-8")

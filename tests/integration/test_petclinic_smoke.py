"""PetClinic owner-slice translate -> wire -> FastAPI integration smoke."""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from typer.testing import CliRunner

import j2py.pipeline as pipeline
from j2py.config.loader import ConfigLoader
from j2py.framework_plugins.spring import SpringWiringPlugin
from j2py.pipeline import translate_file
from j2py.wire.cli import app as wire_app

pytestmark = pytest.mark.spring_smoke

FIXTURES = Path(__file__).parent.parent / "fixtures"
PETCLINIC_SLICE = FIXTURES / "java" / "PetClinicSmokeOwnerSlice.java"
_MISSING = object()


@pytest.fixture(scope="session")
def petclinic_app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    fastapi = pytest.importorskip("fastapi")
    testclient = pytest.importorskip("fastapi.testclient")
    sqlalchemy = pytest.importorskip("sqlalchemy")
    sqlalchemy_orm = pytest.importorskip("sqlalchemy.orm")
    sqlalchemy_pool = pytest.importorskip("sqlalchemy.pool")

    workspace = tmp_path_factory.mktemp("petclinic-smoke")
    translated_root = workspace / "translated"
    wiring_dir = workspace / "petclinic_wiring"
    translated_root.mkdir()
    output = translated_root / "petclinic_smoke_owner_slice.py"

    result = translate_file(PETCLINIC_SLICE, cfg=_spring_cfg(), use_llm=False, validate=False)
    result.output_path = output
    output.write_text(result.python_source, encoding="utf-8")
    sidecar = pipeline.write_wiring_metadata_sidecar(result)
    assert sidecar == output.with_suffix(".wiring.json")

    runner = CliRunner()
    generated = runner.invoke(
        wire_app,
        ["generate", str(translated_root), "--target", "fastapi", "--output", str(wiring_dir)],
    )
    assert generated.exit_code == 0, generated.output
    assert (wiring_dir / "petclinic_smoke_owner_slice_wiring.py").exists()
    assert (wiring_dir / "app_wiring.py").exists()

    validation = runner.invoke(
        wire_app,
        [
            "validate",
            str(translated_root),
            "--wiring-dir",
            str(wiring_dir),
            "--format",
            "json",
        ],
    )
    assert validation.exit_code == 1, validation.output
    validation_payload = json.loads(validation.output)
    assert validation_payload["errors"] == 0
    assert {item["code"] for item in validation_payload["findings"]} == {
        "missing-session-factory",
    }

    runtime = importlib.import_module("j2py.translate.runtime.j2py_runtime")
    previous_runtime = sys.modules.get("j2py_runtime", _MISSING)
    sys.modules["j2py_runtime"] = runtime
    added_paths = [str(workspace), str(translated_root)]
    sys.path[:0] = added_paths
    imported: list[str] = []
    try:
        translated = _import_module("petclinic_smoke_owner_slice", imported)
        router_module = _import_module(
            "petclinic_wiring.petclinic_smoke_owner_slice_wiring",
            imported,
        )
        app_wiring = _import_module("petclinic_wiring.app_wiring", imported)

        engine = sqlalchemy.create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=sqlalchemy_pool.StaticPool,
        )
        translated.Base.metadata.create_all(engine)
        session_local = sqlalchemy_orm.sessionmaker(bind=engine)

        app = fastapi.FastAPI()
        app_wiring.register_routes(app)

        def get_session_override() -> Iterator[Any]:
            with session_local() as session:
                yield session

        class SmokeOwnerController(translated.OwnerController):  # type: ignore[name-defined]
            def find_owner(self, owner_id: int) -> Any:
                owner = self.owner_repository.find_by_id(owner_id)
                if owner is None:
                    raise fastapi.HTTPException(status_code=404, detail="Owner not found")
                return _owner_payload(owner)

            def create_owner(self, request: Any) -> dict[str, Any]:
                owner = translated.Owner(**request.model_dump())
                saved = self.owner_repository.save(owner)
                self.owner_repository._session.commit()
                return _owner_payload(saved)

        owner_repository_dependency = fastapi.Depends(router_module.get_owner_repository)

        def get_owner_controller_override(
            owner_repository: Any = owner_repository_dependency,
        ) -> SmokeOwnerController:
            return SmokeOwnerController(owner_repository)

        app.dependency_overrides[router_module.get_session] = get_session_override
        app.dependency_overrides[router_module.get_owner_controller] = get_owner_controller_override

        with testclient.TestClient(app) as client:
            yield client
    finally:
        for path in added_paths:
            if path in sys.path:
                sys.path.remove(path)
        for name in imported:
            sys.modules.pop(name, None)
        if previous_runtime is _MISSING:
            sys.modules.pop("j2py_runtime", None)
        else:
            sys.modules["j2py_runtime"] = previous_runtime


def test_list_owners_empty(petclinic_app: Any) -> None:
    response = petclinic_app.get("/owners")

    assert response.status_code == 200
    assert response.json() == []


def test_get_owner_not_found(petclinic_app: Any) -> None:
    response = petclinic_app.get("/owners/999")

    assert response.status_code == 404


def test_create_owner(petclinic_app: Any) -> None:
    body = {
        "first_name": "James",
        "last_name": "Carter",
        "address": "110 W. Liberty St.",
        "city": "Madison",
        "telephone": "6085551023",
    }

    response = petclinic_app.post("/owners", json=body)

    assert response.status_code in (200, 201)
    assert response.json()["first_name"] == "James"


def _spring_cfg():
    return (
        ConfigLoader()
        .add_defaults()
        .build()
        .model_copy(
            update={
                "annotation_map_preset": "spring",
                "framework_plugins": [SpringWiringPlugin()],
                "emit_wiring_metadata": True,
            },
        )
    )


def _import_module(name: str, imported: list[str]) -> ModuleType:
    sys.modules.pop(name, None)
    module = importlib.import_module(name)
    imported.append(name)
    return module


def _owner_payload(owner: Any) -> dict[str, Any]:
    return {
        "id": owner.id,
        "first_name": owner.first_name,
        "last_name": owner.last_name,
        "address": owner.address,
        "city": owner.city,
        "telephone": owner.telephone,
    }

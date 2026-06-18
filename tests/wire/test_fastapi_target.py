"""Tests for FastAPI wiring generation."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import j2py.pipeline as pipeline
from j2py.framework_plugins.spring import SpringWiringPlugin
from j2py.pipeline import translate_file
from j2py.wire.loader import load_wiring_sidecars
from j2py.wire.targets.fastapi import GENERATED_HEADER, FastAPITarget
from tests.translate.skeleton.helpers import CFG, FIXTURES


def _spring_cfg():
    return CFG.model_copy(
        update={
            "annotation_map_preset": "spring",
            "framework_plugins": [SpringWiringPlugin()],
            "emit_wiring_metadata": True,
        },
    )


def test_fastapi_target_generates_router_from_real_petclinic_sidecar(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    translated_root.mkdir()
    output = translated_root / "owner_controller.py"
    fixture = FIXTURES / "java" / "PetClinicOwnerController.java"
    result = translate_file(fixture, cfg=_spring_cfg(), use_llm=False, validate=False)
    result.output_path = output
    output.write_text(result.python_source, encoding="utf-8")
    sidecar = pipeline.write_wiring_metadata_sidecar(result)
    assert sidecar is not None

    load_result = load_wiring_sidecars(translated_root)
    generated = FastAPITarget(translated_root=translated_root).generate(
        load_result.sidecars,
        tmp_path / "wiring",
    )

    router = tmp_path / "wiring" / "owner_controller_wiring.py"
    app_wiring = tmp_path / "wiring" / "app_wiring.py"
    assert generated == [router, app_wiring]
    router_source = router.read_text(encoding="utf-8")
    app_source = app_wiring.read_text(encoding="utf-8")
    assert router_source.startswith(GENERATED_HEADER)
    assert app_source.startswith(GENERATED_HEADER)
    assert 'router = APIRouter(prefix="/owners", tags=["owners"])' in router_source
    assert '@router.get("")' in router_source
    assert '@router.get("/{owner_id}")' in router_source
    assert '@router.post("", status_code=201)' in router_source
    assert "def get_owner_repository(" in router_source
    assert "owner_repository: OwnerRepository = Depends(get_owner_repository)," in router_source
    assert "# TODO(j2py): replace with your session factory" in router_source
    assert "last_name: str | None = None" in router_source
    assert "request: OwnerRequest" in router_source
    assert "return controller.find_owner(owner_id)" in router_source
    assert (
        "from wiring.owner_controller_wiring import router as owner_controller_router" in app_source
    )
    assert "app.include_router(owner_controller_router)" in app_source
    ast.parse(router_source)
    ast.parse(app_source)


def test_fastapi_target_overwrites_generated_files(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    sidecar = _write_minimal_controller(translated_root)
    output_dir = tmp_path / "wiring"
    target = FastAPITarget(translated_root=translated_root)
    load_result = load_wiring_sidecars(translated_root)
    target.generate(load_result.sidecars, output_dir)
    router = output_dir / "owner_controller_wiring.py"
    router.write_text("stale\n", encoding="utf-8")

    target.generate(load_result.sidecars, output_dir)

    assert router.read_text(encoding="utf-8").startswith(GENERATED_HEADER)
    assert sidecar.exists()


def test_generated_fastapi_wiring_imports_when_translated_modules_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    translated_root = tmp_path / "translated"
    _write_minimal_controller(translated_root)
    _write_fastapi_stubs(tmp_path)
    output_dir = tmp_path / "wiring"
    load_result = load_wiring_sidecars(translated_root)
    FastAPITarget(translated_root=translated_root).generate(load_result.sidecars, output_dir)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.syspath_prepend(str(translated_root))
    for name in [
        "fastapi",
        "sqlalchemy",
        "sqlalchemy.orm",
        "wiring.app_wiring",
        "wiring.owner_controller_wiring",
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    app_wiring = __import__("wiring.app_wiring", fromlist=["register_routes"])
    fastapi = __import__("fastapi")
    app = fastapi.FastAPI()
    app_wiring.register_routes(app)

    assert app.routers


def _write_minimal_controller(translated_root: Path) -> Path:
    translated_root.mkdir(parents=True, exist_ok=True)
    module = translated_root / "owner_controller.py"
    module.write_text(
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
    sidecar = module.with_suffix(".wiring.json")
    sidecar.write_text(json.dumps(_minimal_controller_payload(module)), encoding="utf-8")
    return sidecar


def _minimal_controller_payload(module: Path) -> dict[str, object]:
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


def _write_fastapi_stubs(root: Path) -> None:
    (root / "fastapi.py").write_text(
        "\n".join(
            [
                "class APIRouter:",
                "    def __init__(self, prefix='', tags=None):",
                "        self.prefix = prefix",
                "        self.tags = tags or []",
                "    def get(self, *args, **kwargs):",
                "        return lambda fn: fn",
                "    def post(self, *args, **kwargs):",
                "        return lambda fn: fn",
                "",
                "class FastAPI:",
                "    def __init__(self):",
                "        self.routers = []",
                "    def include_router(self, router):",
                "        self.routers.append(router)",
                "",
                "def Depends(dependency):",
                "    return dependency",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    sqlalchemy = root / "sqlalchemy"
    sqlalchemy.mkdir()
    (sqlalchemy / "__init__.py").write_text("", encoding="utf-8")
    (sqlalchemy / "orm.py").write_text("class Session:\n    pass\n", encoding="utf-8")

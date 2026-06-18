"""Contract tests for the documented Spring wiring metadata profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE = Path("tests/fixtures/framework/spring_wiring_profile_v1.json")

SIDE_CAR_TOP_LEVEL_KEYS = {"schema_version", "source", "output", "elements"}
ELEMENT_KEYS = {
    "plugin",
    "kind",
    "java_name",
    "python_name",
    "annotations",
    "metadata",
}
ALLOWED_ROLES = {
    "controller",
    "service",
    "repository",
    "component",
    "configuration",
    "entity",
}
ALLOWED_PARAMETER_SOURCES = {"path", "query", "body", "unknown"}
ALLOWED_INJECTION_SOURCES = {"constructor", "field", "method"}
ALLOWED_ROUTE_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "REQUEST"}


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def _spring(element: dict[str, Any]) -> dict[str, Any]:
    metadata = element["metadata"]
    assert set(metadata) == {"spring"}
    spring = metadata["spring"]
    assert spring["profile_version"] == 1
    return spring


def _by_java_name(payload: dict[str, Any], java_name: str) -> list[dict[str, Any]]:
    return [element for element in payload["elements"] if element["java_name"] == java_name]


def _derive_python_module(output: str, translated_root: str) -> str:
    relative = Path(output).relative_to(translated_root).with_suffix("")
    module = ".".join(relative.parts)
    return module.removesuffix(".__init__")


def test_spring_profile_fixture_uses_existing_generic_sidecar_shape() -> None:
    payload = _fixture()

    assert set(payload) == SIDE_CAR_TOP_LEVEL_KEYS
    assert payload["schema_version"] == 1
    assert "wiring" not in payload
    assert "python_module" not in payload
    assert "plugin" not in payload
    assert payload["source"].endswith("OwnerController.java")
    assert payload["output"].endswith("owner_controller.py")

    for element in payload["elements"]:
        assert set(element) == ELEMENT_KEYS
        assert element["plugin"] == "spring-wiring"
        assert element["kind"] in {"class", "constructor", "field", "method"}
        assert isinstance(element["annotations"], list)
        _spring(element)


def test_spring_profile_fixture_covers_v1_metadata_families() -> None:
    payload = _fixture()
    spring_objects = [_spring(element) for element in payload["elements"]]

    roles = {spring["role"] for spring in spring_objects if "role" in spring}
    assert {"controller", "repository", "entity"} <= roles <= ALLOWED_ROLES
    assert any("router_prefix" in spring for spring in spring_objects)
    assert any("route" in spring for spring in spring_objects)
    assert any(spring.get("route", {}).get("parameters") for spring in spring_objects)
    assert any(spring.get("route", {}).get("request_body") for spring in spring_objects)
    assert any(spring.get("inject", {}).get("source") == "constructor" for spring in spring_objects)
    assert any(spring.get("inject", {}).get("source") == "field" for spring in spring_objects)
    assert any("entity_type" in spring and "id_type" in spring for spring in spring_objects)
    assert any("table_name" in spring for spring in spring_objects)


def test_spring_profile_route_and_injection_values_are_enumerated() -> None:
    payload = _fixture()

    for element in payload["elements"]:
        spring = _spring(element)
        if "role" in spring:
            assert spring["role"] in ALLOWED_ROLES
        if "route" in spring:
            route = spring["route"]
            assert route["http_method"] in ALLOWED_ROUTE_METHODS
            assert route["handler"] == element["python_name"]
            for parameter in route["parameters"]:
                assert parameter["source"] in ALLOWED_PARAMETER_SOURCES
                assert isinstance(parameter["required"], bool)
            request_body = route["request_body"]
            if request_body is not None:
                assert set(request_body) == {
                    "name",
                    "java_name",
                    "python_type",
                    "required",
                }
                assert isinstance(request_body["required"], bool)
        if "inject" in spring:
            inject = spring["inject"]
            assert inject["source"] in ALLOWED_INJECTION_SOURCES
            assert isinstance(inject["required"], bool)
            assert "qualifier" in inject


def test_spring_profile_keeps_route_composition_in_j2py_wire() -> None:
    payload = _fixture()
    controller = _by_java_name(payload, "OwnerController")[0]
    route = next(
        _spring(element)["route"]
        for element in payload["elements"]
        if element["java_name"] == "findOwner"
    )

    assert _spring(controller)["router_prefix"] == "/owners"
    assert route["path"] == "/{owner_id}"
    assert route["path"] != "/owners/{owner_id}"


def test_spring_profile_module_identity_is_derived_from_output_path() -> None:
    payload = _fixture()

    assert _derive_python_module(payload["output"], "translated") == (
        "com.example.owner_controller"
    )

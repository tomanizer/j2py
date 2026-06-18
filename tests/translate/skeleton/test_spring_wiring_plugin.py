"""Tests for Spring wiring metadata plugin emission."""

from __future__ import annotations

import json
from pathlib import Path

import j2py.pipeline as pipeline
from j2py.config.loader import ConfigLoader
from j2py.framework_plugins.spring import SpringWiringPlugin
from j2py.pipeline import translate_file
from tests.translate.skeleton.helpers import (
    CFG,
    FIXTURES,
    assert_module_executes,
    translate_source_with_diagnostics,
)


def _spring_cfg():
    return CFG.model_copy(
        update={
            "annotation_map_preset": "spring",
            "framework_plugins": [SpringWiringPlugin()],
            "emit_wiring_metadata": True,
        },
    )


def _metadata_by_kind(source: str):
    result = translate_source_with_diagnostics(source, cfg=_spring_cfg())
    return result, {
        (record.kind, record.java_name): record.metadata["spring"]
        for record in result.diagnostics.framework_metadata
    }


def test_python_config_loads_spring_wiring_plugin() -> None:
    cfg = (
        ConfigLoader()
        .add_defaults()
        .add_file(FIXTURES / "framework" / "spring_wiring_plugin_config.py")
        .build()
    )

    assert cfg.annotation_map_preset == "spring"
    assert cfg.emit_wiring_metadata is True
    assert len(cfg.framework_plugins) == 1
    assert isinstance(cfg.framework_plugins[0], SpringWiringPlugin)


def test_controller_class_emits_role_and_router_prefix_metadata() -> None:
    result, metadata = _metadata_by_kind(
        """
        @interface RestController {}
        @interface RequestMapping {
            String value();
        }

        @RestController
        @RequestMapping("/owners")
        public class OwnerController {
        }
        """,
    )

    assert metadata[("class", "OwnerController")] == {
        "profile_version": 1,
        "role": "controller",
        "component_name": "ownerController",
        "router_prefix": "/owners",
    }
    assert "@rest_controller" in result.source
    assert '@request_mapping("/owners")' in result.source
    assert "# @RestController" not in result.source
    assert_module_executes(result.source)


def test_http_method_annotations_emit_route_metadata() -> None:
    _result, metadata = _metadata_by_kind(
        """
        @interface GetMapping { String value(); }
        @interface PostMapping { String value(); }
        @interface PutMapping { String value(); }
        @interface DeleteMapping { String value(); }
        @interface RequestMapping {
            String value();
            RequestMethod method();
        }
        enum RequestMethod { GET }

        public class OwnerController {
            @GetMapping("/{ownerId}")
            public String findOwner() { return "ok"; }

            @PostMapping("")
            public String createOwner() { return "ok"; }

            @PutMapping("/{ownerId}")
            public String updateOwner() { return "ok"; }

            @DeleteMapping("/{ownerId}")
            public void deleteOwner() {}

            @RequestMapping(value = "/search", method = RequestMethod.GET)
            public String searchOwners() { return "ok"; }
        }
        """,
    )

    assert metadata[("method", "findOwner")]["route"]["http_method"] == "GET"
    assert metadata[("method", "findOwner")]["route"]["path"] == "/{owner_id}"
    assert metadata[("method", "createOwner")]["route"]["http_method"] == "POST"
    assert metadata[("method", "createOwner")]["route"]["path"] == ""
    assert metadata[("method", "updateOwner")]["route"]["http_method"] == "PUT"
    assert metadata[("method", "deleteOwner")]["route"]["http_method"] == "DELETE"
    assert metadata[("method", "searchOwners")]["route"]["http_method"] == "GET"
    assert metadata[("method", "searchOwners")]["route"]["path"] == "/search"


def test_route_parameters_request_body_and_response_status_are_metadata() -> None:
    result, metadata = _metadata_by_kind(
        """
        @interface PostMapping { String value(); }
        @interface ResponseStatus { HttpStatus value(); }
        @interface PathVariable { String value(); }
        @interface RequestParam {
            String value();
            boolean required() default true;
        }
        @interface RequestBody {}
        enum HttpStatus { CREATED }
        class Owner {}
        class OwnerForm {}

        public class OwnerController {
            @PostMapping("/{ownerId}")
            @ResponseStatus(HttpStatus.CREATED)
            public Owner createOwner(
                @PathVariable("ownerId") int ownerId,
                @RequestParam(value = "lastName", required = false) String lastName,
                @RequestBody OwnerForm form
            ) {
                return null;
            }
        }
        """,
    )

    route = metadata[("method", "createOwner")]["route"]
    assert route["status_code"] == 201
    assert route["parameters"] == [
        {
            "name": "owner_id",
            "java_name": "ownerId",
            "source": "path",
            "python_type": "int",
            "required": True,
        },
        {
            "name": "last_name",
            "java_name": "lastName",
            "source": "query",
            "python_type": "str",
            "required": False,
        },
    ]
    assert route["request_body"] == {
        "name": "form",
        "java_name": "form",
        "python_type": "OwnerForm",
        "required": True,
    }
    assert "@response_status(201)" in result.source


def test_autowired_field_injection_emits_metadata_and_init_param() -> None:
    result, metadata = _metadata_by_kind(
        """
        @interface Autowired {}
        @interface Qualifier { String value(); }
        interface OwnerService {}

        public class OwnerController {
            @Autowired
            @Qualifier("ownerService")
            private OwnerService ownerService;
        }
        """,
    )

    assert metadata[("field", "ownerService")] == {
        "profile_version": 1,
        "inject": {
            "name": "owner_service",
            "java_name": "ownerService",
            "type": "OwnerService",
            "source": "field",
            "required": True,
            "qualifier": "ownerService",
        },
    }
    assert "def __init__(self, owner_service: OwnerService) -> None:" in result.source
    assert "# @Autowired" in result.source
    assert '# @Qualifier("ownerService")' in result.source


def test_spring_wiring_plugin_writes_real_sidecar_payload(tmp_path: Path) -> None:
    fixture = FIXTURES / "java" / "SpringWiringController.java"
    output = tmp_path / "spring_wiring_controller.py"
    result = translate_file(fixture, cfg=_spring_cfg(), use_llm=False, validate=False)
    result.output_path = output

    sidecar = pipeline.write_wiring_metadata_sidecar(result)

    assert sidecar == output.with_suffix(".wiring.json")
    assert sidecar is not None
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    elements = payload["elements"]
    assert payload["schema_version"] == 1
    assert all(set(element["metadata"]) == {"spring"} for element in elements)

    class_element = next(element for element in elements if element["kind"] == "class")
    assert class_element["plugin"] == "spring-wiring"
    assert class_element["metadata"]["spring"]["role"] == "controller"
    assert class_element["metadata"]["spring"]["router_prefix"] == "/owners"

    field_element = next(element for element in elements if element["kind"] == "field")
    assert field_element["metadata"]["spring"]["inject"]["name"] == "owner_service"
    assert field_element["metadata"]["spring"]["inject"]["qualifier"] == "ownerService"

    route_elements = {
        element["java_name"]: element["metadata"]["spring"]["route"]
        for element in elements
        if element["kind"] == "method"
    }
    assert route_elements["findOwner"]["path"] == "/{owner_id}"
    assert route_elements["findOwner"]["parameters"][0]["source"] == "path"
    assert route_elements["findOwner"]["parameters"][1]["source"] == "query"
    assert route_elements["createOwner"]["status_code"] == 201
    assert route_elements["createOwner"]["request_body"]["python_type"] == "OwnerForm"
    assert route_elements["updateOwner"]["request_body"]["name"] == "form"
    assert route_elements["deleteOwner"]["http_method"] == "DELETE"

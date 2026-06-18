"""Tests for class/field framework annotation visibility (issue #334)."""

from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.translate.skeleton.helpers import (
    CFG,
    FIXTURES,
    assert_module_executes,
    assert_valid_python,
    translate_source_with_diagnostics,
)

ANNOTATION_MAP_CFG = CFG.model_copy(
    update={
        "annotation_map": {
            "RestController": {
                "python_decorator": "mapped_controller",
                "import": "from zfixtures.spring_shim import mapped_controller",
            },
            "Entity": {
                "python_base": "Base",
                "import": "from zfixtures.db_base import Base",
            },
            "Autowired": {
                "field_comment": "# injected: {field_type} {field_name}",
                "emit_init_param": True,
            },
            "Transactional": {
                "python_decorator": "transactional",
                "import": "from zfixtures.db_tx import transactional",
            },
            "GetMapping": {
                "python_decorator": 'router.get("{value}")',
                "import": "from zfixtures.web import router",
            },
        },
    },
)


def test_framework_class_and_field_annotations_emit_comments_and_warnings() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface Service {}
        @interface RestController {}
        @interface Autowired {}
        @interface Entity {}

        interface OrderRepository {}

        @Service
        @RestController
        public class OrderController {
            @Autowired
            private OrderRepository repo;
        }

        @Entity
        public class User {
            private Long id;
        }
        """,
    )

    assert result.coverage == 1.0
    assert result.diagnostics.semantic_warning_count == 4
    assert "# @Service" in result.source
    assert "# @RestController" in result.source
    assert "# @Autowired" in result.source
    assert "# @Entity" in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "stripped framework annotation @Service on class OrderController",
        "stripped framework annotation @RestController on class OrderController",
        "stripped framework annotation @Autowired on field repo",
        "stripped framework annotation @Entity on class User",
    ]
    assert_valid_python(result.source)


def test_emit_line_comments_false_suppresses_annotation_comments() -> None:
    cfg = CFG.model_copy(update={"emit_line_comments": False})
    result = translate_source_with_diagnostics(
        """
        @interface Service {}

        @Service
        public class Worker {
            private String name;
        }
        """,
        cfg=cfg,
    )

    assert result.coverage == 1.0
    assert "# @Service" not in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "stripped framework annotation @Service on class Worker",
    ]
    assert_valid_python(result.source)


def test_drop_annotations_keep_dropped_reason() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Annotated {
            @Override
            public String toString() {
                return "x";
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "dropped annotation @Override",
    ]
    assert_valid_python(result.source)


def test_unknown_annotation_keeps_unsupported_reason() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface Custom {}

        public class Annotated {
            @Custom
            public String name() {
                return "x";
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "unsupported annotation @Custom",
    ]
    assert_valid_python(result.source)


def test_multiline_annotation_emits_commented_lines() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Annotated {
            @SuppressWarnings({
                "unchecked",
                "rawtypes"
            })
            private String value;
        }
        """,
    )

    assert result.coverage == 1.0
    assert "# @SuppressWarnings({" in result.source
    assert '# "unchecked",' in result.source
    assert '# "rawtypes"' in result.source
    assert "# })" in result.source
    assert_valid_python(result.source)


def test_nested_empty_annotated_class_emits_pass() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Outer {
            @SuppressWarnings("serial")
            private static class EarlyExitException extends RuntimeException {
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "class EarlyExitException(RuntimeException):" in result.source
    assert "    pass" in result.source
    assert_valid_python(result.source)


def test_method_framework_annotation_uses_stripped_reason() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface Transactional {}

        public class Orders {
            @Transactional
            public void process() {
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "# @Transactional" in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "stripped framework annotation @Transactional on method process",
    ]
    assert_valid_python(result.source)


def test_transactional_fixture_preserves_method_and_class_level_metadata() -> None:
    parsed = parse_file(FIXTURES / "java" / "SpringTransactional.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert result.source == (FIXTURES / "python" / "SpringTransactional.py").read_text()
    assert not result.diagnostics.unhandled
    assert "# @Transactional(readOnly=True)" in result.source
    assert "# read-only transaction" in result.source
    assert "# @Transactional(rollbackFor=AuditException)" in result.source
    assert "# rollbackFor=AuditException" in result.source
    assert result.source.index("# @Transactional(readOnly=True)") < result.source.index(
        "def find_owner",
    )
    assert "# @Transactional(readOnly=True)\n    def package_private_helper" not in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "stripped framework annotation @Transactional on class OwnerService",
        "stripped framework annotation @Transactional on method save_owner",
    ]
    assert_valid_python(result.source)


def test_transactional_comments_respect_disabled_line_comments() -> None:
    cfg = CFG.model_copy(update={"emit_line_comments": False})
    result = translate_source_with_diagnostics(
        """
        @interface Transactional {}

        @Transactional(readOnly = true)
        public class Service {
            public void run() {
            }
        }
        """,
        cfg=cfg,
    )

    assert result.coverage == 1.0
    assert "# @Transactional" not in result.source
    assert "# read-only transaction" not in result.source
    assert_valid_python(result.source)


def test_class_transactional_does_not_propagate_to_override_methods() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface Override {}
        @interface Transactional {}

        @Transactional
        public class Service {
            @Override
            public void run() {
            }

            public void save() {
            }
        }
        """
    )

    assert result.coverage == 1.0
    assert "    # @Override\n    def run(self) -> None:" in result.source
    assert "    # @Transactional\n    # @Override\n    def run" not in result.source
    assert "    # @Transactional\n    def save(self) -> None:" in result.source
    assert_valid_python(result.source)


def test_transactional_comments_skip_empty_rollback_for() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface Transactional {
            Class<?>[] rollbackFor() default {};
        }

        public class Service {
            @Transactional(rollbackFor = {})
            public void save() {
            }
        }
        """
    )

    assert result.coverage == 1.0
    assert "# @Transactional" in result.source
    assert "rollbackFor=" not in result.source
    assert_valid_python(result.source)


def test_annotation_map_fixture_lowers_framework_annotations() -> None:
    parsed = parse_file(FIXTURES / "java" / "AnnotationMapFrameworkLowering.java")
    result = translate_skeleton_with_diagnostics(
        parsed,
        extract_symbols(parsed),
        ANNOTATION_MAP_CFG,
    )

    assert result.coverage == 1.0
    assert result.source == (FIXTURES / "python" / "AnnotationMapFrameworkLowering.py").read_text()
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "mapped annotation @RestController -> @mapped_controller on class OrderController",
        "mapped annotation @Entity -> base Base on class OrderController",
        "mapped annotation @Autowired -> field comment, constructor parameter on field repo",
        "mapped annotation @Transactional -> @transactional on method get",
        'mapped annotation @GetMapping -> @router.get("{value}") on method get',
    ]
    assert_valid_python(result.source)


def test_spring_annotation_map_preset_fixture_lowers_rest_controller_get_mapping(
    tmp_path: Path,
) -> None:
    pytest.importorskip("yaml")
    config_file = tmp_path / "j2py.yaml"
    config_file.write_text("annotation_map_preset: spring\n")
    cfg = ConfigLoader().add_defaults().add_file(config_file).build()
    parsed = parse_file(FIXTURES / "java" / "SpringAnnotationPreset.java")

    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), cfg)

    assert result.coverage == 1.0
    assert result.source == (FIXTURES / "python" / "SpringAnnotationPreset.py").read_text()
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "mapped annotation @RestController -> @rest_controller on class SpringAnnotationPreset",
        'mapped annotation @GetMapping -> @get_mapping("{value}") on method hello',
    ]
    assert_module_executes(result.source)


def test_request_body_pojo_promotes_to_pydantic_model_fixture() -> None:
    parsed = parse_file(FIXTURES / "java" / "RequestBodyPydanticModel.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.source == (FIXTURES / "python" / "RequestBodyPydanticModel.py").read_text()
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "__init__" not in result.source
    assert "def get_first_name" not in result.source
    assert "def set_first_name" not in result.source
    assert_valid_python(result.source)


def test_generic_request_body_parameter_promotes_contained_model() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;
        import org.springframework.web.bind.annotation.PostMapping;
        import org.springframework.web.bind.annotation.RequestBody;

        class OwnerController {
            @PostMapping("/owners")
            public void createOwners(@RequestBody List<OwnerRequest> forms) {}
        }

        class OwnerRequest {
            private String firstName;

            public String getFirstName() { return firstName; }
        }
        """,
    )

    assert "from pydantic import BaseModel" in result.source
    assert "forms: list[OwnerRequest]" in result.source
    assert "class OwnerRequest(BaseModel):" in result.source
    assert "first_name: str | None = None" in result.source
    assert "def get_first_name" not in result.source
    assert_valid_python(result.source)


def test_mapping_return_type_promotes_response_body_model() -> None:
    result = translate_source_with_diagnostics(
        """
        import org.springframework.http.ResponseEntity;
        import org.springframework.web.bind.annotation.GetMapping;

        class OwnerController {
            @GetMapping("/owners/1")
            public ResponseEntity<OwnerResponse> getOwner() {
                return null;
            }
        }

        class OwnerResponse {
            private String firstName;

            public String getFirstName() { return firstName; }
        }
        """,
    )

    assert "from pydantic import BaseModel" in result.source
    assert "def get_owner(self) -> ResponseEntity[OwnerResponse]:" in result.source
    assert "class OwnerResponse(BaseModel):" in result.source
    assert "first_name: str | None = None" in result.source
    assert "def get_first_name" not in result.source
    assert_valid_python(result.source)


def test_jackson_model_annotation_promotes_to_pydantic_model() -> None:
    result = translate_source_with_diagnostics(
        """
        import com.fasterxml.jackson.databind.annotation.JsonSerialize;

        @JsonSerialize
        class OwnerJson {
            private String firstName;
        }
        """,
    )

    assert "from pydantic import BaseModel" in result.source
    assert "# @JsonSerialize" in result.source
    assert "class OwnerJson(BaseModel):" in result.source
    assert "first_name: str | None = None" in result.source
    assert_valid_python(result.source)


def test_spring_annotation_map_preset_lowers_parameter_and_status_annotations(
    tmp_path: Path,
) -> None:
    pytest.importorskip("yaml")
    config_file = tmp_path / "j2py.yaml"
    config_file.write_text("annotation_map_preset: spring\n")
    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    result = translate_source_with_diagnostics(
        """
        @RestController
        public class Pets {
            @ResponseStatus(HttpStatus.CREATED)
            @PostMapping("/pets")
            public Pet create(@RequestBody Pet pet, @RequestParam("trace") String trace) {
                return pet;
            }
        }
        """,
        cfg=cfg,
    )

    assert "@response_status(201)" in result.source
    assert '@post_mapping("/pets")' in result.source
    assert "from typing import Annotated" in result.source
    assert "pet: Annotated[Pet, request_body]" in result.source
    assert "trace: Annotated[str, request_param]" in result.source
    assert_module_executes(result.source)


def test_spring_annotation_map_preset_handles_request_mapping_aliases(
    tmp_path: Path,
) -> None:
    pytest.importorskip("yaml")
    config_file = tmp_path / "j2py.yaml"
    config_file.write_text("annotation_map_preset: spring\n")
    cfg = ConfigLoader().add_defaults().add_file(config_file).build()

    result = translate_source_with_diagnostics(
        """
        @Controller
        public class Routes {
            @RequestMapping(path="/owners", method=GET)
            public String owners() {
                return "owners";
            }

            @RequestMapping("/pets")
            public String pets() {
                return "pets";
            }

            @ResponseStatus(code=CREATED)
            @PostMapping({ "/pets" })
            public String create() {
                return "ok";
            }
        }
        """,
        cfg=cfg,
    )

    assert '@request_mapping("/owners", method="GET")' in result.source
    assert '@request_mapping("/pets")' in result.source
    assert 'method="{method}"' not in result.source
    assert "@response_status(201)" in result.source
    assert '@post_mapping("/pets")' in result.source
    assert_module_executes(result.source)


def test_annotation_map_python_base_dedupes_explicit_extends_base() -> None:
    cfg = CFG.model_copy(update={"annotation_map": {"Entity": {"python_base": "Base"}}})
    result = translate_source_with_diagnostics(
        """
        class Base {}

        @Entity
        class User extends Base {
        }
        """,
        cfg=cfg,
    )

    assert "class User(Base):" in result.source
    assert "class User(Base, Base):" not in result.source
    assert_module_executes(result.source)


def test_annotation_map_can_suppress_mapped_audit_comment() -> None:
    cfg = CFG.model_copy(
        update={
            "annotation_map": {
                "Service": {
                    "python_decorator": "service",
                    "preserve_comment": False,
                },
            },
        },
    )
    result = translate_source_with_diagnostics(
        """
        @Service
        public class Worker {
        }
        """,
        cfg=cfg,
    )

    assert "@service" in result.source
    assert "# @Service" not in result.source
    assert_valid_python(result.source)


def test_annotation_map_drop_uses_dropped_reason() -> None:
    cfg = CFG.model_copy(
        update={
            "annotation_map": {
                "Service": {
                    "drop": True,
                },
            },
        },
    )
    result = translate_source_with_diagnostics(
        """
        @Service
        public class Worker {
        }
        """,
        cfg=cfg,
    )

    assert "@service" not in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "dropped annotation @Service",
    ]
    assert_valid_python(result.source)

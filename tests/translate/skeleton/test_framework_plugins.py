"""Tests for Tier 4 framework plugin dispatch."""

from pathlib import Path

from j2py.config.loader import ConfigLoader
from tests.fixtures.framework.reference_plugin import (
    CircularMetadataFrameworkPlugin,
    EmptyMetadataFrameworkPlugin,
    InvalidMetadataFrameworkPlugin,
    MultipleInitParamsFrameworkPlugin,
    RawStringFrameworkPlugin,
    ReferenceFrameworkPlugin,
    ThrowingFrameworkPlugin,
)
from tests.translate.skeleton.helpers import (
    CFG,
    assert_module_executes,
    assert_valid_python,
    translate_source_with_diagnostics,
)


def _reference_cfg():
    return CFG.model_copy(update={"framework_plugins": [ReferenceFrameworkPlugin()]})


def test_python_config_loads_framework_plugin() -> None:
    cfg = (
        ConfigLoader()
        .add_defaults()
        .add_file(Path("tests/fixtures/framework/reference_plugin_config.py"))
        .build()
    )

    assert len(cfg.framework_plugins) == 1
    assert isinstance(cfg.framework_plugins[0], ReferenceFrameworkPlugin)


def test_reference_plugin_injects_class_decorator_and_base() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
        cfg=_reference_cfg(),
    )

    assert "@mapped_controller" in result.source
    assert "class Orders(MappedControllerBase):" in result.source
    assert "# @MappedController" not in result.source
    assert "from tests.fixtures.framework.shims import MappedControllerBase" in result.source
    assert any(
        diagnostic.reason == "framework plugin 'reference' handled class Orders"
        for diagnostic in result.diagnostics.handled
    )
    assert_module_executes(result.source)


def test_reference_plugin_promotes_field_to_init_param_and_dedupes() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface InjectDep {}
        interface OrderService {}

        public class Orders {
            @InjectDep
            private OrderService service;
            @InjectDep
            private OrderService service;
        }
        """,
        cfg=_reference_cfg(),
    )

    assert "def __init__(self, service: OrderService) -> None:" in result.source
    assert result.source.count("def __init__(self, service: OrderService) -> None:") == 1
    assert "self.service: OrderService = service" in result.source
    assert "# injected by reference plugin: OrderService service" in result.source
    assert "# @InjectDep" not in result.source
    assert_valid_python(result.source)


def test_reference_plugin_injects_method_decorator() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface MappedRoute {
            String value();
        }

        public class Orders {
            @MappedRoute("/orders")
            public String listOrders() {
                return "ok";
            }
        }
        """,
        cfg=_reference_cfg(),
    )

    assert '@mapped_route("/orders")' in result.source
    assert "# @MappedRoute" not in result.source
    assert "from tests.fixtures.framework.shims import mapped_route" in result.source
    assert_module_executes(result.source)


def test_reference_plugin_records_wiring_metadata() -> None:
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}
        @interface InjectDep {}
        @interface MappedRoute {
            String value();
        }
        interface OrderService {}

        @MappedController
        public class Orders {
            @InjectDep
            private OrderService service;

            @MappedRoute("/orders")
            public String listOrders() {
                return "ok";
            }
        }
        """,
        cfg=_reference_cfg(),
    )

    records = result.diagnostics.framework_metadata
    assert [
        (record.plugin, record.kind, record.java_name, record.python_name) for record in records
    ] == [
        ("reference", "class", "Orders", "Orders"),
        ("reference", "field", "service", "service"),
        ("reference", "method", "listOrders", "list_orders"),
    ]
    assert records[0].metadata == {"controller": "Orders"}
    assert records[1].metadata == {"inject": {"field": "service", "python_type": "OrderService"}}
    assert records[2].metadata == {"route": {"path": "/orders", "handler": "list_orders"}}
    assert [annotation.simple_name for annotation in records[0].annotations] == [
        "MappedController",
    ]


def test_empty_metadata_plugin_does_not_create_wiring_record() -> None:
    cfg = CFG.model_copy(update={"framework_plugins": [EmptyMetadataFrameworkPlugin()]})
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
        cfg=cfg,
    )

    assert "# handled without metadata" in result.source
    assert result.diagnostics.framework_metadata == []


def test_invalid_metadata_plugin_warns_and_skips_wiring_record() -> None:
    cfg = CFG.model_copy(update={"framework_plugins": [InvalidMetadataFrameworkPlugin()]})
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
        cfg=cfg,
    )

    assert "# handled with invalid metadata" in result.source
    assert result.diagnostics.framework_metadata == []
    assert any(
        "framework plugin 'invalid-metadata' returned non-JSON-serializable metadata"
        in warning.reason
        for warning in result.diagnostics.warnings
    )


def test_circular_metadata_plugin_warns_and_skips_wiring_record() -> None:
    cfg = CFG.model_copy(update={"framework_plugins": [CircularMetadataFrameworkPlugin()]})
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
        cfg=cfg,
    )

    assert "# handled with circular metadata" in result.source
    assert result.diagnostics.framework_metadata == []
    assert any(
        "framework plugin 'circular-metadata' returned non-JSON-serializable metadata"
        in warning.reason
        and "Circular reference detected" in warning.reason
        for warning in result.diagnostics.warnings
    )


def test_raw_string_plugin_result_warns_and_falls_through_to_tier_one() -> None:
    cfg = CFG.model_copy(update={"framework_plugins": [RawStringFrameworkPlugin()]})
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
        cfg=cfg,
    )

    assert "@bad_decorator" not in result.source
    assert "# @MappedController" in result.source
    assert any(
        "framework plugin 'raw-string' returned a raw string instead of a tuple of strings"
        in warning.reason
        for warning in result.diagnostics.warnings
    )


def test_multiple_field_init_params_warns_about_assignment_limit() -> None:
    cfg = CFG.model_copy(update={"framework_plugins": [MultipleInitParamsFrameworkPlugin()]})
    result = translate_source_with_diagnostics(
        """
        @interface InjectDep {}
        interface OrderService {}

        public class Orders {
            @InjectDep
            private OrderService service;
        }
        """,
        cfg=cfg,
    )

    assert "def __init__(self, service: OrderService, service_extra: OrderService) -> None:" in (
        result.source
    )
    assert "self.service: OrderService = service" in result.source
    assert "service_extra" not in result.source.split("self.service: OrderService = service", 1)[1]
    assert any(
        "framework plugin returned multiple init_params for field service" in warning.reason
        for warning in result.diagnostics.warnings
    )


def test_plugin_precedence_suppresses_tier_two_mapping() -> None:
    cfg = CFG.model_copy(
        update={
            "framework_plugins": [ReferenceFrameworkPlugin()],
            "annotation_map": {
                "MappedController": {
                    "python_decorator": "tier_two_controller",
                    "python_base": "TierTwoBase",
                },
            },
        },
    )
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
        cfg=cfg,
    )

    assert "@mapped_controller" in result.source
    assert "tier_two_controller" not in result.source
    assert "TierTwoBase" not in result.source
    assert "class Orders(MappedControllerBase):" in result.source


def test_throwing_plugin_warns_and_falls_through_to_tier_two() -> None:
    cfg = CFG.model_copy(
        update={
            "framework_plugins": [ThrowingFrameworkPlugin()],
            "annotation_map": {
                "MappedController": {
                    "python_decorator": "tier_two_controller",
                    "preserve_comment": False,
                },
            },
        },
    )
    result = translate_source_with_diagnostics(
        """
        @interface MappedController {}

        @MappedController
        public class Orders {
        }
        """,
        cfg=cfg,
    )

    assert "@tier_two_controller" in result.source
    assert "# @MappedController" not in result.source
    assert [
        warning.reason
        for warning in result.diagnostics.warnings
        if "framework plugin 'throwing' raised" in warning.reason
    ] == [
        "framework plugin 'throwing' raised in transform_class: RuntimeError('boom')",
    ]
    assert_valid_python(result.source)

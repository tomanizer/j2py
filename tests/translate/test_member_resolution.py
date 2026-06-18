"""Tests for shared Java member/type-shape resolution helpers."""

from j2py.config.loader import MemberMapEntry
from j2py.parse.java_ast import parse_source
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.expr_static_calls import translate_static_imported_method
from j2py.translate.expr_types import infer_expression_py_type
from j2py.translate.member_resolution import (
    configured_member_binding,
    java_type_shape,
    java_type_shape_of_value,
    java_type_shape_signature,
    resolve_unqualified_member,
    static_import_binding,
    static_import_field_fallback,
    static_import_method_fallback,
    wildcard_static_import_binding,
)
from j2py.translate.name_resolution import FileNameBindings, NameResolver, TypeBinding
from tests.translate.skeleton.helpers import CFG, translate_source_with_diagnostics


def test_static_import_binding_preserves_owner_member_and_python_fallbacks() -> None:
    binding = static_import_binding("com.example.Helpers.magicValue", CFG, kind="unknown")

    assert binding.owner == "com.example.Helpers"
    assert binding.member == "magicValue"
    assert binding.kind == "unknown"
    assert binding.source == "explicit_static_import"
    assert binding.python_owner == "Helpers"
    assert binding.python_member == "magic_value"
    assert static_import_method_fallback(binding, ["value"], CFG) == "Helpers.magic_value(value)"
    assert static_import_field_fallback(binding, CFG) == "Helpers.magic_value"


def test_static_import_call_lowering_prefers_member_binding_over_raw_import() -> None:
    parsed = parse_source(
        """
        public class Calls {
            public int call(int value) {
                return magicValue(value);
            }
        }
        """,
    )
    invocation = next(parsed.root.find_all("method_invocation"))
    args_node = invocation.child_by_field("arguments")
    assert args_node is not None
    binding = static_import_binding("com.example.Helpers.magicValue", CFG, kind="method")

    translated = translate_static_imported_method(
        invocation,
        imported_name="java.lang.Math.sqrt",
        binding=binding,
        arg_nodes=list(args_node.named_children),
        args=["value"],
        ctx=TranslationContext(cfg=CFG, diagnostics=TranslationDiagnostics()),
    )

    assert translated == "Helpers.magic_value(value)"


def test_java_type_shape_preserves_collection_type_arguments_before_erasure() -> None:
    shape = java_type_shape("java.util.List<String>", CFG)

    assert shape.raw == "java.util.List<String>"
    assert shape.simple == "List"
    assert shape.category == "collection"
    assert shape.python_erasure == "list"
    assert [arg.simple for arg in shape.type_args] == ["String"]


def test_java_type_shape_signature_distinguishes_generic_inputs_before_erasure() -> None:
    signature = java_type_shape_signature(
        ["List<String>", "List<Integer>", "Map<String, Integer>", "char"],
        CFG,
    )

    assert signature == (
        "collection:List->list[string:String->str]",
        "collection:List->list[numeric:Integer->int]",
        "map:Map->dict[string:String->str,numeric:Integer->int]",
        "string:char->str",
    )


def test_java_type_shape_keeps_numeric_widths_visible_despite_python_erasure() -> None:
    signature = java_type_shape_signature(["int", "long"], CFG)

    assert signature == ("numeric:int->int", "numeric:long->int")


def test_java_type_shape_classifies_configured_dict_collection_as_map() -> None:
    cfg = CFG.model_copy(update={"collection_map": {**CFG.collection_map, "Attributes": "dict"}})

    shape = java_type_shape("Attributes<String, String>", cfg)

    assert shape.category == "map"


def test_java_type_shape_classifies_configured_non_dict_collection() -> None:
    cfg = CFG.model_copy(update={"collection_map": {**CFG.collection_map, "VectorList": "list"}})

    shape = java_type_shape("VectorList<String>", cfg)

    assert shape.category == "collection"
    assert shape.python_erasure == "list"


def test_java_type_shape_classifies_map_suffix_as_map() -> None:
    shape = java_type_shape("ImmutableMultimap<String, Integer>", CFG)

    assert shape.category == "map"


def test_configured_member_binding_uses_project_member_map() -> None:
    cfg = CFG.model_copy(
        update={
            "member_map": {
                "com.example.Util.max": MemberMapEntry(
                    kind="method",
                    python_owner="Util",
                    python_member="max_value",
                    return_type="int",
                ),
            },
        },
    )

    binding = configured_member_binding("com.example.Util.max", cfg)

    assert binding is not None
    assert binding.owner == "com.example.Util"
    assert binding.member == "max"
    assert binding.python_owner == "Util"
    assert binding.python_member == "max_value"
    assert binding.return_type == "int"


def test_resolve_unqualified_member_binds_same_class_instance_and_static() -> None:
    instance_ctx = TranslationContext(
        cfg=CFG,
        diagnostics=TranslationDiagnostics(),
        class_methods={"value"},
        class_method_return_types={"value": "int"},
        containing_class_name="Counter",
        in_instance_method=True,
    )
    static_ctx = TranslationContext(
        cfg=CFG,
        diagnostics=TranslationDiagnostics(),
        class_static_methods={"value"},
        class_method_return_types={"value": "int"},
        containing_class_name="Counter",
    )

    instance = resolve_unqualified_member("value", instance_ctx)
    static = resolve_unqualified_member("value", static_ctx)

    assert instance is not None
    assert instance.source == "same_class"
    assert instance.python_owner == "self"
    assert static is not None
    assert static.source == "same_class"
    assert static.python_owner == "Counter"


def test_wildcard_static_import_binding_uses_local_member_facts() -> None:
    ctx = TranslationContext(
        cfg=CFG,
        diagnostics=TranslationDiagnostics(),
        declared_type_method_return_types={"Numbers": {"max": "int"}},
        declared_type_java_fields={"Numbers": {"LIMIT": "int"}},
    )

    method = wildcard_static_import_binding("example.Numbers", "max", ctx, kind="method")
    field = wildcard_static_import_binding("example.Numbers", "LIMIT", ctx, kind="field")

    assert method is not None
    assert method.source == "wildcard_static_import"
    assert method.python_owner == "Numbers"
    assert method.python_member == "max_"
    assert field is not None
    assert static_import_field_fallback(field, CFG) == "Numbers.LIMIT"


def test_java_type_shape_of_value_uses_declared_java_types() -> None:
    parsed = parse_source(
        """
        class Values {
            String run(java.util.List<String> values) {
                return values.get(0);
            }
        }
        """,
    )
    identifier = next(node for node in parsed.root.find_all("identifier") if node.text == "values")
    ctx = TranslationContext(
        cfg=CFG,
        diagnostics=TranslationDiagnostics(),
        variable_java_types={"values": "java.util.List<String>"},
    )

    shape = java_type_shape_of_value(identifier, ctx)

    assert shape is not None
    assert shape.category == "collection"
    assert shape.type_args[0].simple == "String"


def test_java_type_shape_of_value_uses_constructor_result_type() -> None:
    parsed = parse_source(
        """
        class Values {
            Object run() {
                return new java.util.ArrayList<String>();
            }
        }
        """,
    )
    creation = next(parsed.root.find_all("object_creation_expression"))
    ctx = TranslationContext(cfg=CFG, diagnostics=TranslationDiagnostics())

    shape = java_type_shape_of_value(creation, ctx)

    assert shape is not None
    assert shape.simple == "ArrayList"
    assert shape.category == "collection"
    assert shape.type_args[0].simple == "String"


def test_wildcard_static_import_from_local_class_lowers_method_and_field() -> None:
    result = translate_source_with_diagnostics(
        """
        package example;
        import static example.Numbers.*;

        class Numbers {
            static int LIMIT = 10;
            static int max(int left, int right) {
                return left > right ? left : right;
            }
        }

        class UseNumbers {
            int run() {
                return max(1, LIMIT);
            }
        }
        """,
    )

    assert "return Numbers.max_(1, Numbers.LIMIT)" in result.source
    assert not result.diagnostics.unhandled


def test_same_class_unqualified_members_route_through_class_or_self() -> None:
    result = translate_source_with_diagnostics(
        """
        class Counter {
            static int LIMIT = 10;

            int value() {
                return 1;
            }

            int runInstance() {
                return value();
            }

            static int staticValue() {
                return LIMIT;
            }

            static int runStatic() {
                return staticValue();
            }
        }
        """,
    )

    assert "return self.value()" in result.source
    assert "return Counter.static_value()" in result.source
    assert "return Counter.LIMIT" in result.source
    assert not result.diagnostics.unhandled


def test_unknown_external_wildcard_static_import_warns_without_unhandled_import() -> None:
    result = translate_source_with_diagnostics(
        """
        import static com.external.Helpers.*;

        class UseHelpers {
            int run() {
                return helper(1);
            }
        }
        """,
    )

    assert "return helper(1)" in result.source
    assert not result.diagnostics.unhandled
    assert any(
        warning.category == "wildcard_static_import_unresolved"
        and warning.facts["owner"] == "com.external.Helpers"
        for warning in result.diagnostics.warnings
    )
    assert any(
        warning.category == "wildcard_static_import_unresolved"
        and warning.facts.get("member") == "helper"
        for warning in result.diagnostics.warnings
    )


def test_configured_static_method_import_lowers_through_member_map() -> None:
    cfg = CFG.model_copy(
        update={
            "member_map": {
                "com.example.Util.max": MemberMapEntry(
                    kind="method",
                    python_owner="Util",
                    python_member="max_value",
                    return_type="int",
                ),
            },
        },
    )
    result = translate_source_with_diagnostics(
        """
        import static com.example.Util.max;

        class UseUtil {
            int run() {
                return max(1, 2);
            }
        }
        """,
        cfg=cfg,
    )

    assert "return Util.max_value(1, 2)" in result.source
    assert not result.diagnostics.unhandled


def test_configured_qualified_static_call_resolves_imported_simple_receiver() -> None:
    cfg = CFG.model_copy(
        update={
            "member_map": {
                "com.example.Util.max": MemberMapEntry(
                    kind="method",
                    python_owner="Util",
                    python_member="max_value",
                    return_type="int",
                ),
            },
        },
    )
    result = translate_source_with_diagnostics(
        """
        import com.example.Util;

        class UseUtil {
            int run() {
                return Util.max(1, 2);
            }
        }
        """,
        cfg=cfg,
    )

    assert "return Util.max_value(1, 2)" in result.source
    assert not result.diagnostics.unhandled


def test_configured_return_shape_resolves_imported_simple_receiver() -> None:
    cfg = CFG.model_copy(
        update={
            "member_map": {
                "com.example.Util.make": MemberMapEntry(
                    kind="method",
                    return_shape="object:Thing->Thing",
                ),
            },
        },
    )
    parsed = parse_source(
        """
        import com.example.Util;

        class UseUtil {
            Object run() {
                return Util.make();
            }
        }
        """,
    )
    invocation = next(parsed.root.find_all("method_invocation"))
    ctx = TranslationContext(
        cfg=cfg,
        diagnostics=TranslationDiagnostics(),
        name_resolver=NameResolver(
            FileNameBindings(
                imported_types={
                    "Util": TypeBinding(
                        raw_name="Util",
                        python_name="Util",
                        import_line="from com.example.Util import Util",
                    ),
                },
            ),
        ),
    )

    assert infer_expression_py_type(invocation, ctx) == "Thing"


def test_configured_return_shape_accepts_simple_shape_without_category_prefix() -> None:
    cfg = CFG.model_copy(
        update={
            "member_map": {
                "Util.make": MemberMapEntry(
                    kind="method",
                    return_shape="Thing->Thing",
                ),
            },
        },
    )
    parsed = parse_source(
        """
        class UseUtil {
            Object run() {
                return Util.make();
            }
        }
        """,
    )
    invocation = next(parsed.root.find_all("method_invocation"))
    ctx = TranslationContext(cfg=cfg, diagnostics=TranslationDiagnostics())

    assert infer_expression_py_type(invocation, ctx) == "Thing"

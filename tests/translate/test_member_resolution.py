"""Tests for shared Java member/type-shape resolution helpers."""

from j2py.parse.java_ast import parse_source
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.expr_static_calls import translate_static_imported_method
from j2py.translate.member_resolution import (
    java_type_shape,
    java_type_shape_signature,
    static_import_binding,
    static_import_field_fallback,
    static_import_method_fallback,
)
from tests.translate.skeleton.helpers import CFG


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

"""Direct tests for deterministic Java name binding."""

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_source
from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
from j2py.translate.name_resolution import (
    FileNameBindings,
    NameResolver,
    NameScope,
    TypeBinding,
    build_file_name_bindings,
    scope_from_context,
)
from tests.translate.skeleton.helpers import CFG


def resolve(
    raw_name: str,
    *,
    bindings: FileNameBindings | None = None,
    scope: NameScope | None = None,
):
    resolver = NameResolver(bindings or FileNameBindings())
    return resolver.resolve_identifier(raw_name, scope or NameScope())


def test_expression_alias_takes_precedence_over_parameter_and_local() -> None:
    resolved = resolve(
        "item",
        scope=NameScope(
            expression_aliases={"item": "_j2py_item"},
            param_names={"item"},
            local_names={"item"},
        ),
    )

    assert resolved.kind == "expression_alias"
    assert resolved.python_name == "_j2py_item"
    assert resolved.import_line is None


def test_static_field_alias_takes_precedence_over_parameter_and_local() -> None:
    resolved = resolve(
        "PI",
        bindings=FileNameBindings(static_field_aliases={"PI": "math.pi"}),
        scope=NameScope(param_names={"PI"}, local_names={"PI"}),
    )

    assert resolved.kind == "static_field_alias"
    assert resolved.python_name == "math.pi"
    assert resolved.is_static_value


def test_scope_static_field_alias_can_supply_current_binding() -> None:
    resolved = resolve(
        "PI",
        scope=NameScope(static_field_aliases={"PI": "math.pi"}),
    )

    assert resolved.kind == "static_field_alias"
    assert resolved.python_name == "math.pi"


def test_parameter_shadows_imported_type() -> None:
    resolved = resolve(
        "ExternalThing",
        bindings=FileNameBindings(
            imported_types={
                "ExternalThing": TypeBinding(
                    raw_name="ExternalThing",
                    python_name="ExternalThing",
                    import_line="from com.example.ExternalThing import ExternalThing",
                ),
            },
        ),
        scope=NameScope(param_names={"ExternalThing"}),
    )

    assert resolved.kind == "parameter"
    assert resolved.python_name == "external_thing"
    assert resolved.import_line is None
    assert not resolved.is_type_reference


def test_local_shadows_same_package_type_fallback() -> None:
    resolved = resolve(
        "Peer",
        bindings=FileNameBindings(package_name="com.example"),
        scope=NameScope(local_names={"Peer"}),
    )

    assert resolved.kind == "local"
    assert resolved.python_name == "peer"
    assert resolved.import_line is None


def test_instance_field_shadows_imported_type() -> None:
    resolved = resolve(
        "ExternalThing",
        bindings=FileNameBindings(
            imported_types={
                "ExternalThing": TypeBinding(
                    raw_name="ExternalThing",
                    python_name="ExternalThing",
                    import_line="from com.example.ExternalThing import ExternalThing",
                ),
            },
        ),
        scope=NameScope(
            class_fields={"ExternalThing"},
            class_field_types={"ExternalThing": "object"},
            in_instance_method=True,
        ),
    )

    assert resolved.kind == "field"
    assert resolved.python_name == "self.external_thing"
    assert resolved.import_line is None


def test_static_context_field_uses_field_name_without_self() -> None:
    resolved = resolve(
        "VALUES",
        scope=NameScope(
            class_fields={"VALUES"},
            class_field_types={"VALUES": "list[str]"},
            in_instance_method=False,
        ),
    )

    assert resolved.kind == "field"
    assert resolved.python_name == "values"
    assert resolved.import_line is None


def test_explicit_imported_type_returns_binding_and_import_request() -> None:
    resolved = resolve(
        "ExternalThing",
        bindings=FileNameBindings(
            imported_types={
                "ExternalThing": TypeBinding(
                    raw_name="ExternalThing",
                    python_name="ExternalThing",
                    import_line="from com.example.ExternalThing import ExternalThing",
                ),
            },
        ),
    )

    assert resolved.kind == "imported_type"
    assert resolved.python_name == "ExternalThing"
    assert resolved.import_line == "from com.example.ExternalThing import ExternalThing"
    assert resolved.is_type_reference


def test_import_map_type_binding_uses_mapped_python_name_without_import_request() -> None:
    resolved = resolve(
        "ExternalThing",
        bindings=FileNameBindings(
            imported_types={
                "ExternalThing": TypeBinding(
                    raw_name="ExternalThing",
                    python_name="Thing",
                    source="import_map",
                ),
            },
        ),
    )

    assert resolved.kind == "imported_type"
    assert resolved.python_name == "Thing"
    assert resolved.import_line is None
    assert resolved.reason == "import_map type binding"


def test_dropped_import_type_binding_keeps_class_name_without_import_request() -> None:
    resolved = resolve(
        "Dropped",
        bindings=FileNameBindings(
            imported_types={
                "Dropped": TypeBinding(
                    raw_name="Dropped",
                    python_name="Dropped",
                    source="drop_import",
                ),
            },
        ),
    )

    assert resolved.kind == "imported_type"
    assert resolved.python_name == "Dropped"
    assert resolved.import_line is None
    assert resolved.reason == "drop_import type binding"


def test_containing_type_is_preserved_without_import_request() -> None:
    resolved = resolve(
        "Outer",
        bindings=FileNameBindings(package_name="com.example"),
        scope=NameScope(containing_class_name="Outer"),
    )

    assert resolved.kind == "containing_type"
    assert resolved.python_name == "Outer"
    assert resolved.import_line is None
    assert resolved.is_type_reference


def test_nested_type_is_preserved_without_import_request() -> None:
    resolved = resolve(
        "Inner",
        bindings=FileNameBindings(package_name="com.example"),
        scope=NameScope(nested_class_names={"Inner"}),
    )

    assert resolved.kind == "nested_type"
    assert resolved.python_name == "Inner"
    assert resolved.import_line is None
    assert resolved.is_type_reference


def test_same_package_type_fallback_requests_peer_import() -> None:
    resolved = resolve(
        "Peer",
        bindings=FileNameBindings(package_name="com.example"),
    )

    assert resolved.kind == "package_type"
    assert resolved.python_name == "Peer"
    assert resolved.import_line == "from com.example.Peer import Peer"
    assert resolved.is_type_reference


def test_default_package_compilation_unit_type_requests_absolute_import() -> None:
    resolved = resolve(
        "Peer",
        bindings=FileNameBindings(compilation_unit_types={"Peer"}),
    )

    assert resolved.kind == "compilation_unit_type"
    assert resolved.python_name == "Peer"
    assert resolved.import_line == "from Peer import Peer"
    assert resolved.is_type_reference


def test_all_caps_identifier_does_not_use_type_fallback() -> None:
    resolved = resolve(
        "VALUES",
        bindings=FileNameBindings(package_name="com.example"),
    )

    assert resolved.kind == "unknown"
    assert resolved.python_name == "values"
    assert resolved.import_line is None


def test_unknown_lowercase_identifier_remains_value_name() -> None:
    resolved = resolve("externalThing")

    assert resolved.kind == "unknown"
    assert resolved.python_name == "external_thing"
    assert resolved.import_line is None
    assert not resolved.is_type_reference


def test_unknown_identifier_respects_disabled_field_snake_case() -> None:
    resolved = resolve(
        "displayName",
        scope=NameScope(snake_case_fields=False),
    )

    assert resolved.kind == "unknown"
    assert resolved.python_name == "displayName"


def test_build_file_name_bindings_captures_current_skeleton_inputs() -> None:
    cfg = CFG.model_copy(
        update={
            "drop_imports": {*CFG.drop_imports, "com.example.Dropped"},
            "import_map": {
                **CFG.import_map,
                "com.example.ExternalThing": "from ext import ExternalThing as Thing",
            },
        },
    )
    parsed = parse_source(
        """
        package com.example;

        import com.example.ExternalThing;
        import com.example.Dropped;
        import com.example.Plain;
        import static java.lang.Math.PI;

        public class UsesNames {}
        """,
    )
    symbols = extract_symbols(parsed)

    bindings = build_file_name_bindings(
        parsed,
        symbols,
        cfg,
        static_field_aliases={"PI": "math.pi"},
        static_method_imports={"requireNonNull": "java.util.Objects.requireNonNull"},
    )

    assert bindings.package_name == "com.example"
    assert bindings.compilation_unit_types == {"UsesNames"}
    assert bindings.static_field_aliases == {"PI": "math.pi"}
    assert bindings.static_method_imports == {
        "requireNonNull": "java.util.Objects.requireNonNull",
    }
    assert bindings.imported_types["ExternalThing"] == TypeBinding(
        raw_name="ExternalThing",
        python_name="Thing",
        source="import_map",
    )
    assert bindings.imported_types["Dropped"] == TypeBinding(
        raw_name="Dropped",
        python_name="Dropped",
        source="drop_import",
    )
    assert bindings.imported_types["Plain"] == TypeBinding(
        raw_name="Plain",
        python_name="Plain",
        import_line="from com.example.Plain import Plain",
    )


def test_translation_context_has_empty_name_resolver_by_default() -> None:
    ctx = TranslationContext(cfg=CFG, diagnostics=TranslationDiagnostics())

    resolved = ctx.name_resolver.resolve_identifier("externalThing", NameScope())

    assert resolved.kind == "unknown"
    assert resolved.python_name == "external_thing"


def test_scope_from_context_reuses_context_collections() -> None:
    ctx = TranslationContext(
        cfg=CFG,
        diagnostics=TranslationDiagnostics(),
        expression_aliases={"value": "_j2py_value"},
        static_field_aliases={"PI": "math.pi"},
        param_names={"value"},
        local_names={"localValue"},
        class_fields={"fieldValue"},
        class_field_types={"fieldValue": "int"},
        nested_class_names={"Inner"},
    )

    scope = scope_from_context(ctx)

    assert scope.expression_aliases is ctx.expression_aliases
    assert scope.static_field_aliases is ctx.static_field_aliases
    assert scope.param_names is ctx.param_names
    assert scope.local_names is ctx.local_names
    assert scope.class_fields is ctx.class_fields
    assert scope.class_field_types is ctx.class_field_types
    assert scope.nested_class_names is ctx.nested_class_names

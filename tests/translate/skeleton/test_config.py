"""Skeleton translator tests — config and import emission."""

from tests.translate.skeleton.helpers import (
    CFG,
    assert_valid_python,
    translate_source,
)


def test_import_map_emits_configured_python_imports_and_drops_known_imports() -> None:
    python_source, coverage = translate_source(
        """
        import java.nio.file.Path;
        import java.util.List;

        public class UsesPath {
            public Path first(List<Path> paths) {
                return paths.get(0);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from pathlib import Path" in python_source
    assert "java.util.List" not in python_source
    assert "def first(self, paths: list[Path]) -> Path:" in python_source
    assert_valid_python(python_source)


def test_custom_import_map_and_naming_flags_are_respected() -> None:
    cfg = CFG.model_copy(
        update={
            "import_map": {**CFG.import_map, "com.example.ExternalThing": "from ext import Thing"},
            "snake_case_methods": False,
            "snake_case_fields": False,
        },
    )
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class Naming {
            private String displayName = "x";

            public String getDisplayName() {
                return displayName;
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert "from ext import Thing" in python_source
    assert "self.displayName: str" in python_source
    assert "def getDisplayName(self) -> str:" in python_source
    assert "return self.displayName" in python_source
    assert_valid_python(python_source)


def test_imported_class_references_keep_class_name_and_emit_import() -> None:
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class UsesExternal {
            public Object make() {
                return ExternalThing.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.ExternalThing import ExternalThing" in python_source
    assert "return ExternalThing.create()" in python_source
    assert "external_thing.create()" not in python_source
    assert_valid_python(python_source)


def test_local_variable_shadows_imported_class_reference() -> None:
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class UsesExternal {
            public Object make() {
                Object ExternalThing = source();
                return ExternalThing.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.ExternalThing import ExternalThing" not in python_source
    assert "external_thing = source()" in python_source
    assert "return external_thing.create()" in python_source
    assert "return ExternalThing.create()" not in python_source
    assert_valid_python(python_source)


def test_parameter_shadows_imported_class_reference() -> None:
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class UsesExternal {
            public Object make(Object ExternalThing) {
                return ExternalThing.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.ExternalThing import ExternalThing" not in python_source
    assert "def make(self, external_thing: object) -> object:" in python_source
    assert "return external_thing.create()" in python_source
    assert "return ExternalThing.create()" not in python_source
    assert_valid_python(python_source)


def test_field_shadows_imported_class_reference() -> None:
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class UsesExternal {
            private Object ExternalThing;

            public Object make() {
                return ExternalThing.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.ExternalThing import ExternalThing" not in python_source
    assert "self.external_thing: object | None = None" in python_source
    assert "return self.external_thing.create()" in python_source
    assert "return ExternalThing.create()" not in python_source
    assert_valid_python(python_source)


def test_same_package_class_references_emit_import_without_importing_static_fields() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class UsesPeer {
            private static final String[] VALUES = new String[1];

            static {
                Peer.fill(VALUES);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.Peer import Peer" in python_source
    assert "from com.example.VALUES import VALUES" not in python_source
    assert "Peer.fill(VALUES)" in python_source
    assert "peer.fill" not in python_source
    assert_valid_python(python_source)


def test_locals_and_parameters_shadow_same_package_class_fallback() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class UsesPeer {
            public Object local() {
                Object Peer = source();
                return Peer.create();
            }

            public Object param(Object Peer) {
                return Peer.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.Peer import Peer" not in python_source
    assert "peer = source()" in python_source
    assert "def param(self, peer: object) -> object:" in python_source
    assert python_source.count("return peer.create()") == 2
    assert "return Peer.create()" not in python_source
    assert_valid_python(python_source)


def test_field_shadows_same_package_class_fallback() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class UsesPeer {
            private Object Peer;

            public Object make() {
                return Peer.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.Peer import Peer" not in python_source
    assert "self.peer: object | None = None" in python_source
    assert "return self.peer.create()" in python_source
    assert "return Peer.create()" not in python_source
    assert_valid_python(python_source)


def test_containing_and_nested_class_references_do_not_request_peer_imports() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class Outer {
            static class Inner {
                static Object create() {
                    return null;
                }
            }

            public static Object create() {
                return null;
            }

            public Object makeInner() {
                return Inner.create();
            }

            public Object makeOuter() {
                return Outer.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.Inner import Inner" not in python_source
    assert "from com.example.Outer import Outer" not in python_source
    # A nested type referenced from a method body is not a bare local in Python; it is
    # reached through its enclosing class. The enclosing top-level class stays bare.
    assert "return Outer.Inner.create()" in python_source
    assert "return Outer.create()" in python_source
    assert "inner.create()" not in python_source
    assert "outer.create()" not in python_source
    assert_valid_python(python_source)


def test_static_imported_nested_member_qualifies_owner_in_method_body() -> None:
    # A wildcard static import of a nested class's members (Validators.*) binds the
    # owner to the bare nested name. From a method body that name is undefined, so the
    # owner must be reached through its enclosing class.
    python_source, coverage = translate_source(
        """
        package com.example;

        import static com.example.Host.Validators.*;

        public class Host {
            public static int build(int raw) {
                return nonNegative(raw);
            }

            static class Validators {
                static int nonNegative(int arg) {
                    return arg;
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return Host.Validators.non_negative(raw)" in python_source
    assert "return non_negative(raw)" not in python_source
    assert "from com.example.Validators import Validators" not in python_source
    assert_valid_python(python_source)


def test_static_imported_enum_constant_qualifies_through_enum() -> None:
    # `import static Lexer.Kind.*` lets the source name DOT/HYPHEN bare; in Python they
    # are reached through the enum, which itself is reached through its enclosing class.
    python_source, coverage = translate_source(
        """
        package com.example;

        import static com.example.Lexer.Kind.*;

        public class Lexer {
            public boolean isBoundary(Kind k) {
                return k == DOT || k == HYPHEN;
            }

            enum Kind {
                DOT,
                HYPHEN,
                EOI
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return k == Lexer.Kind.DOT or k == Lexer.Kind.HYPHEN" in python_source
    assert "== DOT" not in python_source
    assert_valid_python(python_source)


def test_nested_type_reference_in_class_body_stays_bare() -> None:
    # Inside a class body the sibling nested name is a bare local while the enclosing
    # class name is not yet bound, so a class-level reference must NOT be qualified.
    python_source, coverage = translate_source(
        """
        package com.example;

        public class Holder {
            static class Base {
            }

            static class Derived extends Base {
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "class Derived(Base):" in python_source
    assert "class Derived(Holder.Base):" not in python_source
    assert_valid_python(python_source)


def test_unknown_lowercase_identifier_remains_value_name() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class LowercaseValue {
            public Object make() {
                return externalThing.create();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.ExternalThing import ExternalThing" not in python_source
    assert "return external_thing.create()" in python_source
    assert "return ExternalThing.create()" not in python_source
    assert_valid_python(python_source)


def test_dropped_imports_keep_class_casing_without_emitting_import() -> None:
    cfg = CFG.model_copy(
        update={
            "drop_imports": {*CFG.drop_imports, "com.example.Dropped"},
        },
    )
    python_source, coverage = translate_source(
        """
        import com.example.Dropped;

        public class UsesDropped {
            public Object make() {
                return Dropped.create();
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert "return Dropped.create()" in python_source
    assert "from com.example.Dropped import Dropped" not in python_source
    assert "dropped.create()" not in python_source
    assert_valid_python(python_source)


def test_parameter_shadows_dropped_import_class_binding() -> None:
    cfg = CFG.model_copy(
        update={
            "drop_imports": {*CFG.drop_imports, "com.example.Dropped"},
        },
    )
    python_source, coverage = translate_source(
        """
        import com.example.Dropped;

        public class UsesDropped {
            public Object make(Object Dropped) {
                return Dropped.create();
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert "from com.example.Dropped import Dropped" not in python_source
    assert "return dropped.create()" in python_source
    assert "return Dropped.create()" not in python_source
    assert_valid_python(python_source)


def test_default_package_class_references_emit_absolute_import() -> None:
    python_source, coverage = translate_source(
        """
        public class Peer {
            public static void fill(String[] values) {
            }
        }

        public class UsesPeer {
            public static void run() {
                Peer.fill(new String[1]);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from Peer import Peer" in python_source
    assert "Peer.fill(" in python_source
    assert "peer.fill(" not in python_source
    assert_valid_python(python_source)


def test_imported_class_references_use_configured_import_binding() -> None:
    cfg = CFG.model_copy(
        update={
            "import_map": {**CFG.import_map, "com.example.ExternalThing": "from ext import Thing"},
        },
    )
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class UsesExternal {
            public Object make() {
                return ExternalThing.create();
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert "from ext import Thing" in python_source
    assert "return Thing.create()" in python_source
    assert "ExternalThing.create()" not in python_source
    assert_valid_python(python_source)


def test_imported_class_references_use_configured_import_alias_binding() -> None:
    cfg = CFG.model_copy(
        update={
            "import_map": {
                **CFG.import_map,
                "com.example.ExternalThing": "from ext import ExternalThing as Thing",
            },
        },
    )
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class UsesExternal {
            public Object make() {
                return ExternalThing.create();
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert "from ext import ExternalThing as Thing" in python_source
    assert "return Thing.create()" in python_source
    assert "return ExternalThing.create()" not in python_source
    assert_valid_python(python_source)


def test_imported_class_object_creation_does_not_request_expression_import_yet() -> None:
    python_source, coverage = translate_source(
        """
        import com.example.ExternalThing;

        public class UsesExternal {
            public Object make() {
                return new ExternalThing();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.ExternalThing import ExternalThing" not in python_source
    assert "return ExternalThing()" in python_source
    assert "return external_thing()" not in python_source
    assert_valid_python(python_source)

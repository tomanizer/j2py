"""Cross-file class-hierarchy translation.

Covers rule-layer fixes surfaced by the commons-lang ``tuple`` case study
(docs/CASE_STUDY_COMMONS_LANG_TUPLE.md):

* A generic superclass declared in another file (``extends Pair<L, R>``) must be kept
  as the Python base class and its import requested (previously the generic wrapper hid
  the type name and the base was silently dropped).
* A static field whose initializer references the class being defined
  (``NULL = new Foo()``) must be deferred to a post-class module assignment, since the
  class name is not yet bound inside the class body.
* Same-package sibling type references inside method bodies are emitted as function-local
  imports to break the base↔derived circular import cycle (issue #325).
"""

from tests.translate.skeleton.helpers import (
    assert_module_executes,
    assert_valid_python,
    translate_source,
)


def test_generic_same_package_superclass_is_kept_and_imported() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class Sub extends Base<String, Integer> {
            public String describe() {
                return "sub";
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.example.Base import Base" in python_source
    assert "class Sub(Base):" in python_source
    assert_valid_python(python_source)


def test_generic_superclass_uses_explicit_import_binding() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        import com.other.Base;

        public class Sub extends Base<String> {
            public String describe() {
                return "sub";
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from com.other.Base import Base" in python_source
    assert "class Sub(Base):" in python_source
    assert_valid_python(python_source)


def test_same_file_superclass_needs_no_import() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        class Base {
            public String describe() {
                return "base";
            }
        }

        class Sub extends Base {
        }
        """,
    )

    assert coverage == 1.0
    assert "class Sub(Base):" in python_source
    assert "from com.example.Base import Base" not in python_source
    # Both classes share the Python module, so the subclass resolves its base directly.
    assert_module_executes(python_source)


def test_self_referential_static_field_is_deferred_after_class() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class Node {
            private static final Node ROOT = new Node();

            public Node() {
            }
        }
        """,
    )

    assert coverage == 1.0
    class_body, _, deferred = python_source.partition("Node.ROOT = Node()")
    # The forward self-reference must not run inside the class body.
    assert "ROOT: Node = Node()" not in class_body
    assert "    ROOT" not in class_body
    # It is emitted once, at module level, after the class definition.
    assert "Node.ROOT = Node()" in python_source
    assert deferred.strip() == ""
    # The module imports cleanly (the original class-body form raised NameError).
    assert_module_executes(python_source)


def test_dependent_static_field_is_deferred_after_self_referential_field() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        public class Node {
            private static final Node ROOT = new Node();
            private static final Node ROOT_COPY = ROOT.copy();

            public Node copy() {
                return this;
            }
        }
        """,
    )

    assert coverage == 1.0
    class_body, _, deferred = python_source.partition("Node.ROOT = Node()")
    assert "ROOT: Node = Node()" not in class_body
    assert "ROOT_COPY: Node = ROOT.copy()" not in class_body
    assert "Node.ROOT = Node()" in python_source
    assert "Node.ROOT_COPY = Node.ROOT.copy()" in python_source
    assert python_source.index("Node.ROOT = Node()") < python_source.index(
        "Node.ROOT_COPY = Node.ROOT.copy()",
    )
    assert deferred.strip() == "Node.ROOT_COPY = Node.ROOT.copy()"
    assert_module_executes(python_source)


def test_method_reference_static_field_dependency_is_deferred_in_order() -> None:
    python_source, coverage = translate_source(
        """
        package com.example;

        import java.util.Comparator;

        public class Version {
            public static final Comparator<Version> INCREMENT_ORDER =
                    Version::compareToIgnoreBuildMetadata;
            public static final Comparator<Version> PRECEDENCE_ORDER =
                    INCREMENT_ORDER.reversed();

            public int compareToIgnoreBuildMetadata(Version other) {
                return 0;
            }
        }
        """,
    )

    assert coverage == 1.0
    class_body, _, deferred = python_source.partition(
        "Version.INCREMENT_ORDER = Version.compare_to_ignore_build_metadata",
    )
    assert "INCREMENT_ORDER: Comparator[Version]" not in class_body
    assert "PRECEDENCE_ORDER: Comparator[Version]" not in class_body
    assert "Version.INCREMENT_ORDER = Version.compare_to_ignore_build_metadata" in python_source
    assert "Version.PRECEDENCE_ORDER = Version.INCREMENT_ORDER.reversed()" in python_source
    assert python_source.index(
        "Version.INCREMENT_ORDER = Version.compare_to_ignore_build_metadata",
    ) < python_source.index("Version.PRECEDENCE_ORDER = Version.INCREMENT_ORDER.reversed()")
    assert deferred.strip() == "Version.PRECEDENCE_ORDER = Version.INCREMENT_ORDER.reversed()"
    assert_valid_python(python_source)


def test_same_package_sibling_ref_in_method_body_is_local_import() -> None:
    # Issue #325: base↔derived circular import. Base.factory() references the derived
    # class (same package, no explicit Java import). That reference must become a
    # function-local import, not a module-level one, so the derived file can import
    # the base without triggering a circular import error.
    python_source, coverage = translate_source(
        """
        package com.example;

        public class Base {
            public static Base create() {
                return new Derived();
            }
        }
        """,
    )

    assert coverage == 1.0
    module_imports, _, class_body = python_source.partition("\nclass Base")
    # Sibling reference must NOT appear at module level.
    assert "from com.example.Derived import Derived" not in module_imports
    # It MUST appear as a local import inside the method body.
    assert "from com.example.Derived import Derived" in class_body
    assert_valid_python(python_source)

"""Cross-file class-hierarchy translation.

Covers two rule-layer fixes surfaced by the commons-lang ``tuple`` case study
(docs/CASE_STUDY.md):

* A generic superclass declared in another file (``extends Pair<L, R>``) must be kept
  as the Python base class and its import requested (previously the generic wrapper hid
  the type name and the base was silently dropped).
* A static field whose initializer references the class being defined
  (``NULL = new Foo()``) must be deferred to a post-class module assignment, since the
  class name is not yet bound inside the class body.
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

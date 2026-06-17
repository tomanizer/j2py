"""Overload classifier tests."""

from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import JavaNode, parse_source
from j2py.translate.class_members import member_groups, member_python_name
from j2py.translate.overload_classification import OverloadKind, classify_overload_group

CFG = ConfigLoader().add_defaults().build()


def _overload_group(source: str, name: str) -> list[JavaNode]:
    parsed = parse_source(source)
    for class_node in parsed.root.find_all("class_declaration"):
        body = class_node.child_by_field("body")
        assert body is not None
        members = [
            child
            for child in body.named_children
            if child.type in {"constructor_declaration", "method_declaration"}
        ]
        for group in member_groups(members):
            if member_python_name(group[0]) == name:
                return group
    raise AssertionError(f"missing overload group {name!r}")


def test_classifies_forwarding_overloads_as_merge_forwarding() -> None:
    group = _overload_group(
        """
        public class Ranges {
            public static Range of(String start, String end) {
                return of(start, end, null);
            }

            public static Range of(String start, String end, Comparator comparator) {
                return new Range(start, end, comparator);
            }
        }
        """,
        "of",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.MERGE_FORWARDING
    assert classification.reason == "overload group forwards to one implementation"


def test_classifies_identical_body_overloads_as_merge_equivalent() -> None:
    group = _overload_group(
        """
        public class Over {
            public int get(int value) { return 1; }
            public int get(String value) { return 1; }
        }
        """,
        "get",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.MERGE_IDENTICAL_OR_EQUIVALENT
    assert "identical or equivalent" in classification.reason


def test_classifies_runtime_value_dispatch_when_guards_are_distinct() -> None:
    group = _overload_group(
        """
        public class Over {
            public int get(int value) { return value; }
            public int get(String value) { return 1; }
        }
        """,
        "get",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.VALUE_DISPATCH_SAFE
    assert classification.guard_signatures == (
        ("isinstance({arg}, int) and not isinstance({arg}, bool)",),
        ("isinstance({arg}, str)",),
    )


def test_classifies_runtime_dispatch_when_erased_signatures_are_distinct() -> None:
    group = _overload_group(
        """
        class Foo {}
        class Bar {}

        public class Over {
            public int get(Foo value) { return 1; }
            public int get(Bar value) { return 2; }
        }
        """,
        "get",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.RUNTIME_DISPATCH_SAFE
    assert classification.reason == "erased Python signatures are pairwise distinct"


def test_classifies_erasure_collisions_as_unsafe() -> None:
    group = _overload_group(
        """
        public class Over {
            public int width(int value) { return value; }
            public int width(long value) { return 1; }
        }
        """,
        "width",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.ERASURE_COLLISION_UNSAFE
    assert classification.erased_signatures == (("int",), ("int",))
    assert "indistinguishable Python runtime shapes" in classification.reason


def test_constructor_pass_through_forwarding_does_not_claim_merge_support() -> None:
    group = _overload_group(
        """
        public class Box {
            public Box(int value) {
                this(Integer.valueOf(value));
            }

            public Box(Integer value) {
                value.toString();
            }
        }
        """,
        "__init__",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.ERASURE_COLLISION_UNSAFE
    assert classification.erased_signatures == (("int",), ("int",))


def test_classifies_static_instance_same_name_collision_separately() -> None:
    group = _overload_group(
        """
        public class Circuit {
            public static boolean isOpen(Circuit breaker) {
                return breaker.isOpen();
            }

            public boolean isOpen() {
                return true;
            }
        }
        """,
        "is_open",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.STATIC_INSTANCE_COLLISION
    assert classification.reason == "static and instance members share one Python name"


def test_classifies_fixed_arity_beats_varargs_as_value_dispatch_varargs_safe() -> None:
    group = _overload_group(
        """
        public class Stats {
            public static int max(int a, int b, int c) {
                return a > b ? (a > c ? a : c) : (b > c ? b : c);
            }

            public static int max(int... values) {
                return values[0];
            }
        }
        """,
        "max_",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.VALUE_DISPATCH_VARARGS_SAFE
    assert "fixed and varargs guards are pairwise distinct" in classification.reason
    assert classification.guard_signatures == (
        ("fixed", "3", "int", "int", "int"),
        ("varargs", "0", "int:spread"),
    )


def test_classifies_varargs_erasure_collisions_as_unsafe() -> None:
    group = _overload_group(
        """
        public class Unsafe {
            public static int pick(int... values) {
                return 1;
            }

            public static int pick(long... values) {
                return 2;
            }
        }
        """,
        "pick",
    )

    classification = classify_overload_group(group, CFG)

    assert classification.kind is OverloadKind.ERASURE_COLLISION_UNSAFE
    assert classification.erased_signatures == (("*int",), ("*int",))
    assert "indistinguishable Python runtime shapes" in classification.reason

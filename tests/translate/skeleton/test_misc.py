"""Skeleton translator tests — miscellaneous skeleton behaviour."""

from tests.translate.skeleton.helpers import (
    assert_valid_python,
    translate_source,
)


def test_receiverless_method_call_escapes_python_builtin_name() -> None:
    python_source, coverage = translate_source(
        """
        public class BuiltinHelper {
            public String list() {
                return "external";
            }
        }

        public class BuiltinName {
            public String list() {
                return "value";
            }

            public String assertThat(String value) {
                return value;
            }

            public String call() {
                return list();
            }

            public String callHelper(String value) {
                return assertThat(value);
            }

            public String callGlobal(String value) {
                return when(value);
            }

            public String callExternal(BuiltinHelper helper) {
                return helper.list();
            }

            public String callUndeclared(ExternalHelper helper) {
                return helper.list();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "def list_(self) -> str:" in python_source
    assert "return self.list_()" in python_source
    assert "return list()" not in python_source
    assert "return self.assert_that(value)" in python_source
    assert "return when(value)" in python_source
    assert "return self.when(value)" not in python_source
    assert "return helper.list_()" in python_source
    assert "def call_undeclared(self, helper: ExternalHelper) -> str:" in python_source
    assert "return helper.list()" in python_source
    assert_valid_python(python_source)


def test_non_empty_collection_constructor_translates_to_copy() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.ArrayList;
        import java.util.HashMap;
        import java.util.HashSet;
        import java.util.List;
        import java.util.Map;
        import java.util.Set;

        public class Copy {
            public List<String> copy(List<String> people) {
                List<String> copied = new ArrayList<>(people);
                return copied;
            }

            public Map<String, String> copyMap(Map<String, String> source) {
                return new HashMap<>(source);
            }

            public Set<String> copySet(Set<String> source) {
                return new HashSet<>(source);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "copied = list(people)" in python_source
    assert "return dict(source)" in python_source
    assert "return set(source)" in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)

"""Skeleton translator tests — stream pipeline rewrites."""



from tests.translate.skeleton.helpers import (
    CFG,
    assert_valid_python,
    translate_source,
    translate_source_with_diagnostics,
)


def test_stream_item_name_avoids_bad_singularization() -> None:
    """Regression: _stream_item_name used to produce statu/addres/clas etc."""
    from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
    from j2py.translate.expressions import _stream_item_name

    ctx = TranslationContext(cfg=CFG, diagnostics=TranslationDiagnostics())

    cases = {
        "statuses": "status",
        "status": "status",
        "addresses": "address",
        "address": "address",
        "classes": "class",
        "items": "item",
        "entries": "entry",
    }
    for src_name, want in cases.items():
        got = _stream_item_name(src_name, ctx)
        # tolerate "item_" style safety suffix from naming
        ok = got == want or got == want + "_" or got.endswith(want) or got.endswith(want + "_")
        assert ok, f"{src_name} -> {got} (wanted ~{want})"





def test_stream_pipeline_produces_sensible_loop_var_for_statuses() -> None:
    """A successful stream rewrite for a 'statuses' receiver should not emit statu/statuse."""
    python_source, coverage = translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> names(List<Status> statuses) {
                return statuses.stream()
                        .map(Status::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    # The pipeline must have fired and produced a clean listcomp (coverage 1.0 for this file)
    assert coverage == 1.0
    # The loop variable should be a sensible singular ("status" or "status_" after naming),
    # not a truncated form like "statu".
    assert "for status in statuses" in python_source or "for status_ in statuses" in python_source
    # Avoid old bad truncation in the generated comp (signatures may still contain "statuses").
    assert "for statu in" not in python_source and "for statu_" not in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)





def test_stream_pipeline_to_set_rewrite() -> None:
    """Phase 1: toSet collector now rewrites to set comprehension."""
    python_source, coverage = translate_source(
        """
        import java.util.Set;
        import java.util.stream.Collectors;

        public class Streams {
            public Set<String> unique(List<Status> statuses) {
                return statuses.stream()
                        .map(Status::getName)
                        .collect(Collectors.toSet());
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "{" in python_source and " for " in python_source and "}" in python_source
    assert "for status in statuses" in python_source or "for status_ in statuses" in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)





def test_stream_pipeline_joining_basic() -> None:
    """Phase 1: basic Collectors.joining() rewrites to .join(genexp)."""
    python_source, coverage = translate_source(
        """
        import java.util.stream.Collectors;

        public class Streams {
            public String joined(List<String> parts) {
                return parts.stream()
                        .filter(s -> !s.isEmpty())
                        .collect(Collectors.joining(", "));
            }
        }
        """,
    )

    assert coverage == 1.0
    assert ".join(" in python_source
    assert "for " in python_source and " in parts" in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)





def test_stream_source_call_uses_valid_loop_target_for_collection_values() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.Set;
        import java.util.stream.Collectors;

        public class Streams {
            public Set<ExecutableHint> constructors(Builder builder) {
                return builder.constructors.values().stream()
                        .map(ExecutableHint.Builder::build)
                        .collect(Collectors.toSet());
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "for values() in" not in python_source
    assert "for value in builder.constructors.values()" in python_source
    assert "value.build()" in python_source
    assert_valid_python(python_source)





def test_stream_source_getter_call_uses_valid_loop_target_for_joining() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.stream.Collectors;

        public class Streams {
            public String signature(JdkProxyHint left) {
                return left.getProxiedInterfaces().stream()
                        .map(TypeReference::getCanonicalName)
                        .collect(Collectors.joining(","));
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "for get_proxied_interfaces() in" not in python_source
    assert "for interface in left.get_proxied_interfaces()" in python_source
    assert "interface.get_canonical_name()" in python_source
    assert_valid_python(python_source)





def test_stream_pipeline_sorted_and_distinct() -> None:
    """Phase 2: support .sorted() and .distinct() as post-wraps on the comp."""
    # Safe when they appear late in the chain before terminal.
    python_source, coverage = translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> sortedUnique(List<String> items) {
                return items.stream()
                        .filter(s -> s.length() > 0)
                        .sorted()
                        .distinct()
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert coverage == 1.0
    # Should have the inner comp wrapped with sorted and distinct
    assert "list(dict.fromkeys(sorted(" in python_source
    assert " for " in python_source and " in items" in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)





def test_stream_pipeline_sorted_with_key() -> None:
    """Phase 2: .sorted(Comparator) with simple method ref key."""
    python_source, coverage = translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<Item> byName(List<Item> items) {
                return items.stream()
                        .sorted(Item::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "sorted(" in python_source
    assert "key=lambda " in python_source  # or similar
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)





def test_stream_sorted_before_map_falls_back_to_preserve_order() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> sortedNames(List<Item> items) {
                return items.stream()
                        .sorted()
                        .map(Item::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "stream map after sorted/distinct requires order-preserving translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    assert "return sorted([item.get_name() for item in items])" not in result.source
    assert_valid_python(result.source)





def test_stream_distinct_before_map_falls_back_to_preserve_order() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> uniqueNames(List<Item> items) {
                return items.stream()
                        .distinct()
                        .map(Item::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "stream map after sorted/distinct requires order-preserving translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    assert "dict.fromkeys([item.get_name() for item in items])" not in result.source
    assert_valid_python(result.source)





def test_joining_with_prefix_suffix_falls_back() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.stream.Collectors;

        public class Streams {
            public String joined(List<String> parts) {
                return parts.stream()
                        .collect(Collectors.joining(", ", "[", "]"));
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "Collectors.joining with prefix/suffix requires manual translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    assert_valid_python(result.source)





def test_stream_pipeline_grouping_by_basic() -> None:
    """Phase 3: basic groupingBy produces helper with defaultdict accumulation."""
    python_source, coverage = translate_source(
        """
        import java.util.List;
        import java.util.Map;
        import java.util.stream.Collectors;

        public class Streams {
            public Map<String, List<String>> byFirst(List<String> items) {
                return items.stream()
                        .filter(s -> !s.isEmpty())
                        .collect(Collectors.groupingBy(s -> s.substring(0,1)));
            }
        }
        """,
    )

    assert coverage > 0.5  # at least the construct itself handled
    assert "def _j2py_groupby_" in python_source
    assert "from collections import defaultdict" in python_source
    assert "groups[key].append" in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)





def test_stream_pipeline_to_map_basic() -> None:
    """Phase 3: basic toMap produces helper with dict accumulation."""
    python_source, coverage = translate_source(
        """
        import java.util.Map;
        import java.util.stream.Collectors;

        public class Streams {
            public Map<String, Integer> toMap(List<Item> items) {
                return items.stream()
                        .filter(i -> i.getValue() > 0)
                        .collect(Collectors.toMap(Item::getKey, Item::getValue));
            }
        }
        """,
    )

    assert "def _j2py_to_map_" in python_source
    assert "result = {}" in python_source
    assert "result[key] = " in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)





def test_to_map_with_merge_function_falls_back() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.Map;
        import java.util.stream.Collectors;

        public class Streams {
            public Map<String, Integer> toMap(List<Item> items) {
                return items.stream()
                        .collect(Collectors.toMap(Item::getKey, Item::getValue, (a, b) -> b));
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "Collectors.toMap with merge/supplier arguments requires manual translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    assert_valid_python(result.source)





def test_stream_flatmap_list_stream_to_list_rewrite() -> None:
    """flatMap(List::stream) rewrites to nested comprehension instead of flat_map chain."""
    python_source, coverage = translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> flat(List<List<String>> nested) {
                return nested.stream()
                        .flatMap(List::stream)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "flat_map" not in python_source
    assert ".stream()" not in python_source
    assert "for nested in nested" in python_source
    assert "for nested_item in nested" in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)


def test_stream_flatmap_with_map_rewrite() -> None:
    """AdvancedStreams flatMapExample pattern: flatMap then map to upper case."""
    python_source, coverage = translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> nestedUpper(List<List<String>> nested) {
                return nested.stream()
                        .flatMap(List::stream)
                        .map(String::toUpperCase)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "to_upper_case()" in python_source
    assert ".flat_map(" not in python_source
    assert_valid_python(python_source)


def test_stream_flatmap_unsupported_mapper_falls_back() -> None:
    """Non-method-reference flatMap mappers still record an explicit diagnostic."""
    result = translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> flat(List<List<String>> nested) {
                return nested.stream()
                        .flatMap(list -> list.stream())
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    reasons = [u.reason for u in result.diagnostics.unhandled]
    assert any("unsupported stream intermediate: flatMap" in r for r in reasons)
    assert_valid_python(result.source)



